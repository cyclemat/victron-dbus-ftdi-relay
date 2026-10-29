#!/bin/sh
# Wird bei jedem Boot aus /data/rc.local aufgerufen.
# 1) udev-Regel: serial-starter ignoriert genau dieses Board (geht bei
#    Firmware-Updates verloren, wird hier wiederhergestellt)
# 2) Dienst-Symlink anlegen (/service wird bei jedem Boot neu erzeugt)
BASE=/data/dbus-ftdi-relay
RULE=/etc/udev/rules.d/zz-ftdi-relay.rules
SERIAL=$(sed -n 's/^serial[ \t]*=[ \t]*//p' "$BASE/config.ini" 2>/dev/null | head -n1 | tr -d '\r \t')

if [ -n "$SERIAL" ]; then
    LINE='ACTION=="add", ENV{ID_BUS}=="usb", ENV{ID_SERIAL_SHORT}=="'"$SERIAL"'", ENV{VE_SERVICE}="ignore"'
    if ! grep -qxF "$LINE" "$RULE" 2>/dev/null; then
        [ -x /opt/victronenergy/swupdate-scripts/remount-rw.sh ] && \
            /opt/victronenergy/swupdate-scripts/remount-rw.sh
        echo "$LINE" > "$RULE"
        udevadm control --reload-rules 2>/dev/null
        echo "udev-Regel fuer FTDI $SERIAL angelegt"
    fi
fi

ln -sfn "$BASE/service" /service/dbus-ftdi-relay
