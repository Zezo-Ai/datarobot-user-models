#!/usr/bin/env bash
# Copyright 2021 DataRobot, Inc. and its affiliates.
#
# All rights reserved.
# This is proprietary source code of DataRobot, Inc. and its affiliates.
#
# Released under the terms of DataRobot Tool and Utility Agreement.

set -ex

export GIT_ROOT=$(git rev-parse --show-toplevel)


source "${GIT_ROOT}/tools/image-build-utils.sh"
source "${GIT_ROOT}/tests/functional/integration-helpers.sh"

ENVS_DIR="public_dropin_environments"
FRAMEWORK=$1

if [ "$1" = "python3_keras" ]; then
    DOCKER_IMAGE="python3_keras"
elif [ "$1" = "python3_onnx" ]; then
    DOCKER_IMAGE="python3_onnx"
elif [ "$1" = "python3_pytorch" ]; then
    DOCKER_IMAGE="python3_pytorch"
elif [ "$1" = "python3_sklearn" ]; then
    DOCKER_IMAGE="python3_sklearn"
elif [ "$1" = "python3_xgboost" ]; then
    DOCKER_IMAGE="python3_xgboost"
elif [ "$1" = "r_lang" ]; then
    DOCKER_IMAGE="r_lang"
elif [ "$1" = "java_codegen" ]; then
    DOCKER_IMAGE="java_codegen"
elif [ "$1" = "julia" ]; then
    ENVS_DIR="example_dropin_environments"
    DOCKER_IMAGE="julia_mlj"
elif [ "$1" = "triton" ]; then
    ENVS_DIR="public_dropin_gpu_environments"
    DOCKER_IMAGE="triton_server"
elif [ "$1" = "vllm" ]; then
    ENVS_DIR="public_dropin_gpu_environments"
    DOCKER_IMAGE="vllm"
elif [ "$1" = "nim" ]; then
    ENVS_DIR="public_dropin_nim_environments"
    DOCKER_IMAGE="nim_llama_8b"
elif [ "$1" = "nim_sidecar" ]; then
    ENVS_DIR="public_dropin_nim_environments"
    DOCKER_IMAGE="nim_sidecar"
fi;

export DOCKER_IMAGE=$DOCKER_IMAGE

# The "jenkins_artifacts" folder is created in the groovy script
DRUM_WHEEL_REAL_PATH="$(realpath "$(find jenkins_artifacts/datarobot_drum*.whl)")"

build_dropin_env_dockerfile "${GIT_ROOT}/${ENVS_DIR}/${DOCKER_IMAGE}" ${DRUM_WHEEL_REAL_PATH} || exit 1

# Authenticate to NVIDIA registry
# https://docs.nvidia.com/launchpad/ai/base-command-coe/latest/bc-coe-docker-basics-step-02.html
if [ -n "${NGC_CLI_API_KEY}" ]; then
  docker login --username="\$oauthtoken" --password="${NGC_CLI_API_KEY}" nvcr.io
fi

# shellcheck disable=SC2218
build_docker_image_with_drum "${GIT_ROOT}/${ENVS_DIR}/${DOCKER_IMAGE}" \
                              ${DOCKER_IMAGE} \
                              ${DRUM_WHEEL_REAL_PATH} || exit 1

unameOut="$(uname -s)"
case "${unameOut}" in
    Linux*)
        machine=Linux
        url_host="localhost"
        network="host"
      ;;
    Darwin*)
        machine=Mac
        url_host="host.docker.internal"
        network="bridge"
        ;;
    *)
        machine="UNKNOWN:${unameOut}"
        echo "Tests are not supported on $machine"
        exit 1
esac

# If we are in terminal will be true when running the script manually. Via Jenkins it will be false
TERMINAM_OPTION=""
if [ -t 1 ] ; then
  TERMINAM_OPTION="-t"
fi

echo "detected machine=$machine url_host: $url_host"
# Note: The mapping of /tmp is critical so the code inside the docker can run the tests.
#       Since one of the tests is using a docker the second docker can only share a host file
#       system with the first docker.
# Note: The --network=host will allow a code running inside the docker to access the host network
#       In mac we dont have host network so we use the host.docker.internal ip
# Note: The `--gpus all` is required for GPU predictors tests
# Note: For nim_sidecar, the GPUs go to the sidecar container, not the DRUM container

export TEST_URL_HOST=$url_host
export GPU_COUNT=$(nvidia-smi -L | wc -l)
echo "GPU count: $GPU_COUNT"

GPU_OPTION=""
if [[ $GPU_COUNT -ge 1 ]] ; then
  GPU_OPTION="--gpus all"
else
  # Don't set env var if no GPUs are available to tests can be skipped
  unset GPU_COUNT
fi

# allow write access to test results file from docker
rm -f ${GIT_ROOT}/results_integration.xml
touch ${GIT_ROOT}/results_integration.xml
chmod 777 ${GIT_ROOT}/results_integration.xml
sudo chmod -R 777 ${GIT_ROOT}/.pytest_cache

docker run -i $TERMINAM_OPTION $GPU_OPTION \
    --network $network \
    -v $HOME:$HOME \
    -e GPU_COUNT \
    -e AWS_ACCESS_KEY_ID \
    -e AWS_SECRET_ACCESS_KEY \
    -e HF_TOKEN \
    -e NGC_API_KEY \
    -e TEST_URL_HOST=$url_host \
    -v /tmp:/tmp \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "${GIT_ROOT}:${GIT_ROOT}" \
    --user root \
    --workdir ${GIT_ROOT} \
    --entrypoint "" \
    $DOCKER_IMAGE \
    ./tests/functional/run_integration_tests_in_framework_container.sh $1

TEST_RESULT=$?

echo "Done running tests: $TEST_RESULT"
exit $TEST_RESULT
