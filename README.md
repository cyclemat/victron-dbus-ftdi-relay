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
sh install.sh
```

`install.sh` startet automatisch das Setup, solange noch kein Board eingetragen ist. Das Setup läuft in vier Schritten ab:

1. Es listet alle FTDI-Geräte mit Seriennummer, Chip-Typ und USB-Port. Geräte, die gerade ein Venus-Dienst nutzt (z. B. `vedirect-interface`), sind markiert.
2. Du wählst das Relaisboard per Nummer aus. Fremde Chip-Typen oder belegte Geräte werden erst nach der ausdrücklichen Eingabe `ja` angefasst.
3. Es fragt, ob alle Relais aus sind. Daraus erkennt es, ob das Board invertiert schaltet. Dann lässt es Relais 1 kurz anziehen, und du bestätigst das.
4. Nur nach deiner Bestätigung schreibt es Seriennummer, `invert` und bei Bedarf `product_ids` in die `config.ini`. Kommentare und alle anderen Einträge bleiben dabei erhalten.

Später, etwa nach einem Board-Tausch, startest du das Setup jederzeit erneut mit `python3 dbus_ftdi_relay.py --setup`. Ein laufender Dienst wird dafür kurz angehalten, danach aktualisiert das Setup die udev-Regel und startet den Dienst neu.

Weitere Befehle:

- `python3 dbus_ftdi_relay.py --list`: alle FTDI-Geräte anzeigen.
- `python3 dbus_ftdi_relay.py --test`: alle Relais nacheinander schalten. Den Dienst vorher mit `svc -d` stoppen.

**Log:** `tail -F /var/log/dbus-ftdi-relay/current | tai64nlocal`

**Steuerung:** `svc -d|-u|-t /service/dbus-ftdi-relay`

**Entfernen:** `sh uninstall.sh`

Die Seriennummer ist Pflicht, denn ohne sie startet der Dienst nicht. So fasst er nie ein anderes FTDI-Gerät wie ein VE.Direct-USB-Kabel an. Automatisch berücksichtigt werden nur FT245R/FT232R (Produkt-ID 6001).

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
