<p align="center">
  <img src="dbus-Relais-Banner.png" alt="CycleMat Victron D-Bus FTDI Relay Banner" width="100%">
</p>

<h1 align="center">⚡ Victron D-Bus FTDI Relay</h1>
<h3 align="center">8-Kanal-USB-Relaissteuerung direkt in Victron Venus OS</h3>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Victron%20Venus%20OS-007ACC" alt="Platform: Victron Venus OS">
  <img src="https://img.shields.io/badge/Interface-FTDI%20USB-blue" alt="Interface: FTDI USB">
  <img src="https://img.shields.io/badge/Channels-8-orange" alt="Channels: 8">
  <img src="https://img.shields.io/badge/Integration-D--Bus%20%7C%20MQTT-00A6D6" alt="Integration: D-Bus and MQTT">
  <img src="https://img.shields.io/badge/Status-Testing-yellow" alt="Status: Testing">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/cyclemat/victron-dbus-ftdi-relay" alt="License"></a>
</p>

<p align="center">
  <strong>🇩🇪 Deutsch</strong> · <a href="README_EN.md">🇬🇧 English</a>
</p>

---

## 🚀 Über das Projekt

**Victron D-Bus FTDI Relay** bindet ein **8-Kanal-USB-Relaisboard mit FTDI-Chip** (FT245RL/FT232RL und ULN2803) als Schalter in **Venus OS** ein. Die Relais erscheinen in der Schalter-Ansicht der neuen Victron-Oberfläche (**gui-v2**) und können über **D-Bus, MQTT und Node-RED** geschaltet werden.

> Ziel: Ein kostengünstiges USB-Relaisboard ohne zusätzliche Python-Pakete direkt in die Victron-Bedienoberfläche integrieren.

**⚠️ Projektstatus: Testing.** Bitte zuerst ohne angeschlossene Verbraucher testen.

## ✨ Funktionen

- 🔌 **8 unabhängige Relaiskanäle** in Venus OS
- 🖥️ **Integration in gui-v2**, einschließlich benutzerdefinierter Namen, Gruppen und Sichtbarkeit
- 🎛️ **Schalter- oder Tasterbetrieb** pro Kanal
- 🔁 **D-Bus-Ansteuerung**, mit Zugriff über MQTT und Node-RED
- 🛠️ **Geführtes FTDI-Setup** mit Geräteauswahl und Invertierungstest
- 🔄 **Automatische Wiederverbindung** bei abgezogenem oder zurückgesetztem USB-Board
- 📦 **Kein pip und keine zusätzlichen Python-Bibliotheken**: FTDI-Bitbang über die Kernel-`usbfs`-Schnittstelle

---

## 📋 Voraussetzungen

- **Victron Venus OS** mit neuer **gui-v2** und Schalter-Ansicht; eine aktuelle Version verwenden (andere Projekte nennen v3.70 oder neuer).
- **Root-Zugang per SSH** zum GX-Gerät.
- Ein unterstütztes **8-Kanal-USB-Relaisboard** mit FT245R/FT232R (standardmäßig USB-Produkt-ID `6001`) und ULN2803.
- **12 V** Versorgung an `VCC/GND` des Relaisboards.

> **Wichtig:** Bei der ersten USB-Verbindung können ungewollte Schaltvorgänge auftreten. Verbraucher bis nach der Installation und dem Funktionstest abklemmen.

---

## 📦 Installation

Die Installationsdatei `dbus-ftdi-relay.tar.gz` zunächst auf das GX-Gerät übertragen (**auf deinem Computer ausführen**):

```sh
scp dbus-ftdi-relay.tar.gz root@<gx-ip>:/data/
```

Danach **per SSH auf dem GX-Gerät** ausführen:

```sh
cd /data
tar xzf dbus-ftdi-relay.tar.gz
cd dbus-ftdi-relay
sh install.sh
```

### 🧩 Geführtes Setup

Wenn noch kein Board konfiguriert ist, startet `install.sh` automatisch das Setup:

