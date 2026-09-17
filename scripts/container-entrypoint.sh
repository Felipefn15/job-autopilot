#!/usr/bin/env bash
set -euo pipefail

umask 077
mkdir -p "${DATA_DIR:-/data}" "${BROWSER_PROFILE_DIR:-/data/playwright_profile}"

if [[ "${BROWSER_HEADLESS:-false}" != "true" ]]; then
  Xvfb "${DISPLAY:-:99}" -screen 0 1920x1080x24 -nolisten tcp &
  sleep 1
fi

if [[ "${ENABLE_VNC:-false}" == "true" ]]; then
  x11vnc -display "${DISPLAY:-:99}" -forever -shared -nopw -listen 0.0.0.0 &
  websockify --web=/usr/share/novnc 6080 localhost:5900 &
  echo "noVNC is available on container port 6080."
fi

exec "$@"
