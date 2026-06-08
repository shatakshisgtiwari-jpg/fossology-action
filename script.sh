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
docker_cmd+=" /bin/fossologyscanner"
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
eval $docker_cmd

# Generate dashboard if enabled
if [ "${DASHBOARD}" == "true" ]; then
    echo "Generating license compliance dashboard..."

    # Determine script directory
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    if [ -n "${GITHUB_ACTION_PATH}" ]; then
        SCRIPT_DIR="${GITHUB_ACTION_PATH}"
    fi

    # Find report file based on REPORT_FORMAT
    REPORT_FILE=""
    case "${REPORT_FORMAT}" in
        SPDX_JSON)
            REPORT_FILE=$(find . -maxdepth 2 \( -name "*.spdx.json" -o -name "*spdx*.json" \) ! -name "*.spdx3.*" -type f 2>/dev/null | head -1) ;;
        SPDX3_JSON)
            REPORT_FILE=$(find . -maxdepth 2 \( -name "*.spdx3.json" -o -name "*.spdx3*.json" -o -name "*.jsonld" \) -type f 2>/dev/null | head -1) ;;
        SPDX_YAML)
            REPORT_FILE=$(find . -maxdepth 2 \( -name "*.spdx.yaml" -o -name "*.spdx.yml" -o -name "*spdx*.yaml" \) -type f 2>/dev/null | head -1) ;;
        SPDX_RDF)
            REPORT_FILE=$(find . -maxdepth 2 \( -name "*.spdx.rdf" -o -name "*spdx*.rdf" \) ! -name "*.spdx3.*" -type f 2>/dev/null | head -1) ;;
        SPDX_TAG_VALUE)
            REPORT_FILE=$(find . -maxdepth 2 \( -name "*.spdx" -o -name "*.spdx.tv" -o -name "*spdx*.tv" \) -type f 2>/dev/null | head -1) ;;
        SPDX3_TTL)
            REPORT_FILE=$(find . -maxdepth 2 \( -name "*.spdx3.ttl" -o -name "*.ttl" \) -type f 2>/dev/null | head -1) ;;
        SPDX3_RDF)
            REPORT_FILE=$(find . -maxdepth 2 -name "*.spdx3.rdf" -type f 2>/dev/null | head -1) ;;
        TEXT|*)
            REPORT_FILE=$(find . -maxdepth 2 \( -name "*fossology*" -o -name "*scanner*" -o -name "*license*" \) -type f 2>/dev/null | head -1) ;;
    esac

    # Fallback: search for any recognizable report file
    if [ -z "${REPORT_FILE}" ]; then
        REPORT_FILE=$(find . -maxdepth 2 \( -name "*.spdx.json" -o -name "*.spdx3.json" -o -name "*.spdx.yaml" -o -name "*.spdx.yml" -o -name "*.spdx.rdf" -o -name "*.spdx" -o -name "*.spdx.tv" -o -name "*.jsonld" -o -name "*.ttl" \) -type f 2>/dev/null | head -1)
    fi

    if [ -f "${REPORT_FILE}" ]; then
        echo "Found report file: ${REPORT_FILE}"

        export DASHBOARD_ENABLED="${DASHBOARD}"
        export DASHBOARD_CHARTS="${DASHBOARD_CHARTS}"
        export DASHBOARD_RISK="${DASHBOARD_RISK}"
        export DASHBOARD_UNKNOWN="${DASHBOARD_UNKNOWN}"

        python3 "${SCRIPT_DIR}/generate_dashboard.py" "${REPORT_FILE}" --format "${REPORT_FORMAT}"

        if [ $? -eq 0 ]; then
            echo "✅ Dashboard generated successfully"
        else
            echo "⚠️ Dashboard generation failed"
        fi
    else
        echo "⚠️ No report file found for format '${REPORT_FORMAT}'. Dashboard generation skipped."
    fi
else
    echo "Dashboard generation disabled"
fi