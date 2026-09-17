#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo."
  exit 1
fi

apt-get update
apt-get install -y docker.io docker-compose-v2 git
systemctl enable --now docker

target_user="${SUDO_USER:-ubuntu}"
usermod -aG docker "${target_user}"

echo "Docker is ready."
echo "Reconnect the ${target_user} SSH session so the docker group membership is applied."
