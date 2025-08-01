"""
Copyright 2021 DataRobot, Inc. and its affiliates.
All rights reserved.
This is proprietary source code of DataRobot, Inc. and its affiliates.
Released under the terms of DataRobot Tool and Utility Agreement.
"""
import logging

import werkzeug
from flask import request, Response, stream_with_context
from requests_toolbelt import MultipartEncoder

from datarobot_drum.drum.enum import (
    PredictionServerMimetypes,
    PRED_COLUMN,
    SPARSE_COLNAMES,
    TargetType,
    UnstructuredDtoKeys,
    X_TRANSFORM_KEY,
    Y_TRANSFORM_KEY,
)
from datarobot_drum.drum.exceptions import DrumSchemaValidationException
from datarobot_drum.drum.server import (
    HTTP_200_OK,
    HTTP_404_NOT_FOUND,
    HTTP_422_UNPROCESSABLE_ENTITY,
)
from datarobot_drum.drum.utils.structured_input_read_utils import StructuredInputReadUtils
from datarobot_drum.drum.root_predictors.chat_helpers import is_streaming_response
from datarobot_drum.drum.root_predictors.deployment_config_helpers import (
    build_pps_response_json_str,
)
from datarobot_drum.drum.root_predictors.transform_helpers import (
    is_sparse,
    make_csv_payload,
    make_mtx_payload,
)
from datarobot_drum.drum.root_predictors.unstructured_helpers import (
    _resolve_incoming_unstructured_data,
    _resolve_outgoing_unstructured_data,
)


