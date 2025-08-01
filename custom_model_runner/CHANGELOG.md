# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

#### [1.16.21] - 2025-07-16
##### Removed
- Removed PMML support

#### [1.16.20] - 2025-07-03
#### Changed
- Fixed VLLM support.

#### [1.16.19] - 2025-06-26
#### Changed
- Allow override NIM server details.

#### [1.16.18] - 2025-06-24
##### Changed
- Added support for drum inline predictor for agentic models
- Updated mlops to use improved async mode

#### [1.16.17] - 2025-06-05
##### Changed
- Fixed issue with OTel tracing when flask server uses more then on process
- Added gracefull shutdown for OTel tracer

#### [1.16.16] - 2025-06-03
##### Changed
- Minor improvements required for chat API and agentic metrics

#### [1.16.15] - 2025-05-30
##### Changed
- Added OTel instrumentation for chat interface.

#### [1.16.14] - 2025-05-27
##### Changed 
- Fix for `chat()` with a `ModerationPipeline`.

#### [1.16.13] - 2025-05-12
##### Added 
- Request ID for logging messages
- API requests are logged with Request ID
- Access log with request_id for errored API calls
- Add support for `AGENTIC_WORKFLOW` target type

##### Changed
- Using logs output for all server operations. `print` command is discouraged in user modules.

#### [1.16.12] - 2025-04-23
##### Changed
- Allow `select` advanced tuning parameters to be up to 1024 characters
- Add support for `get_supported_llm_models()` hook with OpenAI `v1/models` API.

#### [1.16.11] - 2025-03-31
##### Changed
- Add support for `extra_body` handling in NIM and vLLM chat completion proxy endpoints.
- Use optimized `association_id` generation logic for chat completions.

#### [1.16.10.post1] - 2025-06-25
#### Changed
- Allow override NIM server details.

#### [1.16.10] - 2025-03-19
##### Changed
- Ensure only TextGen models have chat capability.

#### [1.16.9] - 2025-03-18
##### Changed
- Handles the special case when the model fails to initialize within the NIM Predictor.

#### [1.16.8] - 2025-03-14
##### Changed
- In Chat Completion requests, the `model` parameter `datarobot-deployed-llm` is translated into the actual model name.


#### [1.16.7] - 2025-02-27
##### Changed
- Fix bug with handling of `model` param in Chat Completion requests.

#### [1.16.6] - 2025-02-26
##### Changed
- vLLM and NIM predictors now allow the user to specify `model` name as part of a chat completion request. The old behavior hard-coded `datarobot-deployed-llm` as the model name. While this value is still the default if no model name is passed in the completion request, it can be overriden by setting the `served_model_name` runtime parameter.
- Adds support for `score()` hook in `NIMPredictor()` class.

#### [1.16.5] - 2025-02-18
##### Changed
- vLLM predictor now supports `default_parallelism` runtime parameter for setting either -tp or -pp
  based on the number of GPUs provided in the Resource Bundle. By default -tp will be used.
- Add support for PyTorch 2.6+ models in Python predictor.
- Extend DRUM API to support proxy requests to the model server.
- Extend NimPredictor to support multi-container deployments
- Internal adjustments to support newer versions of Keras.
- Adds support for `score_unstructured()` hook in `NIMPredictor()` class.

#### [1.16.4] - 2025-01-31
##### Changed
- Added support for Python 3.12

#### [1.16.3] - 2025-01-28
##### Changed
- vLLM and NIM predictors now support `CUSTOM_MODEL_WORKERS` runtime parameter values greater than 1.

#### [1.16.2] - 2025-01-23
##### Changed
- Don't report monitoring data if training data is not available.
- Update NIM predictor to look for both `start-server.sh` or `start_server.sh` in the image.

#### [1.16.1] - 2025-01-22
##### Changed
- Remove support for Apache Arrow.

#### [1.16.0] - 2025-01-08
- Remove 'mlpiper' dependency and replace its functionality with comparable built-in implementations.
- Avoid using the mlops tracking agent to report statistics to DataRobot.
- Deprecate the '--production' mode and replace its functionality with Flask running in multi-process mode.
  Previously, this mode relied on the Nginx and uWSGI servers, which have now been removed.
- Add support for GeoPoint target type.
- Internal improvements.

#### [1.15.0] - 2024-11-26
##### Changed
- Add support for lazy-loading from a command line, mainly for local development.

