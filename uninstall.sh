#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SERVICE_NAME="$(basename "$SCRIPT_DIR")"
SERVICE_PATH="/service/$SERVICE_NAME"

svc -d "$SERVICE_PATH" 2>/dev/null || true
rm -f "$SERVICE_PATH"

if [ -f /data/rc.local ]; then
    sed -i "\|sh $SCRIPT_DIR/install.sh|d" /data/rc.local
    sed -i "\|bash $SCRIPT_DIR/install.sh|d" /data/rc.local
fi

echo "Removed the $SERVICE_NAME service."
echo "Configuration and logs were left in place."