1. **FTDI-Geräte finden:** Seriennummer, Chip-Typ und USB-Port anzeigen; bereits von Venus-Diensten (z. B. `vedirect-interface`) verwendete Geräte markieren.
2. **Relaisboard auswählen:** Bei ungeeignetem Chip-Typ oder bereits belegtem Gerät ist die ausdrückliche Bestätigung `ja` erforderlich.
3. **Schaltlogik erkennen:** Nach Bestätigung, dass alle Relais aus sind, wird die Invertierung erkannt und **Relais 1 kurz geschaltet**. Das Ergebnis muss bestätigt werden.
4. **Konfiguration speichern:** Erst nach Bestätigung werden Seriennummer, `invert` und ggf. `product_ids` in `config.ini` geschrieben; andere Einträge und Kommentare bleiben erhalten.

Nach einem Board-Tausch lässt sich das Setup erneut starten:

```sh
cd /data/dbus-ftdi-relay
python3 dbus_ftdi_relay.py --setup
```

Hierfür wird ein laufender Dienst kurz angehalten; anschließend werden die udev-Regel aktualisiert und der Dienst neu gestartet.

---

## 🎮 Bedienung und Konfiguration

Die Relais erscheinen in der **Schalter-Ansicht von Venus OS gui-v2**. Pro Relais lassen sich **Name**, **Gruppe/Kachel**, **Sichtbarkeit** sowie **Typ** (Ein/Aus-Schalter oder Taster) einstellen. Diese Einstellungen werden in `localsettings` gespeichert und überleben Neustarts und Updates.

### 🧰 Nützliche Befehle

| Aufgabe | Befehl |
| --- | --- |
| FTDI-Geräte anzeigen | `python3 dbus_ftdi_relay.py --list` |
| Setup erneut starten | `python3 dbus_ftdi_relay.py --setup` |
| Alle Relais nacheinander testen | `python3 dbus_ftdi_relay.py --test` |
| Live-Log anzeigen | `tail -F /var/log/dbus-ftdi-relay/current \| tai64nlocal` |
| Dienst stoppen | `svc -d /service/dbus-ftdi-relay` |
| Dienst starten | `svc -u /service/dbus-ftdi-relay` |
| Dienst neu anstoßen | `svc -t /service/dbus-ftdi-relay` |
| Deinstallieren | `sh uninstall.sh` |

**Vor `--test` den Dienst mit `svc -d /service/dbus-ftdi-relay` stoppen.** Befehle aus dem Installationsordner ausführen.

### 🔁 Verhalten bei Neustart und Fehlern

| Situation | Verhalten |
| --- | --- |
| Dienststart / USB-Board wieder verbunden | `startup = restore`: letzter Zustand wird wiederhergestellt (Taster bleiben aus); `startup = off`: alle Relais aus |
| USB-Reset / Bitbang-Modus verloren | Erkennung beim nächsten Prüfzyklus (ca. 2 Sekunden), danach Neuinitialisierung |
| USB-Board abgezogen | Schalter in gui-v2 deaktiviert; automatische Wiederverbindung |
| Dienst wird gestoppt | Relais behalten ihren aktuellen Zustand |
| 12-V- oder USB-Versorgung fällt aus | Relais fallen hardwareseitig ab |

---

## 🔐 Wichtig: Venus OS `serial-starter`

Venus OS versucht, neu erkannte serielle USB-Geräte mit verschiedenen Treibern anzusprechen. Beim FTDI-Bitbang-Relaisboard könnte **jedes geschriebene Byte ein Relais schalten**. Das Projekt schützt das Board deshalb auf zwei Wegen:

1. **Gezielte udev-Regel:** `install.sh` nimmt genau das konfigurierte Board anhand seiner Seriennummer vom `serial-starter` aus. Andere FTDI-Geräte, beispielsweise VE.Direct-USB-Kabel, bleiben unberührt. `boot.sh` stellt die Regel beim Start auch nach Firmware-Updates wieder her.
2. **Trennung vom seriellen Kernel-Treiber:** Der Dienst löst `ftdi_sio` vom Board und bindet ihn während des Betriebs nicht wieder ein. Dadurch gibt es für dieses Board kein `/dev/ttyUSBx`.

