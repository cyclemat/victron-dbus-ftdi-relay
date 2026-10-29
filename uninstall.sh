#!/bin/sh
BASE=/data/dbus-ftdi-relay
SVC=/service/dbus-ftdi-relay
if [ -e "$SVC" ]; then
    svc -dx "$SVC" "$SVC/log" 2>/dev/null
    rm -f "$SVC"
fi
if [ -f /data/rc.local ]; then
    grep -vF "$BASE/boot.sh" /data/rc.local > /tmp/rc.local.$$
    cat /tmp/rc.local.$$ > /data/rc.local
    rm -f /tmp/rc.local.$$
fi
if [ -f /etc/udev/rules.d/zz-ftdi-relay.rules ]; then
    [ -x /opt/victronenergy/swupdate-scripts/remount-rw.sh ] && \
        /opt/victronenergy/swupdate-scripts/remount-rw.sh
    rm -f /etc/udev/rules.d/zz-ftdi-relay.rules
    udevadm control --reload-rules 2>/dev/null
fi
echo ">> Dienst entfernt. Dateien liegen weiter in $BASE."