#### [1.14.3] - 2024-11-13
##### Changed
- Allow any value for `model` argument in Chat API request for `BaseOpenAiGpuPredictor`.

#### [1.14.2] - 2024-11-07
##### Changed
- Removed most of the upper constraints for DRUM dependencies.

#### [1.14.1] - 2024-11-01
##### Fix
- Status updater in LLM envs displays correct number of steps left to complete.

#### [1.14.0] - 2024-10-31
##### Changed
- Add lazy loading of Custom Model data

##### Fix
- Failure to submit monitoring could cause Chat API request to fail
- Association id would not be passed to moderations library

#### [1.13.0] - 2024-10-22
##### Changed
- Add chat api support for GPU Predictors
- Extend capabilities endpoint with chat support info
- Add watchdog to GPU Predictors

#### [1.12.2] - 2024-10-04
##### Changed
- Fixed some issues with chat monitoring

#### [1.12.1] - 2024-09-24
##### Changed
- Improved log messages
- Chat monitoring support
- flask-cors update

#### [1.12.0] - 2024-09-03
##### Changed
- Update support to Py>=3.8

#### [1.11.6] - 2024-08-30
##### Changed
- Don't cache vLLM dirs in DRUM

#### [1.11.5] - 2024-06-18
##### Changed
- Set numpy version to <2.0.0

#### [1.11.4] - 2024-05-30
##### Changed
- Upgrade Pillow to 10.3.0 to address CVE-2024-28219

#### [1.11.3] - 2024-05-24
##### Fix
- Pipeline template port values jsonification.

#### [1.11.2] - 2024-05-23
##### Changed
- Bump werkzeug==3.0.3
- Add runtime params into running in docker command

#### [1.11.1] - 2024-05-13
##### Changed
- Adds additional supported runtime params for vLLM predictor.

#### [1.11.0] - 2024-05-01
##### Added
- Adds new GPU Language Predictor class with support for NVIDIA Triton, NIM and vLLM
inference servers.
- Hide guard presence if moderations are not enabled.
- Add support for `datarobot-mlops` 10.0+ import paths.

#### [1.10.21] - 2024-03-15
##### Changed
- support providing arguments via env vars, e.g `RUNTIME_PARAMS_FILE=file.yml` is the same as `--runtime-params-file file.yml`
- Other bug fixes

#### [1.10.20] - 2024-02-06
##### Changed
- Add support for extra model output in PPS
- Fix extra model output extraction when target name is provided (text-generation)
- Bump datarobot-model-metrics library to 0.3.6
- Other bug fixes

#### [1.10.19] - 2024-01-29
##### Changed
- Bump pillow<=10.2.0
- Add support for extra model output from Python and R models

#### [1.10.18] - 2024-01-16
##### Changed
- Add support for numeric runtime parameters
- Add support for allowEmpty field for runtime parameters
- Add check for duplicate runtime parameters definitions

#### [1.10.17] - 2023-01-01
##### Changed
- scrub sensitive values from outputs during fit and predict

#### [1.10.16] - 2023-12-08
##### Changed
- Add support for boolean runtime parameters

#### [1.10.15] - 2023-12-04
##### Changed
- Added `/invocations` method to support deployment to AWS SageMaker

#### [1.10.14] - 2023-11-22
##### Changed
- Bump pyarrow<=14.0.1

#### [1.10.13] - 2023-11-13
##### Changed
- Bump pillow<=10.1.0
- Bump black==23.10.1
- Bump pyarrow<=14.0.1
- Reformat code according to the latest black rules

#### [1.10.12] - 2023-11-06
##### Changed
- Bump pillow<=9.4.0
- Bump werkzeug==3.0.1

#### [1.10.11] - 2023-10-31
##### Changed
- Update error messages
- Clean up exceptions handling in model_adapter
- Added user-secrets-mount-path and user-secrets-prefix

#### [1.10.10] - 2023-08-14
##### Changed
- Pin datarobot<4

#### [1.10.9] - 2023-08-08
##### Added
- Pin pandas<=2.0.3

#### [1.10.8] - 2023-08-01
##### Added
- Make /(root) and ping endpoints return 513 in case of server startup error
- Bump supported Python version to 3.11
- Pin datarobot>=3.1.0,<3.2

#### [1.10.7] - 2023-06-30
##### Added
- Constrain scipy>=1.1,<1.11 in the envs
- Support Text Generation (LLM) targets
- Bump datarobot-mlops==9.1.3

