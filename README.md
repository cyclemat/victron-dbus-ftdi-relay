# dbus-ftdi-relay

8-Kanal-USB-Relaisboard mit FTDI-Chip (FT245RL/FT232RL + ULN2803) als Schalter in Venus OS. Die Relais erscheinen in der Schalter-Ansicht der neuen Oberfläche (gui-v2) und sind über D-Bus, MQTT und Node-RED schaltbar.

Der Dienst braucht kein pip und keine Zusatzbibliotheken. Der FTDI-Chip wird per Bitbang direkt über die usbfs-Schnittstelle des Kernels angesprochen.

## Voraussetzungen

- Venus OS mit gui-v2. Die Schalter-Ansicht ist relativ neu, also eine aktuelle Version nehmen (andere Projekte nennen v3.70 oder neuer).
- Root-Zugang per SSH.
- 12 V an VCC/GND des Boards.

## Installation

```sh
scp dbus-ftdi-relay.tar.gz root@<gx-ip>:/data/
cd /data && tar xzf dbus-ftdi-relay.tar.gz && cd dbus-ftdi-relay
cp config.example.ini config.ini

python3 dbus_ftdi_relay.py --list      # Seriennummer des Boards ablesen
vi config.ini                          # serial = <Seriennummer> eintragen
python3 dbus_ftdi_relay.py --test      # Relais 1–8 klicken nacheinander
sh install.sh                          # Dienst + udev-Regel einrichten
```

**Log:** `tail -F /var/log/dbus-ftdi-relay/current | tai64nlocal`

**Steuerung:** `svc -d|-u|-t /service/dbus-ftdi-relay`

**Entfernen:** `sh uninstall.sh`

Klicken beim Test alle Relais gleichzeitig, wenn sie aus sein sollten, ist das Board invertiert. Dann `invert = true` setzen.

## Wichtig: serial-starter

Venus probiert jedes neue serielle USB-Gerät mit seinen Treibern durch. Im Bitbang-Modus würde jedes geschriebene Byte Relais schalten. Deshalb gibt es zwei Schutzmaßnahmen:

1. **Die udev-Regel aus `install.sh`.** Sie nimmt genau dieses Board (per Seriennummer) vom serial-starter aus. Andere FTDI-Adapter, etwa ein VE.Direct-Kabel, bleiben unberührt. Nach Firmware-Updates legt `boot.sh` die Regel beim Booten neu an.
2. **Der Dienst koppelt den Kernel-Treiber `ftdi_sio` ab und hängt ihn bewusst nie wieder an.** Solange der Dienst läuft, existiert kein `/dev/ttyUSBx` für das Board.

Bis zur Installation, also beim allerersten Einstecken, kann der serial-starter das Board noch kurz ansprechen. Deshalb vorher die Verbraucher abklemmen.

## Verhalten

| Situation | Was passiert |
| --- | --- |
| Dienst startet / Board wieder eingesteckt | `startup = restore`: letzter Zustand (Taster immer aus), `off`: alles aus |
| USB-Reset, Board fällt aus dem Bitbang-Modus | wird beim nächsten Prüfzyklus (2 s) erkannt und neu initialisiert |
| Board abgezogen | Schalter werden in der GUI als deaktiviert angezeigt, der Dienst verbindet automatisch neu |
| Dienst wird gestoppt | Relais bleiben, wie sie sind |
| 12 V oder USB-Strom weg | Relais fallen ab (Hardware) |

Pro Relais lassen sich Name, Gruppe (Kachel), Sichtbarkeit und Typ (Ein/Aus oder Taster) in der GUI einstellen. Die Einstellungen landen in localsettings und überleben Neustarts und Updates.

## Sicherheit

- Jeden Verbraucher-Kreis einzeln absichern. Die Kontakte sind laut Aufdruck für 10 A bei 30 V DC ausgelegt.
- Kreise so planen, dass "Relais abgefallen" ein sicherer Zustand ist.
- Nichts Kritisches allein über das USB-Board schalten.

## D-Bus

Der Dienst heißt `com.victronenergy.switch.ftdirelay_<seriennummer>`. Pro Kanal (`relay_1` … `relay_8`) gibt es diese Pfade:

| Pfad | |
| --- | --- |
| `/SwitchableOutput/relay_N/State` | 0/1, schreibbar |
| `/SwitchableOutput/relay_N/Status` | 0x00 aus, 0x09 an, 0x20 Board offline |
| `/SwitchableOutput/relay_N/Settings/CustomName` | Name |
| `/SwitchableOutput/relay_N/Settings/Group` | Kachel |
| `/SwitchableOutput/relay_N/Settings/Type` | 0 Taster, 1 Ein/Aus |
| `/SwitchableOutput/relay_N/Settings/ShowUIControl` | Sichtbarkeit |

Beispiel: `dbus -y com.victronenergy.switch.ftdirelay_<sn> /SwitchableOutput/relay_1/State SetValue 1`

Hinweis: Nach Berichten aus der Community tauchen eigene Schalter-Dienste bisher nicht im VRM-Steuerungsbereich auf, lokal und in der Remote Console aber schon.
