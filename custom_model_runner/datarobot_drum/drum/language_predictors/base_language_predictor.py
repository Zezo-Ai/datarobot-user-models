"""
Copyright 2021 DataRobot, Inc. and its affiliates.
All rights reserved.
This is proprietary source code of DataRobot, Inc. and its affiliates.
Released under the terms of DataRobot Tool and Utility Agreement.
"""
import itertools
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from random import getrandbits
from typing import Optional, List
from uuid import UUID

import pandas as pd

from datarobot_drum.drum.adapters.cli.shared.drum_class_label_adapter import DrumClassLabelAdapter
from datarobot_drum.drum.adapters.model_adapters.python_model_adapter import RawPredictResponse
from datarobot_drum.drum.common import to_bool
from datarobot_drum.drum.lazy_loading.lazy_loading_handler import LazyLoadingHandler
from datarobot_drum.drum.model_metadata import read_model_metadata_yaml
from datarobot_drum.drum.enum import (
    LOGGER_NAME_PREFIX,
    ModelInfoKeys,
    StructuredDtoKeys,
    TargetType,
)
from datarobot_drum.drum.typeschema_validation import SchemaValidator
from datarobot_drum.drum.utils.structured_input_read_utils import StructuredInputReadUtils
from datarobot_drum.drum.data_marshalling import marshal_predictions
from datarobot_drum.drum.root_predictors.chat_helpers import is_streaming_response

import datarobot as dr
from datarobot_mlops.common.connected_exception import DRMLOpsConnectedException

DEFAULT_PROMPT_COLUMN_NAME = "promptText"
EXCEPTION_422 = "predictionInputs/fromJSON/: 422 Client Error: UNPROCESSABLE ENTITY for url"
DRIFT_ERROR_MESSAGE = (
    "Feature Drift tracking and predictions data collection are disabled. Enable feature drift "
    "tracking or predictions data collection from deployment settings first, to post features"
)

logger = logging.getLogger(LOGGER_NAME_PREFIX + "." + __name__)

mlops_loaded = False
mlops_import_error = None
MLOps = None
try:
    from datarobot_mlops.mlops import MLOps
    from datarobot_mlops.common.exception import DRCommonException

    mlops_loaded = True
except ImportError as e:
    mlops_import_error = "Error importing MLOps python module(new path): {}".format(e)
    try:
        from datarobot.mlops.mlops import MLOps
        from datarobot.mlops.common.exception import DRCommonException

        mlops_loaded = True
    except ImportError as e:
        mlops_import_error += "\n\tError importing MLOps python module(old path): {}".format(e)


def uuid4_fast():
    # https://bugs.python.org/issue45556
    return UUID(int=getrandbits(128), version=4)


@dataclass
class PredictResponse:
    predictions: pd.DataFrame
    extra_model_output: Optional[pd.DataFrame] = None

    @property
    def combined_dataframe(self):
        return (
            self.predictions
            if self.extra_model_output is None
            else self.predictions.join(self.extra_model_output)
        )