#### [1.10.6] - 2023-06-12
##### Changed
- Use `lineterminator` in pandas.to_csv()
- Constrain pandas>=1.5.0,<=1.5.3
- Constrain numpy>=1.20.3

#### [1.10.5] - 2023-06-06
##### Changed
- Bump scikit-learn==1.0.2, datarobot-mlops==9.0.7
- Cleanup pandas deprecated method: DataFrame.append()

#### [1.10.4] - 2023-05-24
##### Changed
- Bump flask<=2.3.2 werkzeug<=2.3.4 markupsafe<=2.1.2
- Bump DR scoring code, H2O artifacts for Java predictor

#### [1.10.3] - 2023-05-16
##### Fixed
- Handling of single column datasets in R with missing values
##### Changed
- Example and documentation for MLOps reporting from unstructured models
- Upgrade dr-usertool to 2.x

#### [1.10.2] - 2023-04-24
##### Fixed
- Typeschema numeric categorical equivalency with missing values

#### [1.10.1] - 2023-03-23
##### Changed
- bump DRUM to support Py<3.11
- bump datarobot==3.1.0, pyarrow<=10.0.1, pandas<1.4.0, trafaret>=2.0.0,<2.2.0, rpy2==3.5.8

#### [1.10.0] - 2023-02-10
##### Added
- Runtime parameters support
- Support for `runtimeParameterDefinitions` section in the `model-metadata.yaml` file.
- New CLI flag `--runtime-params-file` which injects Runtime Parameter values into the variables defined in the model metadata.
- `RuntimeParameters` class that simplifies accessing runtime parameters from within a model's `custom.py` file.
##### Changed
- Pin: `datarobot==3.0.2`, `dr-usertool==1.0.0`, `datarobot-bp-workshop==0.2.6`

#### [1.9.14] - 2023-01-11
##### Added
- Enable users to print logs from their custom models without any special flags or requirements.
- Pass request headers into the score_unstructured() hook.

#### [1.9.13] - 2022-11-08
##### Changed
- Pin mlpiper~-2.6.0, log4j==2.19.0
##### Added
- Added log4j custom logger initialization example TestCustomPredictor.java

#### [1.9.12] - 2022-10-31
##### Added
- Add support for a new hook (`custom_flask.py`) in the model-dir to allow extending the Flask application when drum is running in server mode.
- Add a new model template sample (`flask_extension_httpauth`) to illustrate a potential authentication use-case using the new `custom_flask.py` hook.
##### Changed
- Improve handling of SIGTERM to support cleaner shutdowns.
- Use `--init` flag when running docker containers to improve how signals are propagated to child processes.

#### [1.9.11] - 2022-10-24
##### Changed
- Add support to initialize DR Python client in order to allow DR API access.

#### [1.9.10] - 2022-10-05
##### Changed
- Pin `datarobot==2.28.1`
- Require monitor settings for embedded monitor

#### [1.9.9] - 2022-09-29
##### Changed
- Bump com.datarobot.datarobot-prediction package to 2.2.1
##### Fixed
- Pin `datarobot==2.27.0`
- Handle missing values in image typeschema validator

#### [1.9.8] - 2022-08-04
##### Changed
- Added logging method to custom task interface
##### Fixed
- Typeschema correctly handles integer numeric categorical values

#### [1.9.7] - 2022-08-02
##### Changed
- Pin flask<2.2.0 rpy2==3.5.2

#### [1.9.6] - 2022-07-19
##### Changed
- Bumped rpy2>=3.5.2
- Fixed typechecking in R predictor

#### [1.9.5] - 2022-07-06
##### Fixed
- Stringify class labels for PMML model

#### [1.9.4] - 2022-06-13
##### Removed
- Removed drum autofit functionality

#### [1.9.3] - 2022-04-08
##### Added
- Fit runtime report file

#### [1.9.2] - 2022-04-01
##### Fixed
- Pin werkzeug<2.2.0
- Remove werkzeug shutdown API usage

#### [1.9.1] - 2022-03-31
##### Fixed
- Pin werkzeug==2.0.3

#### [1.9.0] - 2022-03-21
##### Added
- DRUM support Python 3.9

#### [1.8.0] - 2022-02-18
##### Added
- Built-in support for ONNX models
- Support for new custom (training) task templates

#### [1.7.2dev1] - 2022-02-16
##### Fixed
- Don't include default drum java predictors into java classpath when working with custom predictor

