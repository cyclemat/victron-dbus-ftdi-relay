#!/bin/sh
set -e
BASE=/data/dbus-ftdi-relay
LINE="sh $BASE/boot.sh"
cd "$BASE"
chmod +x dbus_ftdi_relay.py boot.sh install.sh uninstall.sh service/run service/log/run
if [ ! -f config.ini ]; then
    cp config.example.ini config.ini
    echo ">> config.ini angelegt. Seriennummer eintragen (python3 $BASE/dbus_ftdi_relay.py --list)"
fi
[ -f /data/rc.local ] || printf '#!/bin/sh\n' > /data/rc.local
chmod +x /data/rc.local
grep -qxF "$LINE" /data/rc.local || echo "$LINE" >> /data/rc.local
sh "$BASE/boot.sh"
echo ">> Dienst eingerichtet. Log: tail -F /var/log/dbus-ftdi-relay/current | tai64nlocal"
