"""
Copyright 2021 DataRobot, Inc. and its affiliates.
All rights reserved.
This is proprietary source code of DataRobot, Inc. and its affiliates.
Released under the terms of DataRobot Tool and Utility Agreement.
"""
import logging
import os
import sys
import textwrap
from dataclasses import dataclass
from inspect import signature
from pathlib import Path
from typing import Optional, Union
from typing import NoReturn

import numpy as np
import pandas as pd
from pandas.core.indexes.base import Index
from scipy.sparse import issparse

from datarobot_drum.drum.adapters.model_adapters.abstract_model_adapter import AbstractModelAdapter
from datarobot_drum.drum.artifact_predictors.keras_predictor import KerasPredictor
from datarobot_drum.drum.artifact_predictors.sklearn_predictor import SKLearnPredictor
from datarobot_drum.drum.artifact_predictors.torch_predictor import PyTorchPredictor
from datarobot_drum.drum.artifact_predictors.xgboost_predictor import XGBoostPredictor
from datarobot_drum.drum.artifact_predictors.onnx_predictor import ONNXPredictor
from datarobot_drum.drum.root_predictors.chat_helpers import is_openai_model
from datarobot_drum.drum.common import (
    reroute_stdout_to_stderr,
    SupportedPayloadFormats,
)
from datarobot_drum.drum.data_marshalling import marshal_predictions
from datarobot_drum.drum.data_marshalling import get_request_labels
from datarobot_drum.drum.enum import (
    CLASS_LABELS_ARG_KEYWORD,
    CUSTOM_FILE_NAME,
    CUSTOM_PY_CLASS_NAME,
    CustomHooks,
    LOGGER_NAME_PREFIX,
    ModelInfoKeys,
    NEGATIVE_CLASS_LABEL_ARG_KEYWORD,
    POSITIVE_CLASS_LABEL_ARG_KEYWORD,
    PRED_COLUMN,
    PayloadFormat,
    StructuredDtoKeys,
    TargetType,
    MODERATIONS_HOOK_MODULE,
    MODERATIONS_LIBRARY_PACKAGE,
)
from datarobot_drum.drum.exceptions import (
    DrumCommonException,
    DrumException,
    DrumTransformException,
    DrumSerializationError,
)
from datarobot_drum.drum.utils.dataframe import extract_additional_columns
from datarobot_drum.drum.utils.structured_input_read_utils import StructuredInputReadUtils
from datarobot_drum.drum.utils.drum_utils import DrumUtils
from datarobot_drum.custom_task_interfaces.custom_task_interface import (
    CustomTaskInterface,
    secrets_injection_context,
    load_secrets,
    patch_outputs_to_scrub_secrets,
)

from datarobot_drum import RuntimeParameters

RUNNING_LANG_MSG = "Running environment language: Python."


class DrumPythonModelAdapterError(DrumException):
    """Raised in case of error in PythonModelAdapter"""


@dataclass
class RawPredictResponse:
    predictions: np.ndarray
    columns: Optional[Union[Index, np.ndarray]] = None
    extra_model_output: Optional[pd.DataFrame] = None