#### [1.7.1] - 2022-02-10
##### Fixed
- Handle NoSuchProcess exception in perf-test
- Allow duplicate column names for transforms

#### [1.7.0] - 2022-02-03
##### Added
- Add support for embedded MLOps initialization for unstructured models
- Add support for a graceful termination of a pipeline
- Make Java and R envs to work on Py3.7 instead of 3.6

##### Updated
- Bump 'mlpiper' dependency to 2.5.0 (and higher)

#### [1.6.7] - 2022-01-21
##### Updated
- update log4j version to 2.17.1

#### [1.6.6] - 2021-12-16
##### Updated
- update log4j version to 2.16.0
- bump datarobot>=2.27.0

#### [1.6.5] - 2021-12-11
##### Fixed
- update log4j version
- wrap main func with "if __name__ == __main__"

#### [1.6.4] - 2021-12-03
##### Added
##### Fixed
- Refactor subprocess.Popen() to call command without shell
- Fix numeric class labels for R tasks

#### [1.6.3] - 2021-11-16
##### Added
##### Fixed
- Improve the logic to handle class_labels in BaseLanguagePredictor and PythonModelAdapter.
- Improve the data validation on CAT & TXT features.
- Do not block thread while reading DRUM server stdout during perf tests.

#### [1.6.2] - 2021-11-04
##### Added
- support for Java Unstructured Models
- Add new exit code (3) and improve schema validation exception handling
##### Fixed

#### [1.6.1] - 2021-10-22
##### Changed
- bump DataRobot client dependency to >= 2.26.0
- handle artifacts case insensitively

#### [1.6.0] - 2021-10-08
##### Changed
- regression boston dataset has been replaced with juniors grade dataset
- R: dataset column names are not replaced with R variable valid names (it has been implicitly replaced before)

#### [1.5.16] - 2021-9-30
##### Changed
- add `uwsgi` as extra dependency
##### Fixed
- improved categorical vs text for validation

#### [1.5.15] - 2021-09-23
##### Added
- Release v1.5.15 due to a glitch with v1.5.14 release
- Show CPU usage info in /stats API
- Reporting class labels through MLOps monitoring
- Restrict Y output from custom transform tasks

#### [1.5.14] - 2021-09-22
##### Note
- Consider unreleased, removed from PyPi

#### [1.5.13] - 2021-09-17
##### Fixed
- compile DRUM with Java 11

#### [1.5.12] - 2021-09-15
##### Fixed
- R custom tasks sampling
- R sparse input staying sparse and not getting casted to dense
- R transform sparse output support
- Fixing off by one error with R Sparse Transforms
- Updating Readme documentation
- CSV parsing in Julia inference model
##### Added
- R sparse regression template
- R transform template
- Image transform template
- Type schema to transforms and estimators

#### [1.5.11] - 2021-08-19
##### Fixed
- Apply default schema to transforms
##### Added
- type schema to pipeline examples

#### [1.5.10] - 2021-07-30
##### Fixed
- Updated version of strictyaml to fix issue with comments in yaml metadata files
##### Added
- R support for custom transforms
- Default type schema for transforms when not provided
- Enable strict type-schema validation by default

#### [1.5.9]- 2021-07-19
##### Fixed
- Check R colname validation as both literals and doubles

#### [1.5.8] - 2021-07-14
##### Fixed
- an attempt to stabilize connection to py4j gateway in Java components

#### [1.5.7] - 2021-06-22
##### Updated
- Show full R traceback for fit/predict errors
##### Fixed
- Loading hooks from both custom.R and custom.r
- Fix single-col data bug when running drum fit in R
- Error when using -cd instead of --code-dir when running with docker
- Error when using spaces in --code-dir path when running with docker

#### [1.5.6] - 2021-05-17
##### Fixed
- validate classification probabilities add up to one for all the predictors
- support Julia models

#### [1.5.5] - 2021-04-28
##### Updated
- pin DR client version to 2.24.0
- show stdout for score and transform hooks during drum fit when ``--verbose`` is present

#### [1.5.4] - 2021-04-13
##### Added
- parameter support for training models and transformers

#### [1.5.3] - 2021-04-03
##### Fixed
- check for class labels presence in the model yaml file for binary/multiclass targets
- DRUM Java BasePredictor cleanup
- update docs

#### [1.5.2] - 2021-03-19
##### Added
- sparse column support
- model metadata support for hyperparams and data type schema
- release v1.5.2

