#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SERVICE_NAME="$(basename "$SCRIPT_DIR")"
SERVICE_PATH="/service/$SERVICE_NAME"

if [ ! -e "$SERVICE_PATH" ]; then
    echo "$SERVICE_PATH does not exist. Run install.sh first."
    exit 1
fi

svc -u "$SERVICE_PATH"
sleep 1
svc -t "$SERVICE_PATH"
sleep 1
svstat "$SERVICE_PATH"
