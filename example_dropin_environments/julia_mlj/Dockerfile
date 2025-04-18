# This is the default base image for use with user models and workflows.
# It contains a variety of common useful data-science packages and tools.
FROM datarobot/julia-dropin-env-base

# Install the list of core requirements, e.g. sklearn, numpy, pandas, flask.
# **Don't modify this file!**
COPY dr_requirements.txt dr_requirements.txt

# '--upgrade-strategy eager' will upgrade installed dependencies
# according to package requirements or to the latest
RUN pip3 install -U --upgrade-strategy eager --no-cache-dir --prefer-binary -r dr_requirements.txt  && \
    rm -rf dr_requirements.txt

# rebuild julia image as it depends on the CPU and architecture
RUN julia /opt/julia/sysim.jl

# Copy the drop-in environment code into the correct directory
# Code from the custom model tarball can overwrite the code here
ENV HOME=/opt CODE_DIR=/opt/code ADDRESS=0.0.0.0:8080
WORKDIR ${CODE_DIR}
COPY ./*.sh ${CODE_DIR}/

ENV WITH_ERROR_SERVER=1
#Uncomment the following line to switch to production mode
#ENV PRODUCTION=1 MAX_WORKERS=4 SHOW_STACKTRACE=1

ENTRYPOINT ["/opt/code/start_server.sh"]