#### [1.5.1] - 2021-03-09
##### Fixed
- fix/improve data transfer between Py and Java via py4j
- release v1.5.1

#### [1.5.0] - 2021-02-26
##### Added
- install dependencies into an image if there is a requirements.txt file in the code dir
- release v1.5.0

#### [1.4.16] - 2021-02-18
##### Added
- `/info` endpoint
- progress spinner when building a docker images

##### Fixed
- unset entrypoint when running DRUM in docker

#### [1.4.15] - 2021-02-11
##### Fixed
- dataset temp naming for failed validation checks
- command line argument parsing

#### [1.4.14] - 2021-02-08
##### Added
- make DRUM return predictions in DR format when deployment config is provided
##### Changed
- default perf tests timeout from 180 to 600 s
- refactor model metadata YAML schema

#### [1.4.13] - 2021-02-01
##### Added
- custom Java predictors support
##### Changes
- apply --skip-predict if SKIP_PREDICT env var is present
##### Fixed
- don't fail on spaces in binary class labels in prediction checks
- fix error where X has colname '0' and target is unnamed

#### [1.4.12] - 2021-01-19
##### Changes
- bugfix to prevent resampling of data
- surface warning but don't error out if prediction consistency check fails
##### Fixed
- don't fail on spaces in binary class labels in prediction checks

#### [1.4.11] - 2021-01-14
##### Changes
- transform server passes back formats for both transformed X and y
- transform server passes back column names if transformed X is sparse

#### [1.4.10] - 2021-01-11
##### Added
- support providing arguments via env vars, e.g `TARGET_TYPE regression` is the same as `--target-type regression`
##### Changes
- prediction side effects check no longer run for custom transforms; still assert that transform server launches and returns 200 response
- test coverage confirming support of sparse input and output for custom transforms and transform server
##### Removed
-- `--unsupervised` arg support

#### [1.4.9] - 2020-12-29
##### Changes
- `transform` mode now takes and returns both `X` and `y`. The `transform` hook must use both arguments for custom transforms,
 but need only return `X` (if `y` is not returned, it will not be transformed)
- The user may forgo a `transform` hook for custom transforms if they use an sklearn artifact. If the user does not define
`transform`, the target will not be used in transforming the fatures and will remain un-transformed.
- Added support for multiclass to drum push in anticipation of the release of datarobot client v2.22
- check if payload format (csv/mtx/arrow) is supported

#### [1.4.8] - 2020-12-11
##### Fixed
- Force class labels to be strings

#### [1.4.7] - 2020-12-11
##### Added
- do predictions side effects check (when fitting a model)
##### Fixed
- Handling of class mapping to class order with numeric values

#### [1.4.6] - 2020-12-08
##### Added
- **/predictions** and **/predictionsUnstructured** endpoints as aliases for **/predict** and **/predictUnstructured**
- handling the case when input sent as binary data
##### Fixed
- Validation of numeric multiclass class labels should always compare as strings

#### [1.4.5] - 2020-12-02
##### Added
-  **/transform** endpoint added to prediction server
##### Changes
- Allow multiclass to function with only 2 labels

#### [1.4.4] - 2020-11-24
##### Added
- New `transform` target type for performing pre-/post- processing on features/targets
##### Changes
- Unpin pyarrow version

#### [1.4.3] - 2020-11-17
##### Added
- Compare DRUM version on host and container when running in *--docker* mode
##### Fixed
- Arrow format input data support

#### [1.4.2] - 2020-11-14
##### Added
- Support for a single uwsgi process in production mode
- Capabilities endpoint
- Arrow format input data support

##### Changed
- Change dependency for new major release of mlpiper v2.4.0, which executes RESTful pipeline in a single uWSGI process
- Catch and report exceptions from user's code
- Set Flask server (no production) logging level to the level from the command line

##### Fixed
- Fixed issue with multiclass scoring failing with numerical class labels
- Fixed multiclass class labels file not working in --docker mode

#### [1.4.1] - 2020-10-29
##### Added
- H2O driverless AI mojo pipeline support
- fit on sparse data
- `predictUnstructured` endpoint for uwsgi-based prediction server

#### [1.4.0] - 2020-10-23
##### Added
- `multiclass` target type
- `class-labels` for specifying the class labels of a multiclass model
- `class-labels-file` for specifying a file containing the class labels of a multiclass model
- add multiclass classification support for `drum score` and `drum server`
##### Changed
- support only keras built into tensorflow >= 2.2.1
- `--target-type` is now required for `drum fit`