class PredictMixin:
    """
    This class implements predict flow shared by PredictionServer and UwsgiServing classes.
    This flow assumes endpoints implemented using Flask.

    """

    @staticmethod
    def _log_if_possible(logger, log_level, message):
        if logger is not None:
            logger.log(log_level, message)

    @staticmethod
    def _validate_content_type_header(header):
        ret_mimetype, content_type_params_dict = werkzeug.http.parse_options_header(header)
        ret_charset = content_type_params_dict.get("charset")
        return ret_mimetype, ret_charset

    @staticmethod
    def _fetch_data_from_request(file_key, logger=None):
        filestorage = request.files.get(file_key)

        charset = None
        if filestorage is not None:
            binary_data = filestorage.stream.read()
            mimetype = StructuredInputReadUtils.resolve_mimetype_by_filename(filestorage.filename)

            if logger is not None:
                logger.debug(
                    "Filename provided under {} key: {}".format(file_key, filestorage.filename)
                )

        # TODO: probably need to return empty response in case of empty request
        elif len(request.data) and file_key == "X":
            binary_data = request.data
            mimetype, charset = PredictMixin._validate_content_type_header(request.content_type)
        else:
            wrong_key_error_message = (
                "Samples should be provided as: "
                "  - a csv or mtx under `{}` form-data param key."
                "  - binary data".format(file_key)
            )
            if logger is not None:
                logger.error(wrong_key_error_message)
            raise ValueError(wrong_key_error_message)
        return binary_data, mimetype, charset

    @staticmethod
    def _fetch_additional_files_from_request(file_key, logger=None):
        filestorage = request.files.get(file_key)

        if filestorage is not None:
            binary_data = filestorage.stream.read()

            if logger is not None:
                logger.debug(
                    "Filename provided under {} key: {}".format(file_key, filestorage.filename)
                )
            return binary_data
        return None

    def _get_sparse_column_names(self, logger):
        sparse_column_data = self._fetch_additional_files_from_request(
            SPARSE_COLNAMES, logger=logger
        )
        if sparse_column_data:
            return StructuredInputReadUtils.read_sparse_column_data_as_list(sparse_column_data)
        return None

    @staticmethod
    def _stream_openai_chunks(stream):
        for chunk in stream:
            chunk_json = chunk.to_json(indent=None)
            for line in chunk_json.splitlines():
                yield f"data: {line}\n"
            yield "\n"

        yield "data: [DONE]\n\n"

    def _check_mimetype_support(self, mimetype):
        # TODO: self._predictor.supported_payload_formats is property so gets initialized on every call, make it a method?
        mimetype_supported = self._predictor.supported_payload_formats.is_mimetype_supported(
            mimetype
        )
        if not mimetype_supported and not self._predictor.has_read_input_data_hook():
            error_message = (
                "ERROR: payload format `{}` is not supported by predictor/transformer. ".format(
                    mimetype
                )
                + "Make DRUM support the format or implement `read_input_data` hook to read the data. "
            )
            return {"message": error_message}, HTTP_422_UNPROCESSABLE_ENTITY
        return None

    def _do_predict_structured(self, logger=None):
        response_status = HTTP_200_OK
        try:
            binary_data, mimetype, charset = self._fetch_data_from_request("X", logger=logger)
            sparse_column_names = self._get_sparse_column_names(logger=logger)

            mimetype_support_error_response = self._check_mimetype_support(mimetype)
            if mimetype_support_error_response is not None:
                return mimetype_support_error_response
        except ValueError as e:
            response_status = HTTP_422_UNPROCESSABLE_ENTITY
            return {"message": "ERROR: " + str(e)}, response_status

        predict_response = self._predictor.predict(
            binary_data=binary_data,
            mimetype=mimetype,
            charset=charset,
            sparse_colnames=sparse_column_names,
        )

        if self._target_type == TargetType.UNSTRUCTURED:
            response = predict_response.predictions
        else:
            if self._target_type not in (
                TargetType.TEXT_GENERATION,
                TargetType.GEO_POINT,
                TargetType.VECTOR_DATABASE,
                TargetType.AGENTIC_WORKFLOW,
            ):
                # float32 is not JSON serializable, so cast to float, which is float64
                predict_response.predictions = predict_response.predictions.astype("float")
            if self._deployment_config is not None:
                response = build_pps_response_json_str(
                    predict_response, self._deployment_config, self._target_type
                )
            else:
                response = self._build_drum_response_json_str(predict_response)

        response = Response(response, mimetype=PredictionServerMimetypes.APPLICATION_JSON)

        return response, response_status

    @staticmethod
    def _build_drum_response_json_str(predict_response):
        out_data = predict_response.predictions
        extra_model_output = predict_response.extra_model_output
        if len(out_data.columns) == 1:
            out_data = out_data[PRED_COLUMN]
        # df.to_json() is much faster.
        # But as it returns string, we have to assemble final json using strings.
        predictions_json_str = out_data.to_json(orient="records")
        if extra_model_output is not None:
            # For best performance we use the 'split' orientation.
            extra_output_json_str = extra_model_output.to_json(orient="split")
            response = (
                "{"
                f'"predictions":{predictions_json_str},'
                f'"extraModelOutput":{extra_output_json_str}'
                "}"
            )
        else:
            response = f'{{"predictions":{predictions_json_str}}}'
        return response

    def _transform(self, logger=None):
        response_status = HTTP_200_OK

        try:
            feature_binary_data, feature_mimetype, feature_charset = self._fetch_data_from_request(
                "X", logger=logger
            )
            sparse_column_names = self._get_sparse_column_names(logger=logger)
            mimetype_support_error_response = self._check_mimetype_support(feature_mimetype)
            if mimetype_support_error_response is not None:
                return mimetype_support_error_response
        except ValueError as e:
            response_status = HTTP_422_UNPROCESSABLE_ENTITY
            return {"message": "ERROR: " + str(e)}, response_status

        try:
            if "y" in request.files.keys():
                try:
                    (
                        target_binary_data,
                        target_mimetype,
                        target_charset,
                    ) = self._fetch_data_from_request("y", logger=logger)
                    mimetype_support_error_response = self._check_mimetype_support(target_mimetype)
                    if mimetype_support_error_response is not None:
                        return mimetype_support_error_response
                except ValueError as e:
                    response_status = HTTP_422_UNPROCESSABLE_ENTITY
                    return {"message": "ERROR: " + str(e)}, response_status

                out_data, out_target = self._predictor.transform(
                    binary_data=feature_binary_data,
                    mimetype=feature_mimetype,
                    charset=feature_charset,
                    target_binary_data=target_binary_data,
                    target_mimetype=target_mimetype,
                    target_charset=target_charset,
                    sparse_colnames=sparse_column_names,
                )
            else:
                out_data, _ = self._predictor.transform(
                    binary_data=feature_binary_data,
                    mimetype=feature_mimetype,
                    charset=feature_charset,
                    sparse_colnames=sparse_column_names,
                )
                out_target = None
        except DrumSchemaValidationException as e:
            response_status = HTTP_422_UNPROCESSABLE_ENTITY
            return (
                {"message": "ERROR: " + str(e), "is_schema_validation_error": True},
                response_status,
            )

        # make output
        if is_sparse(out_data):
            target_payload = make_csv_payload(out_target) if out_target is not None else None
            feature_payload, colnames = make_mtx_payload(out_data)
            out_format = "sparse"
        else:
            feature_payload = make_csv_payload(out_data)
            target_payload = make_csv_payload(out_target) if out_target is not None else None
            out_format = "csv"

        out_fields = {
            "X.format": out_format,
            X_TRANSFORM_KEY: (
                X_TRANSFORM_KEY,
                feature_payload,
                PredictionServerMimetypes.APPLICATION_OCTET_STREAM,
            ),
        }

        if is_sparse(out_data):
            out_fields.update(
                {
                    SPARSE_COLNAMES: (
                        SPARSE_COLNAMES,
                        colnames,
                        PredictionServerMimetypes.APPLICATION_OCTET_STREAM,
                    )
                }
            )

        if target_payload is not None:
            out_fields.update(
                {
                    "y.format": "csv",
                    Y_TRANSFORM_KEY: (
                        Y_TRANSFORM_KEY,
                        target_payload,
                        PredictionServerMimetypes.APPLICATION_OCTET_STREAM,
                    ),
                }
            )

        m = MultipartEncoder(fields=out_fields)

        response = Response(m.to_string(), mimetype=m.content_type)

        return response, response_status

    def do_predict_structured(self, logger=None):
        wrong_target_type_error_message = (
            "This model has target type '{}', use the {{}} endpoint.".format(
                self._target_type.value
            )
        )

        return_error = False
        if self._target_type == TargetType.TRANSFORM:
            wrong_target_type_error_message = wrong_target_type_error_message.format("/transform/")
            return_error = True
        elif self._target_type == TargetType.UNSTRUCTURED:
            wrong_target_type_error_message = wrong_target_type_error_message.format(
                "/predictUnstructured/ or /predictionsUnstructured/"
            )
            return_error = True

        if return_error:
            if logger is not None:
                logger.error(wrong_target_type_error_message)
            return (
                {"message": "ERROR: " + wrong_target_type_error_message},
                HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return self._do_predict_structured(logger=logger)

    def do_predict_unstructured(self, logger=None):
        # LLMs can also serve as guard models where moderations library expects to interface via /predictUnstructured
        if self._target_type not in {TargetType.UNSTRUCTURED, TargetType.TEXT_GENERATION}:
            response_status = HTTP_422_UNPROCESSABLE_ENTITY
            wrong_target_type_error_message = (
                "This model has target type {}, "
                "use either /predict/ or /predictions/ endpoint.".format(self._target_type)
            )
            if logger is not None:
                logger.error(wrong_target_type_error_message)
            return {"message": "ERROR: " + wrong_target_type_error_message}, response_status

        response_status = HTTP_200_OK
        kwargs_params = {}

        data = request.get_data()
        mimetype, charset = PredictMixin._validate_content_type_header(request.content_type)

        data_binary_or_text, mimetype, charset = _resolve_incoming_unstructured_data(
            data,
            mimetype,
            charset,
        )
        kwargs_params[UnstructuredDtoKeys.MIMETYPE] = mimetype
        if charset is not None:
            kwargs_params[UnstructuredDtoKeys.CHARSET] = charset
        kwargs_params[UnstructuredDtoKeys.QUERY] = request.args
        kwargs_params[UnstructuredDtoKeys.HEADERS] = dict(request.headers)

        ret_data, ret_kwargs = self._predictor.predict_unstructured(
            data_binary_or_text, **kwargs_params
        )

        response_data, response_mimetype, response_charset = _resolve_outgoing_unstructured_data(
            ret_data, ret_kwargs
        )

        response = Response(response_data)

        if response_mimetype is not None:
            content_type = response_mimetype
            if response_charset is not None:
                content_type += "; charset={}".format(response_charset)
            response.headers["Content-Type"] = content_type

        return response, response_status

    def do_chat(self, logger=None):
        unsupported_chat_message = (
            "This model's chat interface was called, but chat is not supported."
        )
        undefined_chat_message = (
            "This model's chat interface was called, but chat() is not implemented."
        )
        # _predictor is a BaseLanguagePredictor attribute of PredictionServer;
        # see PredictionServer.__init__()
        if not self._predictor.supports_chat():
            if self._target_type in [TargetType.TEXT_GENERATION, TargetType.AGENTIC_WORKFLOW]:
                message = undefined_chat_message
            else:
                message = unsupported_chat_message
            self._log_if_possible(logger, logging.ERROR, message)
            return (
                {"message": "ERROR: " + message},
                HTTP_404_NOT_FOUND,
            )

        completion_create_params = request.json
        headers = request.headers

        result = self._predictor.chat(completion_create_params, headers=headers)
        if not is_streaming_response(result):
            response = result.to_dict()
        else:
            response = Response(
                stream_with_context(PredictMixin._stream_openai_chunks(result)),
                mimetype="text/event-stream",
            )

        return response, HTTP_200_OK

    def get_supported_llm_models(self, logger=None):
        if self._target_type != TargetType.TEXT_GENERATION:
            message = "get_supported_llm_models is supported only for TextGen models"
            self._log_if_possible(logger, logging.WARNING, message)
            return (
                {"message": "ERROR: " + message},
                HTTP_404_NOT_FOUND,
            )
        result = self._predictor.get_supported_llm_models()
        return result, HTTP_200_OK

    def do_transform(self, logger=None):
        if self._target_type != TargetType.TRANSFORM:
            endpoint = (
                "predictUnstructured" if self._target_type == TargetType.UNSTRUCTURED else "predict"
            )
            wrong_target_type_error_message = (
                "This model has target type {}, "
                "use the /{}/ endpoint.".format(self._target_type, endpoint)
            )
            if logger is not None:
                logger.error(wrong_target_type_error_message)
            response_status = HTTP_422_UNPROCESSABLE_ENTITY
            return {"message": "ERROR: " + wrong_target_type_error_message}, response_status

        return self._transform(logger=logger)

    def make_capabilities(self):
        return {
            "supported_payload_formats": {
                payload_format: format_version
                for payload_format, format_version in self._predictor.supported_payload_formats
            },
            "supported_methods": {"chat": self._predictor.supports_chat()},
        }
