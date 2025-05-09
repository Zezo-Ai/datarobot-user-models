"""
Copyright 2021 DataRobot, Inc. and its affiliates.
All rights reserved.
This is proprietary source code of DataRobot, Inc. and its affiliates.
Released under the terms of DataRobot Tool and Utility Agreement.
"""

"""
This example shows how to create a multiclass neural net with pytorch
"""
import logging
import os
import pickle
from typing import List, Optional, Any, Dict

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder
import torch

from preprocessing import dense_preprocessing_pipeline
from model_utils import build_classifier, train_classifier, save_torch_model


logger = logging.getLogger(__name__)


preprocessor = None


def fit(
    X: pd.DataFrame,
    y: pd.Series,
    output_dir: str,
    class_order: Optional[List[str]] = None,
    row_weights: Optional[np.ndarray] = None,
    **kwargs,
):
    """This hook MUST ALWAYS be implemented for custom tasks.

    This hook defines how DataRobot will train this task.
    DataRobot runs this hook when the task is being trained inside a blueprint.

    DataRobot will pass the training data, project target, and additional parameters based on the project
    and blueprint configuration as parameters to this function.

    As an output, this hook is expected to create an artifact containing a trained object,
    that is then used to score new data.

    Parameters
    ----------
    X: pd.DataFrame
        Training data that DataRobot passes when this task is being trained. Note that both the training data AND
        column (feature) names are passed
    y: pd.Series
        Project's target column.
    output_dir: str
        A path to the output folder (also provided in --output paramter of 'drum fit' command)
        The artifact [in this example - containing the trained sklearn pipeline]
        must be saved into this folder.
    class_order: Optional[List[str]]
        This indicates which class DataRobot considers positive or negative. E.g. 'yes' is positive, 'no' is negative.
        Class order will always be passed to fit by DataRobot for classification tasks,
        and never otherwise. When models predict, they output a likelihood of one class, with a
        value from 0 to 1. The likelihood of the other class is 1 - this likelihood.
        The first element in the class_order list is the name of the class considered negative inside DR's project,
        and the second is the name of the class that is considered positive
    row_weights: Optional[np.ndarray]
        An array of non-negative numeric values which can be used to dictate how important
        a row is. Row weights is only optionally used, and there will be no filtering for which
        custom models support this. There are two situations when values will be passed into
        row_weights, during smart downsampling and when weights are explicitly specified in the project settings.
    kwargs
        Added for forwards compatibility.

    Returns
    -------
    None
        fit() doesn't return anything, but must output an artifact
        (typically containing a trained object) into output_dir
        so that the trained object can be used during scoring.
    """

    logger.info("Fitting Preprocessing pipeline")
    preprocessor = dense_preprocessing_pipeline.fit(X)
    lb = LabelEncoder().fit(y)

    # write out the class labels file
    logger.info("Serializing preprocessor and class labels")
    with open(os.path.join(output_dir, "class_labels.txt"), mode="w") as f:
        f.write("\n".join(str(label) for label in lb.classes_))

    # Dump the trained object [in this example - a trained PyTorch model]
    # into an artifact [in this example - artifact.pth]
    # and save it into output_dir so that it can be used later when scoring data
    # Note: DRUM will automatically load the model when it is in the default format (see docs)
    # and there is only one artifact file
    with open(os.path.join(output_dir, "preprocessor.pkl"), mode="wb") as f:
        pickle.dump(preprocessor, f)

    logger.info("Transforming input data")
    X = preprocessor.transform(X)
    y = lb.transform(y)

    # For reproducible results
    torch.manual_seed(0)

    estimator, optimizer, criterion = build_classifier(X, len(lb.classes_))
    logger.info("Training classifier")
    train_classifier(X, y, estimator, optimizer, criterion)
    artifact_name = "artifact.pth"
    save_torch_model(estimator, output_dir, artifact_name)


def load_model(code_dir: str) -> Any:
    """
    Can be used to load supported models if your model has multiple artifacts, or for loading
    models that DRUM does not natively support

    Parameters
    ----------
    code_dir : is the directory where model artifact and additional code are provided, passed in

    Returns
    -------
    If used, this hook must return a non-None value
    """
    global preprocessor
    with open(os.path.join(code_dir, "preprocessor.pkl"), mode="rb") as f:
        preprocessor = pickle.load(f)

    # PyTorch 2.6+ changed the default behavior of torch.load() to only load model
    # weights (weights_only=True). We need to explicitly set weights_only=False to load
    # the full model.
    model = torch.load(os.path.join(code_dir, "artifact.pth"), weights_only=False)
    model.eval()
    return model


def transform(data: pd.DataFrame, model: Any) -> pd.DataFrame:
    """
    Intended to apply transformations to the prediction data before making predictions. This is
    most useful if DRUM supports the model's library, but your model requires additional data
    processing before it can make predictions

    Parameters
    ----------
    data : is the dataframe given to DRUM to make predictions on
    model : is the deserialized model loaded by DRUM or by `load_model`, if supplied

    Returns
    -------
    Transformed data
    """
    if preprocessor is None:
        raise ValueError("Preprocessor not loaded")

    # Remove target columns if they're in the dataset
    for target_col in ["class"]:
        if target_col in data:
            data.pop(target_col)

    return data


def score(data: pd.DataFrame, model: Any, **kwargs: Dict[str, Any]) -> pd.DataFrame:
    """
    DataRobot will run this hook when the task is used for scoring inside a blueprint

    This hook defines the output of a custom estimator and returns predictions on input data.
    It should be skipped if a task is a transform.

    Note: While best practice is to include the score hook, if the score hook is not present DataRobot will
    add a score hook and call the default predict method for the library
    See https://github.com/datarobot/datarobot-user-models#built-in-model-support for details

    Parameters
    ----------
    data: pd.DataFrame
        Is the dataframe to make predictions against. If the `transform` hook is utilized,
        `data` will be the transformed data
    model: Any
        Trained object, extracted by DataRobot from the artifact created in fit().
        In this example, contains trained sklearn pipeline extracted from artifact.pkl.
    kwargs:
        Additional keyword arguments to the method

    Returns
    -------
    This method should return predictions as a dataframe with the following format:
      Classification: must have columns for each class label with floating- point class
        probabilities as values. Each row should sum to 1.0. The original class names defined in the project
        must be used as column names. This applies to binary and multi-class classification.
    """

    # Note how we use the preprocessor that's loaded in load_model
    data = preprocessor.transform(data)
    data_tensor = torch.from_numpy(data).type(torch.FloatTensor)
    predictions = model(data_tensor).cpu().data.numpy()

    return pd.DataFrame(data=predictions, columns=kwargs["class_labels"])
