<p align="center">
  <img src="dbus-Relais-Banner.png" alt="CycleMat Victron D-Bus FTDI Relay Banner" width="100%">
</p>

<h1 align="center">⚡ Victron D-Bus FTDI Relay</h1>
<h3 align="center">8-channel USB relay control directly in Victron Venus OS</h3>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Victron%20Venus%20OS-007ACC" alt="Platform: Victron Venus OS">
  <img src="https://img.shields.io/badge/Interface-FTDI%20USB-blue" alt="Interface: FTDI USB">
  <img src="https://img.shields.io/badge/Channels-8-orange" alt="Channels: 8">
  <img src="https://img.shields.io/badge/Integration-D--Bus%20%7C%20MQTT-00A6D6" alt="Integration: D-Bus and MQTT">
  <img src="https://img.shields.io/badge/Status-Testing-yellow" alt="Status: Testing">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/cyclemat/victron-dbus-ftdi-relay" alt="License"></a>
</p>

<p align="center">
  <a href="README.md">🇩🇪 Deutsch</a> · <strong>🇬🇧 English</strong>
</p>

---

## 🚀 About this project

**Victron D-Bus FTDI Relay** integrates an **8-channel USB relay board with an FTDI chip** (FT245RL/FT232RL and ULN2803) as switches in **Venus OS**. Relays appear in the switch view of the new Victron interface (**gui-v2**) and can be controlled via **D-Bus, MQTT and Node-RED**.

> Goal: Integrate an affordable USB relay board directly into Victron's UI without additional Python packages.

**⚠️ Project status: Testing.** Test without connected loads first.

## ✨ Features

- 🔌 **8 independent relay channels** in Venus OS
- 🖥️ **gui-v2 integration**, including custom names, groups and visibility
- 🎛️ **Switch or momentary-button mode** per channel
- 🔁 **D-Bus control** with access through MQTT and Node-RED
- 🛠️ **Guided FTDI setup** with device selection and polarity detection
- 🔄 **Automatic reconnection** after USB removal or reset
- 📦 **No pip or extra Python dependencies**: FTDI bitbang via the kernel `usbfs` interface

---

## 📋 Requirements

- **Victron Venus OS** with the new **gui-v2** switch view; use a current version (other projects reference v3.70 or newer).
- **Root SSH access** to the GX device.
- A compatible **8-channel USB relay board** with FT245R/FT232R (default USB product ID `6001`) and ULN2803.
- **12 V power** connected to the relay board's `VCC/GND`.

> **Important:** On first USB connection, unintended switching is possible. Disconnect all loads until installation and initial testing are complete.

---

## 📦 Installation

Transfer `dbus-ftdi-relay.tar.gz` to the GX device (**run on your computer**):

```sh
scp dbus-ftdi-relay.tar.gz root@<gx-ip>:/data/
```

Then **connect over SSH to the GX device** and run:

```sh
cd /data
tar xzf dbus-ftdi-relay.tar.gz
cd dbus-ftdi-relay
sh install.sh
```

### 🧩 Guided setup

When no board has been configured, `install.sh` launches setup automatically:

1. **Discover FTDI devices:** List serial numbers, chip types and USB ports; identify devices used by Venus services (e.g. `vedirect-interface`).
2. **Select the relay board:** Unsupported chip types or devices already in use require explicit confirmation by typing `ja`.
3. **Determine relay polarity:** After confirming all relays are off, the setup detects inversion, **briefly activates relay 1**, and requests confirmation.
4. **Save configuration:** Only after confirmation are serial number, `invert` and, if needed, `product_ids` written to `config.ini`. Other entries and comments are preserved.

To rerun setup after replacing a board:

```sh
cd /data/dbus-ftdi-relay
python3 dbus_ftdi_relay.py --setup
```

The running service is briefly stopped, then the udev rule is updated and the service restarted.

---

## 🎮 Operation and configuration

Relays appear in the **Venus OS gui-v2 switch view**. Each relay supports configurable **name**, **group/tile**, **visibility** and **type** (on/off or momentary). These settings are stored in `localsettings` and survive restarts and updates.

### 🧰 Useful commands

