#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SERVICE_NAME="$(basename "$SCRIPT_DIR")"
SERVICE_PATH="/service/$SERVICE_NAME"
LOG_PATH="/data/log/$SERVICE_NAME"
RC_LOCAL="/data/rc.local"

echo "Installing $SERVICE_NAME from $SCRIPT_DIR"

if [ ! -f "$SCRIPT_DIR/config.ini" ]; then
    cp "$SCRIPT_DIR/config.example.ini" "$SCRIPT_DIR/config.ini"
    echo "Created $SCRIPT_DIR/config.ini"
    echo "Add your Hypon Cloud credentials before starting the service."
fi

chmod 755 "$SCRIPT_DIR/dbus-hypon-pv.py"
chmod 755 "$SCRIPT_DIR/install.sh"
chmod 755 "$SCRIPT_DIR/restart.sh"
chmod 755 "$SCRIPT_DIR/uninstall.sh"
chmod 755 "$SCRIPT_DIR/service/run"
chmod 755 "$SCRIPT_DIR/service/log/run"

mkdir -p "$LOG_PATH"

if [ -L "$SERVICE_PATH" ]; then
    CURRENT_TARGET="$(readlink -f "$SERVICE_PATH" || true)"
    EXPECTED_TARGET="$(readlink -f "$SCRIPT_DIR/service")"

    if [ "$CURRENT_TARGET" != "$EXPECTED_TARGET" ]; then
        rm -f "$SERVICE_PATH"
        ln -s "$SCRIPT_DIR/service" "$SERVICE_PATH"
    fi
elif [ -e "$SERVICE_PATH" ]; then
    echo "$SERVICE_PATH exists and is not a symlink."
    exit 1
else
    ln -s "$SCRIPT_DIR/service" "$SERVICE_PATH"
fi

if [ ! -f "$RC_LOCAL" ]; then
    printf '#!/bin/sh\n\n' > "$RC_LOCAL"
    chmod 755 "$RC_LOCAL"
fi

STARTUP_LINE="sh $SCRIPT_DIR/install.sh"
grep -qxF "$STARTUP_LINE" "$RC_LOCAL" || echo "$STARTUP_LINE" >> "$RC_LOCAL"

if grep -q "YOUR_HYPON_" "$SCRIPT_DIR/config.ini"; then
    echo
    echo "Installation finished, but the service was not started."
    echo "Edit $SCRIPT_DIR/config.ini, then run $SCRIPT_DIR/restart.sh"
    exit 0
fi

svc -u "$SERVICE_PATH"
sleep 1
svstat "$SERVICE_PATH"
