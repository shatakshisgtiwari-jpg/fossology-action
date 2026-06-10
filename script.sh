#!/bin/bash -e

# SPDX-FileCopyrightText: 2024 Rajul Jha <rajuljha49@gmail.com>
#
# SPDX-License-Identifier: GPL-2.0-only

# Prepare docker run command with arguments
docker_cmd="docker run --rm --name fossologyscanner --entrypoint /bin/fossologyscanner -w /opt/repo -v ${PWD}:/opt/repo \
    -e GITHUB_TOKEN=${GITHUB_TOKEN} \
    -e GITHUB_PULL_REQUEST=${GITHUB_PULL_REQUEST} \
    -e GITHUB_REPOSITORY=${GITHUB_REPOSITORY} \
    -e GITHUB_API=${GITHUB_API_URL} \
    -e GITHUB_REPO_URL=${GITHUB_REPO_URL} \
    -e GITHUB_REPO_OWNER=${GITHUB_REPO_OWNER} \
    -e GITHUB_ACTIONS"

# Mount $GITHUB_STEP_SUMMARY into the container so DashboardReport can
# append markdown to the GitHub Actions job summary directly.
if [ -n "${GITHUB_STEP_SUMMARY}" ]; then
    docker_cmd+=" -v ${GITHUB_STEP_SUMMARY}:/github/step_summary"
    docker_cmd+=" -e GITHUB_STEP_SUMMARY=/github/step_summary"
fi

# Pass dashboard configuration into the container.
# fossologyscanner.py reads DASHBOARD_ENABLED to decide whether to invoke
# DashboardReport after scanning — no external script or SPDX parsing needed.
docker_cmd+=" -e DASHBOARD_ENABLED=${DASHBOARD:-true}"
docker_cmd+=" -e DASHBOARD_CHARTS=${DASHBOARD_CHARTS:-true}"
docker_cmd+=" -e DASHBOARD_RISK=${DASHBOARD_RISK:-true}"
docker_cmd+=" -e DASHBOARD_UNKNOWN=${DASHBOARD_UNKNOWN:-true}"
docker_cmd+=" -e DASHBOARD_COPYRIGHTS=${DASHBOARD_COPYRIGHTS:-true}"

if [ "${KEYWORD_CONF_FILE_PATH}" != "" ]; then
    docker_cmd+=" -v ${GITHUB_WORKSPACE}/${KEYWORD_CONF_FILE_PATH}:/bin/${KEYWORD_CONF_FILE_PATH}"
fi
if [ "${ALLOWLIST_FILE_PATH}" != "" ]; then
    docker_cmd+=" -v ${GITHUB_WORKSPACE}/${ALLOWLIST_FILE_PATH}:/bin/${ALLOWLIST_FILE_PATH}"
fi

docker_cmd+=" ghcr.io/shatakshisgtiwari-jpg/fossology-scanner:latest"
docker_cmd+=" ${SCANNERS}"
docker_cmd+=" ${SCAN_MODE}"

# Add additional conditions
if [ "${SCAN_MODE}" == "differential" ]; then
    docker_cmd+=" --tags ${FROM_TAG} ${TO_TAG}"
fi
if [ "${KEYWORD_CONF_FILE_PATH}" != "" ]; then
    docker_cmd+=" --keyword-conf ${KEYWORD_CONF_FILE_PATH}"
fi
if [ "${ALLOWLIST_FILE_PATH}" != "" ]; then
    docker_cmd+=" --allowlist-path ${ALLOWLIST_FILE_PATH}"
fi
if [ "${REPORT_FORMAT}" != "" ]; then
    docker_cmd+=" --report ${REPORT_FORMAT}"
fi
if [ "${SCAN_MODE}" == "scan-only-deps" ] && [ "${SBOM_PATH}" != "" ]; then
    docker_cmd+=" --sbom-path ${SBOM_PATH}"
fi
if [ "${SCAN_MODE}" == "scan-dir" ] && [ "${SCAN_DIR}" != "" ]; then
    docker_cmd+=" --dir-path ${SCAN_DIR}"
fi

# Run the command
echo $docker_cmd
set +e
eval $docker_cmd
SCANNER_EXIT_CODE=$?
set -e

# Dashboard is now generated INSIDE the container by fossologyscanner.py
# via DashboardReport when DASHBOARD_ENABLED=true.
# No external report-file parsing is needed.
if [ "${DASHBOARD}" == "true" ]; then
    echo "Dashboard was generated inside the container (direct scanner mode)."
else
    echo "Dashboard generation disabled."
fi

# Exit with the scanner's original exit code
exit ${SCANNER_EXIT_CODE}