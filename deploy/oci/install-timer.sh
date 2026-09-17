#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo."
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
app_dir="$(cd "${script_dir}/../.." && pwd)"
service_user="${SUDO_USER:-ubuntu}"
if [[ ! -f "${app_dir}/docker-compose.yml" ]]; then
  echo "Repository not found at ${app_dir}."
  exit 1
fi

escaped_app_dir="${app_dir//&/\\&}"
escaped_service_user="${service_user//&/\\&}"
sed \
  -e "s|__APP_DIR__|${escaped_app_dir}|g" \
  -e "s|__SERVICE_USER__|${escaped_service_user}|g" \
  "${app_dir}/deploy/oci/job-automation.service" \
  > /etc/systemd/system/job-automation.service
chmod 0644 /etc/systemd/system/job-automation.service
install -m 0644 "${app_dir}/deploy/oci/job-automation.timer" /etc/systemd/system/job-automation.timer

systemctl daemon-reload
systemctl enable --now job-automation.timer
systemctl list-timers job-automation.timer
