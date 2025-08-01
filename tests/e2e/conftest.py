"""
Copyright 2021 DataRobot, Inc. and its affiliates.
All rights reserved.
This is proprietary source code of DataRobot, Inc. and its affiliates.
Released under the terms of DataRobot Tool and Utility Agreement.
"""
import json
import os
import uuid
import warnings
from urllib.parse import urlparse

import datarobot as dr
import pytest
from datarobot.enums import DEFAULT_MAX_WAIT
from dr_usertool.datarobot_user_database import DataRobotUserDatabase
from dr_usertool.utils import get_permissions

from tests.constants import PUBLIC_DROPIN_ENVS_PATH, TESTS_DATA_PATH

WEBSERVER_URL = "http://localhost"
ENDPOINT_URL = WEBSERVER_URL + "/api/v2"


def get_admin_api_key():
    admin_api_key = os.environ.get("APP_ADMIN_API_KEY")
    if not admin_api_key:
        raise ValueError("APP_ADMIN_API_KEY environment variable is not set")
    return admin_api_key


def dr_usertool_setup():
    webserver = urlparse(WEBSERVER_URL)
    admin_api_key = get_admin_api_key()
    return DataRobotUserDatabase.setup(
        "adhoc", webserver.hostname, protocol=webserver.scheme, admin_api_key=admin_api_key
    )


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    # check for skipping setup on xdist master process
    if not config.pluginmanager.getplugin("dsession"):
        suffix = str(uuid.uuid4())
        env = dr_usertool_setup()
        admin_api_key = get_admin_api_key()

        # User credentials
        user_username = "local-custom-model-tests-{}@datarobot.com".format(suffix)
        user_password = "Lkjkljnm988989jkr5645tv_{}".format(suffix)
        user_api_key_name = "drum-functional-tests"
        user_permissions = get_permissions(
            "tests/fixtures/user_permissions.json", user_api_key_name
        )

        # Add organization
        org_name = "local-custom-model-tests-org"
        try:
            # ensure it exists
            DataRobotUserDatabase.add_organization(environment=env, organization_name=org_name)
        except ValueError:
            # already exists
            pass
        org = DataRobotUserDatabase.get_organization(environment=env, organization_name=org_name)
        org_id = org["id"]

        # Add user
        DataRobotUserDatabase.add_user(
            env,
            user_username,
            admin_api_key=admin_api_key,
            password=user_password,
            permissions=user_permissions,
            api_key_name=user_api_key_name,
            activated=True,
            unix_user="datarobot_imp",
            organization_id=org_id,
        )

        user_api_keys = DataRobotUserDatabase.get_api_keys(env, user_username, user_password)
        user_api_key = user_api_keys["data"][0]["key"]

        os.environ["DATAROBOT_API_TOKEN"] = user_api_key  # TODO: rename to DATAROBOT_API_KEY
        os.environ["DATAROBOT_ENDPOINT"] = ENDPOINT_URL
        config.user_username = user_username


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    if not config.pluginmanager.getplugin("dsession"):
        warnings.simplefilter("ignore")
        env = dr_usertool_setup()
        admin_api_key = get_admin_api_key()
        DataRobotUserDatabase.delete_user(env, config.user_username, admin_api_key=admin_api_key)
        warnings.simplefilter("error")


def pytest_sessionstart(session):
    dr.Client(endpoint=ENDPOINT_URL, token=os.environ["DATAROBOT_API_TOKEN"])


def get_image_uri(env_info_file):
    with open(env_info_file, "r") as f:
        data = json.load(f)

    image_repo = data["imageRepository"]
    env_version = data["environmentVersionId"]

    return f"datarobot/{image_repo}:{env_version}"


def create_drop_in_env(
    env_root_folder, env_name, programming_language="python", max_wait=DEFAULT_MAX_WAIT
):
    env_dir = os.path.join(env_root_folder, env_name)
    full_env_name = f"{os.path.basename(env_root_folder)}/{env_name}"
    environment = dr.ExecutionEnvironment.create(
        name=full_env_name, programming_language=programming_language
    )
    image_uri = get_image_uri(os.path.join(env_dir, "env_info.json"))
    environment_version = dr.ExecutionEnvironmentVersion.create(
        environment.id, docker_image_uri=image_uri, max_wait=max_wait
    )
    return environment.id, environment_version.id


@pytest.fixture(scope="session")
def java_drop_in_env():
    return create_drop_in_env(PUBLIC_DROPIN_ENVS_PATH, "java_codegen", "java")


@pytest.fixture(scope="session")
def python311_drop_in_env():
    return create_drop_in_env(PUBLIC_DROPIN_ENVS_PATH, "python311")


@pytest.fixture(scope="session")
def sklearn_drop_in_env():
    return create_drop_in_env(PUBLIC_DROPIN_ENVS_PATH, "python3_sklearn")


@pytest.fixture(scope="session")
def xgboost_drop_in_env():
    return create_drop_in_env(PUBLIC_DROPIN_ENVS_PATH, "python3_xgboost")


@pytest.fixture(scope="session")
def pytorch_drop_in_env():
    return create_drop_in_env(
        PUBLIC_DROPIN_ENVS_PATH, "python3_pytorch", max_wait=2 * DEFAULT_MAX_WAIT
    )


@pytest.fixture(scope="session")
def onnx_drop_in_env():
    return create_drop_in_env(PUBLIC_DROPIN_ENVS_PATH, "python3_onnx")


@pytest.fixture(scope="session")
def keras_drop_in_env():
    return create_drop_in_env(PUBLIC_DROPIN_ENVS_PATH, "python3_keras")


@pytest.fixture(scope="session")
def r_drop_in_env():
    return create_drop_in_env(
        PUBLIC_DROPIN_ENVS_PATH,
        "r_lang",
        "r",
        max_wait=4 * DEFAULT_MAX_WAIT,
    )


@pytest.fixture(scope="session")
def julia_drop_in_env():
    return create_drop_in_env(PUBLIC_DROPIN_ENVS_PATH, "julia_mlj", "other")


@pytest.fixture(scope="session")
def binary_testing_data():
    dataset = dr.Dataset.create_from_file(
        file_path=os.path.join(TESTS_DATA_PATH, "iris_binary_training.csv")
    )
    return dataset.id


@pytest.fixture(scope="session")
def binary_vizai_testing_data():
    dataset = dr.Dataset.create_from_file(
        file_path=os.path.join(TESTS_DATA_PATH, "cats_dogs_small_training.csv")
    )
    return dataset.id


@pytest.fixture(scope="session")
def regression_testing_data():
    dataset = dr.Dataset.create_from_file(
        file_path=os.path.join(TESTS_DATA_PATH, "juniors_3_year_stats_regression.csv")
    )
    return dataset.id


@pytest.fixture(scope="session")
def multiclass_testing_data():
    dataset = dr.Dataset.create_from_file(
        file_path=os.path.join(TESTS_DATA_PATH, "skyserver_sql2_27_2018_6_51_39_pm.csv")
    )
    return dataset.id


@pytest.fixture(scope="session")
def unstructured_testing_data():
    dataset = dr.Dataset.create_from_file(
        file_path=os.path.join(TESTS_DATA_PATH, "unstructured_data.txt")
    )
    return dataset.id
