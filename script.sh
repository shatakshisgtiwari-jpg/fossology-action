#!/bin/bash -e

# SPDX-FileCopyrightText: 2024 Rajul Jha <rajuljha49@gmail.com>
#
# SPDX-License-Identifier: GPL-2.0-only

# Prepare docker run command with arguments
docker_cmd="docker run --rm --name fossologyscanner -w /opt/repo -v ${PWD}:/opt/repo \
    -e GITHUB_TOKEN=${GITHUB_TOKEN} \
    -e GITHUB_PULL_REQUEST=${GITHUB_PULL_REQUEST} \
    -e GITHUB_REPOSITORY=${GITHUB_REPOSITORY} \
    -e GITHUB_API=${GITHUB_API_URL} \
    -e GITHUB_REPO_URL=${GITHUB_REPO_URL} \
    -e GITHUB_REPO_OWNER=${GITHUB_REPO_OWNER} \
    -e GITHUB_ACTIONS"

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

# Run the command
echo $docker_cmd
eval $docker_cmd

# Generate dashboard if enabled and SPDX JSON exists
if [ "${DASHBOARD}" == "true" ]; then
    echo "Generating license compliance dashboard..."
    
    # Find SPDX JSON file
    SPDX_JSON=""
    if [ -f "fossology-spdx.json" ]; then
        SPDX_JSON="fossology-spdx.json"
    elif [ -f "spdx.json" ]; then
        SPDX_JSON="spdx.json"
    elif [ -f "report.spdx.json" ]; then
        SPDX_JSON="report.spdx.json"
    else
        # Search in common output directories
        SPDX_JSON=$(find . -maxdepth 2 -name "*.spdx.json" -o -name "*spdx*.json" | head -1)
    fi
    
    if [ -n "${SPDX_JSON}" ] && [ -f "${SPDX_JSON}" ]; then
        echo "Found SPDX JSON: ${SPDX_JSON}"
        
        # Set dashboard environment variables
        export DASHBOARD_ENABLED="${DASHBOARD}"
        export DASHBOARD_CHARTS="${DASHBOARD_CHARTS}"
        export DASHBOARD_RISK="${DASHBOARD_RISK}"
        export DASHBOARD_UNKNOWN="${DASHBOARD_UNKNOWN}"
        
        # Determine script directory
        SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
        if [ -n "${GITHUB_ACTION_PATH}" ]; then
            SCRIPT_DIR="${GITHUB_ACTION_PATH}"
        fi
        
        # Generate dashboard
        python3 "${SCRIPT_DIR}/generate_dashboard.py" "${SPDX_JSON}"
        
        if [ $? -eq 0 ]; then
            echo "✅ Dashboard generated successfully"
        else
            echo "⚠️ Dashboard generation failed"
        fi
    else
        echo "⚠️ No SPDX JSON file found. Dashboard generation skipped."
        echo "Note: Set report_format to include SPDX_JSON to enable dashboard."
    fi
else
    echo "Dashboard generation disabled"
fi