| Action | Command |
| --- | --- |
| List FTDI devices | `python3 dbus_ftdi_relay.py --list` |
| Run setup again | `python3 dbus_ftdi_relay.py --setup` |
| Test all relays sequentially | `python3 dbus_ftdi_relay.py --test` |
| Follow live logs | `tail -F /var/log/dbus-ftdi-relay/current \| tai64nlocal` |
| Stop service | `svc -d /service/dbus-ftdi-relay` |
| Start service | `svc -u /service/dbus-ftdi-relay` |
| Signal/restart service | `svc -t /service/dbus-ftdi-relay` |
| Uninstall | `sh uninstall.sh` |

**Stop the service with `svc -d /service/dbus-ftdi-relay` before running `--test`.** Run commands from the installation directory.

### 🔁 Startup and failure behavior

| Situation | Behavior |
| --- | --- |
| Service starts / USB board reconnects | `startup = restore`: restore last state (momentary channels stay off); `startup = off`: all relays off |
| USB reset / bitbang mode lost | Detected on next check (about 2 seconds), then reinitialized |
| USB board unplugged | gui-v2 switches shown as disabled; automatic reconnect |
| Service stops | Relays retain their current state |
| 12 V or USB power lost | Relays physically drop out |

---

## 🔐 Important: Venus OS `serial-starter`

Venus OS probes newly connected serial USB devices using different drivers. On an FTDI bitbang relay board, **every written byte could switch relays**. Two safeguards are used:

1. **Targeted udev rule:** `install.sh` excludes only the configured board from `serial-starter`, identified by its serial number. Other FTDI devices, such as VE.Direct USB adapters, are unaffected. `boot.sh` recreates the rule on boot, including after firmware updates.
2. **Serial driver detachment:** The service detaches `ftdi_sio` and does not reattach it while running. As a result, the board does not expose a `/dev/ttyUSBx` device.

An **FTDI serial number is mandatory**; the service will not start without one. Only FT245R/FT232R devices with product ID `6001` are considered automatically; using others requires explicit selection or approval.

**Disconnect loads before installing the board for the first time.**

---

## 🧠 D-Bus interface

The service is exposed under:

```text
com.victronenergy.switch.ftdirelay_<serial_number>
```

Each of the eight channels (`relay_1` through `relay_8`) provides:

| D-Bus path | Description |
| --- | --- |
| `/SwitchableOutput/relay_N/State` | Switch state `0/1` (writable) |
| `/SwitchableOutput/relay_N/Status` | `0x00` off, `0x09` on, `0x20` board offline |
| `/SwitchableOutput/relay_N/Settings/CustomName` | Custom name |
| `/SwitchableOutput/relay_N/Settings/Group` | Group/tile |
| `/SwitchableOutput/relay_N/Settings/Type` | `0` momentary, `1` on/off |
| `/SwitchableOutput/relay_N/Settings/ShowUIControl` | Switch visibility |

Example: **Turn on relay 1** (replace the serial number):

```sh
dbus -y com.victronenergy.switch.ftdirelay_<sn> /SwitchableOutput/relay_1/State SetValue 1
```

> **VRM note:** According to community reports, custom switch services may appear in the local UI and Remote Console but not in VRM's control area.

---

## ⚠️ Safety and disclaimer

- **Fuse each load circuit separately.**
- The relay contacts are marked **10 A at 30 V DC** on the referenced board; follow the actual limits of your specific hardware.
- Design circuits so that **de-energized relays represent a safe state**.
- **Do not control safety-critical loads** exclusively through this USB relay board.
- Disconnect loads before testing or modifying the setup.

This is an **independent community open-source hobby project**, not an official Victron extension. It is not affiliated with Victron Energy or FTDI. All trademarks belong to their respective owners. Use at your own risk.

---

## ❤️ Support & donations

This project is free to use. If you would like to support further development, optional donations are appreciated:

**[☕ Support via PayPal](https://paypal.me/cyclemat)**

No paywalls, no obligations – just open source.

## 🛠️ Feedback & contributions

Bug reports, feature suggestions and pull requests are welcome:

- [🐛 Report an issue](https://github.com/cyclemat/victron-dbus-ftdi-relay/issues)
- [💡 Source code & contributions](https://github.com/cyclemat/victron-dbus-ftdi-relay)

---

<p align="center">
  <strong>Built with ❤️ by <a href="https://github.com/cyclemat">CycleMat</a></strong><br>
  <em>More control. Directly in Venus OS.</em>
</p>
