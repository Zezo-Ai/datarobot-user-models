"""
Copyright 2021 DataRobot, Inc. and its affiliates.
All rights reserved.
This is proprietary source code of DataRobot, Inc. and its affiliates.
Released under the terms of DataRobot Tool and Utility Agreement.
"""
import pandas as pd
import logging

from cgi import FieldStorage
from io import BytesIO, StringIO

from scipy.io import mmwrite, mmread
from scipy.sparse import issparse
from scipy.sparse import csr_matrix

from datarobot_drum.drum.enum import X_FORMAT_KEY, X_TRANSFORM_KEY


def filter_urllib3_logging():
    """Filter header errors from urllib3 due to a urllib3 bug."""
    urllib3_logger = logging.getLogger("urllib3.connectionpool")
    if not any(isinstance(x, NoHeaderErrorFilter) for x in urllib3_logger.filters):
        urllib3_logger.addFilter(NoHeaderErrorFilter())


class NoHeaderErrorFilter(logging.Filter):
    """Filter out urllib3 Header Parsing Errors due to a urllib3 bug."""

    def filter(self, record):
        """Filter out Header Parsing Errors."""
        return "Failed to parse headers" not in record.getMessage()


def is_sparse(df):
    return hasattr(df, "sparse") or issparse(df.iloc[0].values[0])


def validate_and_convert_column_names_for_serialization(df):
    """
    Parameters
    ----------
    df: pd.DataFrame

    Returns
    -------
    pd.DataFrame
        DataFrame with columns that can be properly serialized
    """
    columns = df.columns.values

    # Strip all outer whitespace
    columns = [str(colname).strip() for colname in columns]

    # Replace newlines
    columns = [colname.replace("\n", "\\n") for colname in columns]

    # Remove any empty colnames
    columns = [colname for colname in columns if colname]

    if len(columns) != df.shape[1]:
        raise ValueError(
            "Column name serialization check failed, deserializing column names resulted in {}, expected {}\n"
            "Ensure there are no column names made up entirely of whitespace".format(
                len(columns), df.shape[1]
            )
        )

    df.columns = columns
    return df


def make_csv_payload(df):
    df = validate_and_convert_column_names_for_serialization(df)

    s_buf = StringIO()
    df.to_csv(s_buf, index=False, lineterminator="\r\n")
    # Remove the last 2 characters (\r\n) from the string.  This is required for R
    # to properly load a single column dataset from a string.
    return s_buf.getvalue()[:-2].encode("utf-8")


def read_csv_payload(response_dict, transform_key):
    bytes = response_dict[transform_key]
    return pd.read_csv(BytesIO(bytes))


def make_mtx_payload(df):
    sparse_mat = validate_and_convert_column_names_for_serialization(df)
    colnames = df.columns.values
    sink = BytesIO()
    mmwrite(sink, sparse_mat.sparse.to_coo())
    column_payload = "\n".join(str(colname) for colname in colnames)

    return sink.getvalue(), column_payload


def read_mtx_payload(response_dict, transform_key):
    bytes = response_dict[transform_key]
    sparse_mat = mmread(BytesIO(bytes))
    return csr_matrix(sparse_mat)


def parse_multi_part_response(response):
    parsed_response = {}
    fs = FieldStorage(
        fp=BytesIO(response.content),
        headers=response.headers,
        environ={
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": response.headers["Content-Type"],
        },
    )
    for child in fs.list:
        key = child.name
        value = child.file.read()
        parsed_response.update({key: value})

    return parsed_response


def read_x_data_from_response(response):
    def _sparse(data, key):
        return pd.DataFrame.sparse.from_spmatrix(read_mtx_payload(data, key))

    reader = {
        "sparse": _sparse,
        "csv": read_csv_payload,
    }
    data = parse_multi_part_response(response)
    return reader[data[X_FORMAT_KEY]](data, X_TRANSFORM_KEY)