class PythonModelAdapter(AbstractModelAdapter):
    def __init__(self, model_dir, target_type=None):
        self._logger = logging.getLogger(LOGGER_NAME_PREFIX + "." + self.__class__.__name__)

        # Get all the artifact predictors we have
        # let `SKLearnPredictor` be the last item, as we iterate through this list to find the
        # predictor for the given model artifact (based on the instance type of the estimator) it might
        # overlap with other predictors especially the ones with `sklearn.pipeline`
        self._artifact_predictors = [
            KerasPredictor(),
            XGBoostPredictor(),
            PyTorchPredictor(),
            SKLearnPredictor(),
            ONNXPredictor(),
        ]
        self._predictor_to_use = None
        self._custom_hooks = {hook: None for hook in CustomHooks.ALL_PREDICT_FIT_CHAT_STRUCTURED}
        self._model = None
        self._model_dir = model_dir
        self._target_type = target_type

        # New custom task class and instance loaded from custom.py
        self._custom_task_class = None
        self._custom_task_class_instance = None
        self._mod_pipeline = None

        if target_type in (
            TargetType.TEXT_GENERATION,
            TargetType.VECTOR_DATABASE,
            TargetType.AGENTIC_WORKFLOW,
        ):
            self._target_name = os.environ.get("TARGET_NAME")
            if not self._target_name:
                raise ValueError(
                    "Unexpected empty target name for text generation, "
                    "vector database, or agentic workflow target."
                )
            # Instrument http clients in order to get nice traces from moderation library. We are
            # doing this here because moderation library is loaded before custom.py.
            try:
                from opentelemetry.instrumentation.requests import RequestsInstrumentor

                RequestsInstrumentor().instrument()
            except (ImportError, ModuleNotFoundError):
                msg = """Instrumentation for requests is not loaded, make sure appropriate
                packages are installed:

                pip install opentelemetry-instrumentation-requests
                """
            try:
                from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

                AioHttpClientInstrumentor().instrument()
            except (ImportError, ModuleNotFoundError):
                msg = """Instrumentation for aiottp is not loaded, make sure appropriate
                packages are installed:

                pip install opentelemetry-instrumentation-aiohttp-client
                """
                self._logger.warning(msg)
            self._load_moderation_hooks(model_dir)
        else:
            self._target_name = None

    def _load_moderation_hooks(self, model_dir):
        try:
            mod_module = __import__(MODERATIONS_HOOK_MODULE, fromlist=[MODERATIONS_LIBRARY_PACKAGE])
            self._logger.info(
                f"Detected {mod_module.__name__} in {mod_module.__file__}.. trying to load hooks"
            )
            # use the 'moderation_pipeline_factory()' to determine if moderations has integrated pipeline
            if hasattr(mod_module, "moderation_pipeline_factory"):
                self._mod_pipeline = mod_module.moderation_pipeline_factory(
                    self._target_type.value, model_dir=str(model_dir)
                )
            else:
                self._logger.warning(f"No support of {self._target_type} target in moderations.")

        except ImportError as e:
            self._logger.warning(
                f"Could not load moderation hooks: {e}, moderation will be disabled"
            )
            # Just log that no moderation info present

    def _log_and_raise_final_error(self, exc: Exception, message: str) -> NoReturn:
        self._logger.exception(f"{message} Exception: {exc!r}")
        raise DrumPythonModelAdapterError(f"{message} Exception: {exc!r}")

    def has_custom_hook(self, hook_type: CustomHooks):
        return self._custom_hooks.get(hook_type, None) is not None

    @property
    def is_custom_task_class(self):
        """
        Returns
        -------
        True if the code is using the CustomTask class interface. False if it's using the legacy drum hook interface.
        """
        return self._custom_task_class is not None

    @staticmethod
    def _apply_sklearn_transformer(data, model):
        try:
            transformed = model.transform(data)
            if issparse(transformed):
                output_data = pd.DataFrame.sparse.from_spmatrix(transformed)
            else:
                output_data = pd.DataFrame(transformed)
        except Exception as e:
            raise type(e)("Couldn't naively apply transformer:" " {}".format(e)).with_traceback(
                sys.exc_info()[2]
            ) from None

        return output_data

    def _load_custom_hooks_for_new_drum(self, custom_module):
        # use that instance to score
        custom_task_class = getattr(custom_module, CUSTOM_PY_CLASS_NAME)

        if issubclass(custom_task_class, CustomTaskInterface):
            self._custom_task_class = custom_task_class
            self._logger.debug("Hooks loaded: {}".format(self._custom_hooks))

        else:
            raise DrumCommonException(
                "The CustomTask class must inherit from the CustomTaskInterface"
            )

    def _load_custom_hooks_for_legacy_drum(self, custom_module):
        if self._target_type == TargetType.UNSTRUCTURED:
            for hook in CustomHooks.ALL_PREDICT_UNSTRUCTURED:
                self._custom_hooks[hook] = getattr(custom_module, hook, None)

            if self._custom_hooks[CustomHooks.SCORE_UNSTRUCTURED] is None:
                raise DrumCommonException(
                    "In '{}' mode hook '{}' must be provided.".format(
                        TargetType.UNSTRUCTURED.value,
                        CustomHooks.SCORE_UNSTRUCTURED,
                    )
                )
        else:
            for hook in CustomHooks.ALL_PREDICT_FIT_CHAT_STRUCTURED:
                self._custom_hooks[hook] = getattr(custom_module, hook, None)

        if self._custom_hooks.get(CustomHooks.INIT):
            # noinspection PyCallingNonCallable
            self._custom_hooks[CustomHooks.INIT](code_dir=self._model_dir)

        self._logger.debug("Hooks loaded: {}".format(self._custom_hooks))

    def load_custom_hooks(self):
        custom_file_paths = list(Path(self._model_dir).rglob("{}.py".format(CUSTOM_FILE_NAME)))
        if len(custom_file_paths) > 1:
            raise RuntimeError("Found too many custom hook files: {}".format(custom_file_paths))

        if len(custom_file_paths) == 0:
            self._logger.info(
                "No {}.py file detected in {}".format(CUSTOM_FILE_NAME, self._model_dir)
            )
            return

        custom_file_path = custom_file_paths[0]
        self._logger.info("Detected {} .. trying to load hooks".format(custom_file_path))
        sys.path.insert(0, os.path.dirname(custom_file_path))

        try:
            custom_module = __import__(CUSTOM_FILE_NAME)
            if getattr(custom_module, CUSTOM_PY_CLASS_NAME, None):
                self._load_custom_hooks_for_new_drum(custom_module)
            else:
                self._load_custom_hooks_for_legacy_drum(custom_module)

        except ImportError as e:
            self._logger.error("Could not load hooks: {}".format(e))
            raise DrumCommonException(
                "\n\n{}\n"
                "Failed loading hooks from [{}] : {}".format(RUNNING_LANG_MSG, custom_file_path, e)
            )

    def _load_model_from_artifact_for_legacy_drum(self, skip_predictor_lookup=False):
        if self._custom_hooks[CustomHooks.LOAD_MODEL]:
            self._model = self._load_model_via_hook()
        else:
            model_artifact_file = self._detect_model_artifact_file()
            self._model = self._load_via_predictors(model_artifact_file)

        # If a score or chat hook is not given we need to find a predictor that can handle this model
        if (
            self._target_type not in [TargetType.UNSTRUCTURED, TargetType.TRANSFORM]
            and not self._custom_hooks[CustomHooks.SCORE]
            and not self._custom_hooks[CustomHooks.CHAT]
            and not skip_predictor_lookup
        ):
            self._find_predictor_to_use()

        if (
            self._target_type == TargetType.TRANSFORM
            and not self._custom_hooks[CustomHooks.TRANSFORM]
            # don't require transform hook if sklearn transformer
            and "sklearn" not in str(type(self._model))
        ):
            raise DrumCommonException(
                "A transform task requires a user-defined transform hook "
                "for non-sklearn transformers"
            )

        return self._model

    def load_model_from_artifact(
        self,
        user_secrets_mount_path: Optional[str] = None,
        user_secrets_prefix: Optional[str] = None,
        skip_predictor_lookup=False,
    ):
        """
        Load the serialized model from its artifact.
        Returns
        -------
        Any
            The deserialized model
        Raises
        ------
        DrumCommonException if model loading failed.
        """
        if self.is_custom_task_class:
            self._custom_task_class_instance = self._custom_task_class.load(self._model_dir)
            secrets = load_secrets(user_secrets_mount_path, user_secrets_prefix)
            patch_outputs_to_scrub_secrets(secrets.values())
            self._custom_task_class_instance.secrets = secrets
            return self._custom_task_class_instance

        else:
            return self._load_model_from_artifact_for_legacy_drum(skip_predictor_lookup)

    def _load_model_via_hook(self):
        self._logger.debug("Load model hook will be used to load the model")
        # noinspection PyCallingNonCallable

        try:
            model = self._custom_hooks[CustomHooks.LOAD_MODEL](self._model_dir)
        except Exception as exc:
            self._log_and_raise_final_error(exc, "'load_model' hook failed to load the model.")

        if model is None:
            raise DrumCommonException("'load_model' hook failed to load model, None is returned.")

        self._logger.debug("Model was successfully loaded by load hook")
        return model

    def _detect_model_artifact_file(self):
        # No model was loaded - so there is no local hook - so we are using our artifact predictors
        all_supported_extensions = set(p.artifact_extension for p in self._artifact_predictors)
        all_supported_extensions = list(sorted(all_supported_extensions))
        self._logger.debug("Supported suffixes: {}".format(all_supported_extensions))
        model_artifact_file = None

        files_list = sorted(os.listdir(self._model_dir))
        files_list_str = " | ".join(files_list)
        for filename in files_list:
            path = os.path.join(self._model_dir, filename)
            if os.path.isdir(path):
                continue

            if DrumUtils.endswith_extension_ignore_case(filename, all_supported_extensions):
                if model_artifact_file:
                    raise DrumCommonException(
                        "\n\n{}\n"
                        "Multiple serialized model files found. Remove extra artifacts "
                        "or overwrite custom.load_model()\n"
                        "List of retrieved files are: {}".format(RUNNING_LANG_MSG, files_list_str)
                    )
                model_artifact_file = path

        if not model_artifact_file:
            raise DrumCommonException(
                "\n\n{}\n"
                "Could not find model artifact file in: {} supported by default predictors.\n"
                "They support filenames with the following extensions {}.\n"
                "If your artifact is not supported by default predictor, implement custom.load_model() hook.\n"
                "List of retrieved files are: {}".format(
                    RUNNING_LANG_MSG, self._model_dir, all_supported_extensions, files_list_str
                )
            )

        self._logger.debug("model_artifact_file: {}".format(model_artifact_file))
        return model_artifact_file

    def _load_via_predictors(self, model_artifact_file):
        model = None
        pred_that_support_artifact = []
        for pred in self._artifact_predictors:
            if pred.is_artifact_supported(model_artifact_file):
                pred_that_support_artifact.append(pred)

            if pred.can_load_artifact(model_artifact_file):
                try:
                    model = pred.load_model_from_artifact(model_artifact_file)
                except Exception as exc:
                    self._log_and_raise_final_error(
                        exc, "Could not load model from the artifact file."
                    )
                break

        if model is None:
            if len(pred_that_support_artifact) > 0:
                framework_err = """
                    The following frameworks support this model artifact
                    but could not load the model. Check if requirements are missing
                """

                for pred in pred_that_support_artifact:
                    framework_err += "Framework: {}, requirements: {}".format(
                        pred.name, pred.framework_requirements()
                    )

                raise DrumCommonException(textwrap.dedent(framework_err))
            else:
                raise DrumCommonException(
                    "\n\n{}\n"
                    "Could not load model from artifact file {}."
                    " No builtin support for this model was detected".format(
                        RUNNING_LANG_MSG, model_artifact_file
                    )
                )

        self._model = model
        return model

    def _find_predictor_to_use(self):
        # TODO: RAPTOR-4014 need to handle transformers when we don't require transform hook for sklearn pipelines
        self._predictor_to_use = None
        for pred in self._artifact_predictors:
            if pred.can_use_model(self._model):
                self._predictor_to_use = pred
                break

        if not self._predictor_to_use and not self._custom_hooks[CustomHooks.SCORE]:
            raise DrumCommonException(
                "\n\n{}\n"
                "Could not find any framework to handle loaded model and a {} "
                "hook is not provided".format(RUNNING_LANG_MSG, CustomHooks.SCORE)
            )

        self._logger.debug("Predictor to use: {}".format(self._predictor_to_use.name))

    @staticmethod
    def _validate_data(to_validate, hook):
        if hook in {CustomHooks.SCORE, CustomHooks.TRANSFORM}:
            if not isinstance(to_validate, pd.DataFrame):
                raise ValueError(
                    f"{hook} must return a dataframe, but received {type(to_validate)}"
                )
            if len(to_validate.shape) != 2:
                raise ValueError(
                    f"{hook} must return a dataframe of dim 2, but received one with dims {to_validate.shape}"
                )

    @staticmethod
    def _validate_transform_rows(data, output_data):
        if data.shape[0] != output_data.shape[0]:
            raise ValueError(
                "Transformation resulted in different number of rows than original data"
            )

    @property
    def supported_payload_formats(self):
        formats = SupportedPayloadFormats()
        formats.add(PayloadFormat.CSV)
        formats.add(PayloadFormat.MTX)
        return formats

    def model_info(self):
        return {
            ModelInfoKeys.PREDICTOR: None
            if self._predictor_to_use is None
            else self._predictor_to_use.name,
        }

    def load_data(self, binary_data, mimetype, try_hook=True, sparse_colnames=None):
        if self._custom_hooks.get(CustomHooks.READ_INPUT_DATA) and try_hook:
            try:
                data = self._custom_hooks[CustomHooks.READ_INPUT_DATA](binary_data)
            except Exception as exc:
                self._log_and_raise_final_error(
                    exc, "Model 'read_input_data' hook failed to read input data."
                )
        else:
            data = StructuredInputReadUtils.read_structured_input_data_as_df(
                binary_data, mimetype, sparse_colnames
            )

        return data

    def preprocess(self, data, model=None):
        """
        Preprocess data and then pass on to predict method.
        Loads data, either with read hook or built-in method, and applies transform hook if present

        Parameters
        ----------
        model: Any
            The model
        Returns
        -------
        pd.DataFrame
        """
        if self._custom_hooks.get(CustomHooks.TRANSFORM):
            try:
                output_data = self._custom_hooks[CustomHooks.TRANSFORM](data, model)

            except Exception as exc:
                self._log_and_raise_final_error(
                    exc, "Model 'transform hook' failed to transform dataset."
                )

            self._validate_data(output_data, CustomHooks.TRANSFORM)

        else:
            output_data = data

        return output_data

    def _transform_legacy_drum(self, data, target_data, model, **kwargs):
        if self._custom_hooks.get(CustomHooks.TRANSFORM):
            try:
                transform_hook = self._custom_hooks[CustomHooks.TRANSFORM]
                transform_params = signature(transform_hook).parameters
                if len(transform_params) == 3:
                    transform_out = transform_hook(data, model, target_data)
                elif len(transform_params) == 2:
                    transform_out = transform_hook(data, model)
                else:
                    raise ValueError(
                        "Transform hook must take 2 or 3 arguments; "
                        "hook provided takes {}".format(len(transform_params))
                    )
                if type(transform_out) == tuple:
                    raise DrumTransformException(
                        "Transformation of the target variable is not supported by DRUM."
                    )
                output_data = transform_out
                output_target = target_data

            except Exception as exc:
                self._log_and_raise_final_error(
                    exc, "Model 'transform hook' failed to transform dataset."
                )
            self._validate_data(output_data, CustomHooks.TRANSFORM)
            self._validate_transform_rows(output_data, data)
            if output_target is not None:
                self._validate_transform_rows(output_target, target_data)
            return output_data, output_target
        elif "sklearn" in str(type(model)):
            # we don't touch y if user doesn't pass a hook
            return self._apply_sklearn_transformer(data, model), target_data
        else:
            raise ValueError(
                "Transform hook must be implemented for custom transforms, "
                "for non-sklearn transformer."
            )

    def transform(self, model=None, **kwargs):
        """
        Standalone transform method, only used for custom transforms.

        Parameters
        ----------
        model: Any
            The model
        Returns
        -------
        pd.DataFrame
        """
        # TODO: this is very similar to predict, could be refactored
        data = self.load_data(
            binary_data=kwargs.get(StructuredDtoKeys.BINARY_DATA),
            mimetype=kwargs.get(StructuredDtoKeys.MIMETYPE),
            sparse_colnames=kwargs.get(StructuredDtoKeys.SPARSE_COLNAMES),
        )

        target_binary_data = kwargs.get(StructuredDtoKeys.TARGET_BINARY_DATA)
        target_data = None

        if target_binary_data:
            target_data = self.load_data(
                target_binary_data, kwargs.get(StructuredDtoKeys.TARGET_MIMETYPE), try_hook=False
            )

        if self.is_custom_task_class:
            try:
                output_data = self._custom_task_class_instance.transform(data)
                self._validate_data(output_data, CustomHooks.TRANSFORM)
                self._validate_transform_rows(output_data, data)
                output_target = target_data
            except Exception as exc:
                self._log_and_raise_final_error(
                    exc, "Model 'transform' hook failed to transform dataset."
                )
        else:
            output_data, output_target = self._transform_legacy_drum(
                data, target_data, model, **kwargs
            )

        return output_data, output_target

    def has_read_input_data_hook(self):
        return self._custom_hooks.get(CustomHooks.READ_INPUT_DATA) is not None

    def _predict_new_drum(self, data, **kwargs) -> RawPredictResponse:
        try:
            if self._target_type in {TargetType.BINARY, TargetType.MULTICLASS}:
                predictions_df = self._custom_task_class_instance.predict_proba(data, **kwargs)
            else:
                predictions_df = self._custom_task_class_instance.predict(data, **kwargs)
            self._validate_data(predictions_df, CustomHooks.SCORE)
            return RawPredictResponse(predictions_df.values, predictions_df.columns)
        except Exception as exc:
            self._log_and_raise_final_error(exc, "Model 'score' hook failed to make predictions.")

    def _predict_legacy_drum(self, data, model, **kwargs) -> RawPredictResponse:
        positive_class_label = kwargs.get(POSITIVE_CLASS_LABEL_ARG_KEYWORD)
        negative_class_label = kwargs.get(NEGATIVE_CLASS_LABEL_ARG_KEYWORD)
        if self._target_type in {TargetType.BINARY, TargetType.MULTICLASS}:
            request_labels = get_request_labels(
                kwargs.get(CLASS_LABELS_ARG_KEYWORD),
                positive_class_label,
                negative_class_label,
            )
        else:
            request_labels = None

        if request_labels is not None:
            assert all(isinstance(label, str) for label in request_labels)
        extra_model_output = None
        score_fn = self._custom_hooks.get(CustomHooks.SCORE)
        if score_fn:
            try:
                if self._mod_pipeline:
                    predictions_df = self._mod_pipeline.score(data, model, score_fn, **kwargs)
                    if self._target_name not in predictions_df:
                        predictions_df.rename(
                            columns={"completion": self._target_name}, inplace=True
                        )
                else:
                    # noinspection PyCallingNonCallable
                    predictions_df = score_fn(data, model, **kwargs)
            except Exception as exc:
                self._log_and_raise_final_error(
                    exc, "Model 'score' hook failed to make predictions."
                )
            self._validate_data(predictions_df, CustomHooks.SCORE)
            predictions_df, extra_model_output = self._split_to_predictions_and_extra_model_output(
                predictions_df, request_labels
            )
            predictions = predictions_df.values
            model_labels = predictions_df.columns
        else:
            try:
                predictions, model_labels = self._predictor_to_use.predict(data, model, **kwargs)
            except Exception as exc:
                self._log_and_raise_final_error(exc, "Failure when making predictions.")

        if self._custom_hooks.get(CustomHooks.POST_PROCESS):
            # This is probably not great, a user is likely to want unmarshalled predictions in the
            # post-process hook.
            predictions = marshal_predictions(
                request_labels=request_labels,
                predictions=predictions,
                target_type=self._target_type,
                model_labels=model_labels,
            )
            try:
                # noinspection PyCallingNonCallable
                predictions_df = self._custom_hooks[CustomHooks.POST_PROCESS](predictions, model)
            except Exception as exc:
                self._log_and_raise_final_error(
                    exc, "Model 'post_process' hook failed to post-process predictions."
                )
            if not isinstance(predictions_df, pd.DataFrame):
                raise ValueError(
                    f"Output of post_process hook must be a dataframe, not a {type(predictions_df)}"
                )
            predictions = predictions_df.values
            model_labels = predictions_df.columns

        return RawPredictResponse(predictions, model_labels, extra_model_output)

    def _split_to_predictions_and_extra_model_output(self, result_df, request_labels):
        if request_labels:
            # It's Binary or Classification model
            if len(result_df.columns) > len(request_labels):
                predictions_df, extra_model_output = extract_additional_columns(
                    result_df, request_labels
                )
            else:
                extra_model_output = None
                predictions_df = result_df
        else:
            if len(result_df.columns) > 1:
                if self._target_name:
                    target_column = self._target_name
                    if target_column not in result_df:
                        # Try removing quotation marks if exist
                        if (
                            len(target_column) >= 2
                            and target_column[0] == '"'
                            and target_column[-1] == '"'
                        ):
                            target_column = target_column[1:-1]
                else:
                    target_column = PRED_COLUMN
                extra_model_output = result_df.drop(columns=[target_column])
                predictions_df = result_df[[target_column]]
            else:
                extra_model_output = None
                predictions_df = result_df
        return predictions_df, extra_model_output

    def predict(self, model=None, **kwargs) -> RawPredictResponse:
        """
        Makes predictions against the model using the custom predict
        Parameters
        ----------
        model: Any
            The model
        kwargs
        Returns
        -------
        RawPredictResponse
        """
        data = self.load_data(
            binary_data=kwargs.get(StructuredDtoKeys.BINARY_DATA),
            mimetype=kwargs.get(StructuredDtoKeys.MIMETYPE),
            sparse_colnames=kwargs.get(StructuredDtoKeys.SPARSE_COLNAMES),
        )

        data = self.preprocess(data, model)

        if self.is_custom_task_class:
            return self._predict_new_drum(data, **kwargs)
        else:
            return self._predict_legacy_drum(data, model, **kwargs)

    @staticmethod
    def _validate_unstructured_predictions(unstructured_response):
        # response can be either str/bytes or tuple
        # normalize to tuple
        single_input_value = False
        if not isinstance(unstructured_response, tuple):
            single_input_value = True
            unstructured_response = (unstructured_response, None)

        if len(unstructured_response) != 2:
            raise ValueError(
                "In unstructured mode predictions of type tuple must have length = 2, but received length = {}".format(
                    len(unstructured_response)
                )
            )

        data, kwargs = unstructured_response

        if not isinstance(data, (bytes, str, type(None))) or not isinstance(
            kwargs, (dict, type(None))
        ):
            if single_input_value:
                error_msg = "In unstructured mode single return value can be of type str/bytes, but received {}".format(
                    type(data)
                )
            else:
                error_msg = "In unstructured mode tuple return value must be of type (str/bytes, dict) but received ({}, {})".format(
                    type(data), type(kwargs)
                )
            raise ValueError(error_msg)

    def predict_unstructured(self, model, data, **kwargs):
        predictions = self._custom_hooks.get(CustomHooks.SCORE_UNSTRUCTURED)(model, data, **kwargs)
        PythonModelAdapter._validate_unstructured_predictions(predictions)
        return predictions

    def chat(self, completion_create_params, model, association_id, **kwargs):
        chat_fn = self._custom_hooks.get(CustomHooks.CHAT)
        if self._mod_pipeline:
            return self._mod_pipeline.chat(completion_create_params, model, chat_fn, association_id)

        chat_fn_params = signature(chat_fn).parameters
        if len(chat_fn_params) > 2:
            return chat_fn(completion_create_params, model, **kwargs)
        else:
            return chat_fn(completion_create_params, model)

    def get_supported_llm_models(self, model):
        """
        Return list of LLM models supported by this custom model.
        Usually, the trigger is a call to OpenAI models.list() (/v1/models, or /models)

        If custom.py defines get_supported_llm_models(), use its returned list.
        If that hook is not defined, return the model defined in LLM_ID runtime parameter.
        If neither is present, return an empty list.

        Parameters
        ----------
        model

        Returns
        -------
        Dict matching JSON structure of GET https://api.openai.com/v1/models response:
        {"object": "list", "data": [{id, object, created, owned_by}, ...]}
        """
        result = {"object": "list", "data": []}
        if self._custom_hooks.get(CustomHooks.GET_SUPPORTED_LLM_MODELS_LIST):
            self._logger.debug("get_supported_llm_models: custom.py defines the hook")
            response = self._custom_hooks.get(CustomHooks.GET_SUPPORTED_LLM_MODELS_LIST)(model)
            for model in response:
                if is_openai_model(model):
                    result["data"].append(model.to_dict())
        else:
            # defining the hook overrides built-in behavior and is optional
            self._logger.debug("get_supported_llm_models: hook is not defined")
            llm_id_key = "LLM_ID"
            if RuntimeParameters.has(llm_id_key):
                self._logger.debug("get_supported_llm_models: returning LLM_ID")
                llm_id = RuntimeParameters.get(llm_id_key)
                result["data"].append(
                    {
                        "id": llm_id,
                        "object": "model",
                        "created": 1735689600,  # Jan. 1, 2025
                        "owned_by": "DataRobot",
                    }
                )
            else:
                self._logger.debug("get_supported_llm_models: returning empty list")

        return result

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        output_dir: str,
        class_order: Optional[list],
        row_weights: Optional[pd.Series],
        parameters: Optional[dict],
        user_secrets_mount_path: Optional[str],
        user_secrets_prefix: Optional[str],
    ) -> "AbstractModelAdapter":
        if self.is_custom_task_class:
            with reroute_stdout_to_stderr():
                try:
                    self._custom_task_class_instance = self._custom_task_class()
                    with secrets_injection_context(
                        self._custom_task_class_instance,
                        user_secrets_mount_path,
                        user_secrets_prefix,
                    ):
                        self._custom_task_class_instance.fit(
                            X=X,
                            y=y,
                            output_dir=output_dir,
                            class_order=class_order,
                            row_weights=row_weights,
                            parameters=parameters,
                        )

                    try:
                        self._custom_task_class_instance.save(self._model_dir)
                    except DrumSerializationError:
                        raise
                    except Exception:
                        raise DrumSerializationError(
                            "An error occurred when saving your custom task. "
                            "Ensure all variables stored on self are pickle-able or excluded when saving"
                        )
                except AttributeError:
                    raise DrumCommonException(
                        "There appears to be an issue with your fit method OR it is missing entirely. "
                        "Please verify that that the fit method in custom.py is present and runs without errors."
                    )
        else:
            if self._target_type != TargetType.TRANSFORM:
                X = self.preprocess(X)
            with reroute_stdout_to_stderr():
                if self._custom_hooks.get(CustomHooks.FIT):
                    self._custom_hooks[CustomHooks.FIT](
                        X=X,
                        y=y,
                        output_dir=output_dir,
                        class_order=class_order,
                        row_weights=row_weights,
                        parameters=parameters,
                    )
                else:
                    hooks = [
                        "{}: {}".format(hook, fn is not None)
                        for hook, fn in self._custom_hooks.items()
                    ]
                    raise DrumCommonException(
                        "\n\n{}\n"
                        "\nfit() method must be implemented in a file named 'custom.py' in the provided code_dir: '{}' \n"
                        "Here is a list of files in this dir. {}\n"
                        "Here are the hooks your custom.py file has: {}".format(
                            RUNNING_LANG_MSG,
                            self._model_dir,
                            os.listdir(self._model_dir)[:100],
                            hooks,
                        )
                    )
        return self