#### [1.3.0] - 2020-10-15
##### Added
- `read_input_data` hook
- add `target-type` param
- unstructured mode

#### [1.2.0] - 2020-08-28
##### Added
- optional **--language [python|r|java]** argument to enforce execution framework
- uwsgi/nginx powered prediction server
- **-max-workers** argument to limit number of workers in production server mode

##### Removed
- **--threaded** argument from Flask server mode

##### Changed
- dependencies: mlpiper==2.3.0, py4j~=0.10.9
- optional **--unsupervised** argument and handling for unsupervised Fit in python

#### [1.1.4] - 2020-08-04
##### Added
- the docker flag now takes a directory, and will build a docker image
- the `push` verb lets you add your code into DataRobot.
- H2O models support
- r_lang fit component, pipeline, and template
##### Changed
- search custom.py recursively in the code dir
- set rpy2 dependcy <= 3.2.7 to avoid pandas import error

## [1.1.3] - 2020-07-17
### Added
- error server is started in case of imports/pipeline failures
- drum_autofit() helper for sklearn estimator
### Changed
- updated Java predictor dependencies

## [1.1.2] - 2020-06-18
### Added
- PMML support

## [1.1.1] - 2020-06-10
### Added
- language detection by artifact and custom.py/R

### Changed
- now version check is called as `drum --version`

## [1.1.0] - 2020-05-29
### Changed
- public envs are pinned to drum==1.1.0

## [1.0.20] - 2020-05-28
### Changed
- the name to **drum**

## [1.0.19] - 2020-05-18
### Changed
- build only Python 3 wheel

## [1.0.18] - 2020-05-12
### Added
- cmrunner for custom model fit
- fit code to python3_sklearn model template

### Fixed
- printing result if `--output` is not provided

## [1.0.17] - 2020-05-07
### Changed
- change predict() hook to score()
- change signature to `score(data, mode, **kwargs)`
- change command `cmrun predict` to `cmrun score`

### Added
- `new` subcommand for model templates creation

## [1.0.16] - 2020-05-05
### Changed
- unpin rpy2 dependency version

## [1.0.15] - 2020-05-04
### Changed
- require to use sub-command, e.g. `cmrun predict`

## [1.0.14] - 2020-04-30
### Changed
- refactored command/subcommand usage

## [1.0.13] - 2020-04-27
### Added
- CMRUNNER_JAVA_XMX env var to pass max heap memory value to JVM
- autocompletion support
- performance tests feature

## [1.0.12] - 2020-04-23
### Changed
- optimized py4j usage for java predictor

## [1.0.11] - 2020-04-21
### Changed
- improved class labels handling in R binary classification

## [1.0.10] - 2020-04-20
### Added
- --threaded flag which allows to start cmrunner prediction server(Flask) in threaded mode
### Changes
- replaced custom hooks for R with
    - init() -> NULL
    - load_model(input_dir: character) -> Any
    - transform(data: data.frame, model: Any) -> data.frame
    - predict(data: data.frame, model: Any, positive_class_label: character, negative_class_label: character) -> data.frame
    - post_process(predictions: data.frame, model: Any) -> data.frame
- unify argument names in file reading/writing components

## [1.0.9] - 2020-04-16
### Changes
- improved prediction server response serialization

## [1.0.8] - 2020-04-10
### Added
- support for --docker command line option. Running the model inside a docker image

## [1.0.7] - 2020-04-08
### Added
- support Java Codegen models in batch and server modes

## [1.0.6] - 2020-04-03
### Changed
- replaced custom hooks for python with
    - init() -> None
    - load_model(input_dir: str) -> Any
    - transform(data: DataFrame, model: Any) -> DataFrame
    - predict(data: DataFrame, model: Any, positive_class_label: str, negative_class_label: str) -> DataFrame
    - post_process(predictions: DataFrame, model: Any) -> DataFrame

## [1.0.5] - 2020-03-30
### Added
- handle class labels for scikit-learn and R binary classification

## [1.0.4] - 2020-03-20
### Added
- make rpy2 dependency optional

## [1.0.3] - 2020-03-20
### Added
- R models support

## [1.0.2] - 2020-03-19
### Changed
- Change dep: mlpiper==2.2.0
- Bump version to push to test PyPI

## [1.0.1] - 2020-03-09
### Added
- Added wheelhouse for distributing "mlpiper"
- Added README