Die **FTDI-Seriennummer ist verpflichtend**. Ohne Seriennummer startet der Dienst nicht. Automatisch erkannt werden nur FT245R/FT232R-Geräte mit Produkt-ID `6001`; andere Geräte müssen ausdrücklich ausgewählt bzw. freigegeben werden.

**Vor der erstmaligen Installation alle Verbraucher vom Relaisboard trennen.**

---

## 🧠 D-Bus-Schnittstelle

Der Dienst wird unter folgendem Namen bereitgestellt:

```text
com.victronenergy.switch.ftdirelay_<seriennummer>
```

Für alle acht Kanäle (`relay_1` bis `relay_8`) stehen diese Pfade zur Verfügung:

| D-Bus-Pfad | Funktion |
| --- | --- |
| `/SwitchableOutput/relay_N/State` | Schaltzustand `0/1` (schreibbar) |
| `/SwitchableOutput/relay_N/Status` | `0x00` aus, `0x09` an, `0x20` Board offline |
| `/SwitchableOutput/relay_N/Settings/CustomName` | Benutzerdefinierter Name |
| `/SwitchableOutput/relay_N/Settings/Group` | Gruppe/Kachel |
| `/SwitchableOutput/relay_N/Settings/Type` | `0` Taster, `1` Ein/Aus |
| `/SwitchableOutput/relay_N/Settings/ShowUIControl` | Sichtbarkeit des Schalters |

Beispiel: **Relais 1 einschalten** (Seriennummer ersetzen):

```sh
dbus -y com.victronenergy.switch.ftdirelay_<sn> /SwitchableOutput/relay_1/State SetValue 1
```

> **Hinweis zu VRM:** Nach Community-Berichten werden eigene Schalter-Dienste zwar in der lokalen Benutzeroberfläche und Remote Console angezeigt, aber möglicherweise nicht im VRM-Steuerungsbereich.

---

## ⚠️ Sicherheit und Haftung

- Jeden angeschlossenen Verbraucherkreis **separat absichern**.
- Die Relaiskontakte sind laut Board-Aufdruck für **10 A bei 30 V DC** ausgelegt; die tatsächlichen Grenzwerte des jeweiligen Boards beachten.
- Die Schaltung so auslegen, dass **abgefallene Relais einen sicheren Zustand** ergeben.
- **Keine sicherheitskritischen Verbraucher** ausschließlich über dieses USB-Relaisboard schalten.
- Vor Tests und Änderungen angeschlossene Lasten trennen.

Dies ist ein **privates Open-Source-Community-Projekt**, keine offizielle Victron-Erweiterung. Es besteht keine Verbindung zu Victron Energy oder FTDI. Die jeweiligen Marken gehören ihren Inhabern. Verwendung auf eigene Verantwortung.

---

## ❤️ Unterstützung & Spenden

Dieses Projekt ist frei nutzbar. Wenn du die Weiterentwicklung unterstützen möchtest, freue ich mich über eine freiwillige Spende:

**[☕ Via PayPal unterstützen](https://paypal.me/cyclemat)**

Keine Paywall, keine Verpflichtung – einfach Open Source.

## 🛠️ Feedback & Mitmachen

Fehlerberichte, Funktionswünsche und Pull Requests sind willkommen:

- [🐛 Fehler melden](https://github.com/cyclemat/victron-dbus-ftdi-relay/issues)
- [💡 Quellcode & Beiträge](https://github.com/cyclemat/victron-dbus-ftdi-relay)

---

<p align="center">
  <strong>Built with ❤️ by <a href="https://github.com/cyclemat">CycleMat</a></strong><br>
  <em>Mehr Kontrolle. Direkt in Venus OS.</em>
</p>