class BaseLanguagePredictor(DrumClassLabelAdapter, ABC):
    def __init__(
        self,
        target_type: TargetType = None,
        positive_class_label: Optional[str] = None,
        negative_class_label: Optional[str] = None,
        class_labels: Optional[List[str]] = None,
    ):
        DrumClassLabelAdapter.__init__(
            self,
            target_type=target_type,
            positive_class_label=positive_class_label,
            negative_class_label=negative_class_label,
            class_labels=class_labels,
        )
        self._deployment = None
        self._model = None
        self._code_dir = None
        self._params = None
        self._mlops = None
        self._schema_validator = None
        self._prompt_column_name = DEFAULT_PROMPT_COLUMN_NAME

    def configure(self, params):
        """
        Set class instance variables based on input pipeline.
        """
        # DrumClassLabelAdapter fields
        self.positive_class_label = params.get("positiveClassLabel")
        self.negative_class_label = params.get("negativeClassLabel")
        self.class_labels = params.get("classLabels")
        self.target_type = TargetType(params.get("target_type"))

        self._code_dir = params["__custom_model_path__"]
        self._params = params

        if to_bool(params.get("allow_dr_api_access")):
            logger.info("Initializing DataRobot Python client.")
            dr_api_endpoint = self._dr_api_url(endpoint=params["external_webserver_url"])
            dr.Client(token=params["api_token"], endpoint=dr_api_endpoint)

        if self._should_enable_mlops():
            self._init_mlops()

        model_metadata = read_model_metadata_yaml(self._code_dir)
        if model_metadata:
            self._schema_validator = SchemaValidator(model_metadata.get("typeSchema", {}))

    @staticmethod
    def _dr_api_url(endpoint):
        if not endpoint.endswith("api/v2"):
            endpoint = f"{endpoint}/api/v2"
        return endpoint

    def _should_enable_mlops(self):
        return to_bool(self._params.get("monitor")) or self.supports_chat()

    def supports_chat(self):
        return False

    def _init_mlops(self):
        deployment_id = self._params.get("deployment_id", None)
        if not deployment_id:
            logger.info("Deployment id not set, monitoring will be disabled.")
            return

        if not mlops_loaded:
            raise Exception("MLOps module was not imported: {}".format(mlops_import_error))

        if to_bool(self._params.get("allow_dr_api_access")):
            try:
                self._deployment = dr.Deployment.get(deployment_id)
            except Exception as e:
                logger.warning(f"Failed to get deployment info: {e}", exc_info=True)

        self._mlops = MLOps()

        self._mlops.set_deployment_id(deployment_id)

        if self._params.get("model_id", None):
            self._mlops.set_model_id(self._params["model_id"])

        self._configure_mlops()

        if self.supports_chat():
            self._prompt_column_name = self.get_prompt_column_name()
            logger.debug("Prompt column name: %s", self._prompt_column_name)

        self._mlops.init()

    def _configure_mlops(self):
        # If monitor_settings were provided (e.g. for testing) use them, otherwise we will
        # use the API spooler as the default config.
        if self._params.get("monitor_settings"):
            self._mlops.set_channel_config(self._params["monitor_settings"])
        else:
            for required_param in ["external_webserver_url", "api_token"]:
                if required_param not in self._params:
                    raise ValueError(f"MLOps monitoring requires '{required_param}' parameter")
            self._mlops.set_api_spooler(
                mlops_service_url=self._params["external_webserver_url"],
                mlops_api_token=self._params["api_token"],
            )
            self._mlops.set_async_reporting()

    def get_prompt_column_name(self):
        if not self._params.get("deployment_id", None):
            logger.error(
                "No deployment ID found while configuring mlops for chat. "
                f"Fallback to default prompt column name ('{DEFAULT_PROMPT_COLUMN_NAME}')"
            )
            return DEFAULT_PROMPT_COLUMN_NAME

        if self._deployment:
            return self._deployment.model.get("prompt", DEFAULT_PROMPT_COLUMN_NAME)
        logger.warning(
            f"Falling back to default prompt column name ('{DEFAULT_PROMPT_COLUMN_NAME}')"
        )
        return DEFAULT_PROMPT_COLUMN_NAME

    @staticmethod
    def _validate_expected_env_variables(*args):
        for env_var in args:
            if not os.environ.get(env_var):
                raise Exception(f"A valid environment variable '{env_var}' is missing!")

    def monitor(self, kwargs, predictions, predict_time_ms):
        if to_bool(self._params.get("monitor")):
            self._mlops.report_deployment_stats(
                num_predictions=len(predictions), execution_time_ms=predict_time_ms
            )

            df = StructuredInputReadUtils.read_structured_input_data_as_df(
                kwargs.get(StructuredDtoKeys.BINARY_DATA),
                kwargs.get(StructuredDtoKeys.MIMETYPE),
            )
            # mlops.report_predictions_data expect the prediction data in the following format:
            # Regression: [10, 12, 13]
            # Classification: [[0.5, 0.5], [0.7, 03]]
            # In case of classification, class names are also required
            class_names = None
            if len(predictions.columns) == 1:
                mlops_predictions = predictions[predictions.columns[0]].tolist()
            else:
                mlops_predictions = predictions.values.tolist()
                class_names = list(predictions.columns)
            # TODO: Need to convert predictions to a proper format
            # TODO: or add report_predictions_data that can handle a df directly..
            # TODO: need to handle associds correctly

            self._mlops.report_predictions_data(
                features_df=df, predictions=mlops_predictions, class_names=class_names
            )

    def predict(self, **kwargs) -> PredictResponse:
        start_predict = time.time()
        raw_predict_response = self._predict(**kwargs)
        predictions_df = marshal_predictions(
            request_labels=self.class_ordering,
            predictions=raw_predict_response.predictions,
            target_type=self.target_type,
            model_labels=raw_predict_response.columns,
        )
        end_predict = time.time()
        execution_time_ms = (end_predict - start_predict) * 1000
        self.monitor(kwargs, predictions_df, execution_time_ms)
        return PredictResponse(predictions_df, raw_predict_response.extra_model_output)

    @abstractmethod
    def _predict(self, **kwargs) -> RawPredictResponse:
        """Predict on input_filename or binary_data"""
        pass

    def chat(self, completion_create_params, **kwargs):
        start_time = time.time()
        try:
            association_id = str(uuid4_fast())
            response = self._chat(completion_create_params, association_id, **kwargs)
            response = self._validate_chat_response(response)
        except Exception as e:
            self._mlops_report_error(start_time)
            raise e

        if not is_streaming_response(response):
            self._mlops_report_chat_prediction(
                completion_create_params,
                start_time,
                response.choices[0].message.content,
                association_id,
            )
            setattr(response, "datarobot_association_id", association_id)
            return response
        else:

            def generator():
                message_content = []
                try:
                    for chunk in response:
                        if chunk.choices and chunk.choices[0].delta.content:
                            message_content.append(chunk.choices[0].delta.content)
                        setattr(chunk, "datarobot_association_id", association_id)
                        yield chunk
                except Exception:
                    self._mlops_report_error(start_time)
                    raise

                self._mlops_report_chat_prediction(
                    completion_create_params, start_time, "".join(message_content), association_id
                )

            return generator()

    def get_supported_llm_models(self):
        return self._get_supported_llm_models()

    def _get_supported_llm_models(self):
        raise NotImplementedError("GET /models (get_models) is not implemented ")

    def _chat(self, completion_create_params, association_id, **kwargs):
        raise NotImplementedError("Chat is not implemented ")

    def _mlops_report_chat_prediction(
        self, completion_create_params, start_time, message_content, association_id
    ):
        if not self._mlops:
            return

        execution_time_ms = (time.time() - start_time) * 1000

        try:
            self._mlops.report_deployment_stats(
                num_predictions=1, execution_time_ms=execution_time_ms
            )
        except DRCommonException:
            logger.exception("Failed to report deployment stats")

        prompt_content = completion_create_params["messages"][-1]["content"]
        if isinstance(prompt_content, str):
            latest_message = completion_create_params["messages"][-1]["content"]
        elif isinstance(prompt_content, list):
            concatenated_prompt = []
            for content in prompt_content:
                if content["type"] == "text":
                    message = content["text"]
                elif content["type"] == "image_url":
                    message = f"Image URL: {content['image_url']['url']}"
                elif content["type"] == "input_audio":
                    message = f"Audio Input, Format: {content['input_audio']['format']}"
                else:
                    message = f"Unhandled content type: {content['type']}"
                concatenated_prompt.append(message)
            latest_message = "\n".join(concatenated_prompt)
        else:
            logger.warning(f"Unhandled prompt type: {type(prompt_content)}")
            return
        features_df = pd.DataFrame([{self._prompt_column_name: latest_message}])
        predictions = [message_content]

        try:
            self._mlops.report_predictions_data(
                features_df,
                predictions,
                association_ids=[association_id],
            )
        except DRMLOpsConnectedException as e:
            exception_string = str(e)
            if EXCEPTION_422 in exception_string and DRIFT_ERROR_MESSAGE in exception_string:
                logger.warning(exception_string)
                return
        except DRCommonException:
            logger.exception("Failed to report predictions data")

    def _mlops_report_error(self, start_time):
        if not self._mlops:
            return

        execution_time_ms = (time.time() - start_time) * 1000

        try:
            self._mlops.report_deployment_stats(
                num_predictions=0, execution_time_ms=execution_time_ms
            )
        except DRCommonException:
            logger.exception("Failed to report deployment stats")

    @staticmethod
    def _validate_chat_response(response):
        if getattr(response, "object", None) == "chat.completion":
            return response

        try:
            # Take a peek at the first object in the iterable to make sure that this is indeed a chat completion chunk.
            # This should catch cases where hook returns an iterable of a different type early on.
            response_iter = iter(response)
            first_chunk = next(response_iter)

            if type(first_chunk).__name__ == "ChatCompletionChunk":
                # Return a new iterable where the peeked object is included in the beginning
                return itertools.chain([first_chunk], response_iter)
            else:
                raise Exception(
                    f"First chunk does not look like chat completion chunk. str(chunk): '{first_chunk}'"
                )
        except StopIteration:
            return iter(())
        except Exception as e:
            raise Exception(
                f"Expected response to be ChatCompletion or Iterable[ChatCompletionChunk]. response type: {type(response)}."
                f"response(str): {str(response)}"
            ) from e

    def transform(self, **kwargs):
        output = self._transform(**kwargs)
        output_X = output[0]
        if self.target_type.value == TargetType.TRANSFORM.value and self._schema_validator:
            self._schema_validator.validate_outputs(output_X)
        return output

    @abstractmethod
    def _transform(self, **kwargs):
        """Predict on input_filename or binary_data"""
        pass

    @abstractmethod
    def has_read_input_data_hook(self):
        """Check if read_input_data hook defined in predictor"""
        pass

    def model_info(self):
        model_info = {
            ModelInfoKeys.TARGET_TYPE: self.target_type.value,
            ModelInfoKeys.CODE_DIR: self._code_dir,
        }

        if self.target_type == TargetType.BINARY:
            model_info.update({ModelInfoKeys.POSITIVE_CLASS_LABEL: self.positive_class_label})
            model_info.update({ModelInfoKeys.NEGATIVE_CLASS_LABEL: self.negative_class_label})
        elif self.target_type == TargetType.MULTICLASS:
            model_info.update({ModelInfoKeys.CLASS_LABELS: self.class_labels})

        return model_info

    @staticmethod
    def _handle_lazy_loading_files():
        lazy_loading_handler = LazyLoadingHandler()
        if lazy_loading_handler.is_lazy_loading_available:
            lazy_loading_handler.download_lazy_loading_files()
