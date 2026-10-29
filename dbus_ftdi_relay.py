#!/usr/bin/env python3
"""USB-Relaisboard (FTDI-Bitbang) -> Venus OS als com.victronenergy.switch.

* bis zu 8 Relais als Schalter in der Schalter-Ansicht von gui-v2
* Typ pro Relais: Ein/Aus (toggle) oder Taster (momentary)
* Namen, Gruppen, Typ und letzter Zustand liegen in localsettings
* liest die Pins zurueck und initialisiert das Board neu, falls es nach
  einem USB-Reset nicht mehr im Bitbang-Modus ist
* kein pip, keine Zusatzbibliotheken (usbfs per ctypes)
"""

import argparse
import configparser
import logging
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(1, os.path.join(HERE, "ext", "velib_python"))
sys.path.insert(1, "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python")

import ftdi_bitbang as fb  # noqa: E402

VERSION = "0.1.0"
STATE_CONNECTED = 0x100
STATUS_OFF = 0x00
STATUS_ON = 0x09
STATUS_DISABLED = 0x20
TYPE_MOMENTARY = 0
TYPE_TOGGLE = 1
VALID_TYPES = (1 << TYPE_MOMENTARY) | (1 << TYPE_TOGGLE)
PATH_RE = re.compile(r"^/SwitchableOutput/relay_(\d+)/")

log = logging.getLogger("ftdirelay")


# --------------------------------------------------------------- Konfiguration

class ConfigError(Exception):
    pass


class Config:
    def __init__(self, path):
        cp = configparser.ConfigParser()
        cp.read_dict({"general": {}, "names": {}})
        if not cp.read(path, encoding="utf-8"):
            raise ConfigError("Konfiguration nicht gefunden: %s" % path)
        g = cp["general"]
        self.serial = g.get("serial", "").strip()
        self.name = g.get("name", "USB-Relais")
        self.channels = g.getint("channels", 8)
        if not 1 <= self.channels <= 8:
            raise ConfigError("channels muss zwischen 1 und 8 liegen")
        self.invert = g.getboolean("invert", False)
        self.startup = g.get("startup", "restore").strip().lower()
        if self.startup not in ("restore", "off"):
            raise ConfigError("startup muss restore oder off sein")
        self.poll_interval = g.getint("poll_interval", 2)
        self.device_instance = g.getint("device_instance", 50)
        self.group = g.get("group", "").strip()
        self.log_level = g.get("log_level", "info")
        pids = g.get("product_ids", "")
        self.pids = tuple(int(p, 16) for p in pids.split(",") if p.strip()) or fb.DEFAULT_PIDS
        names = cp["names"]
        self.names = {n: names.get(str(n), "Relais %d" % n) for n in range(1, self.channels + 1)}

    @property
    def chanmask(self):
        return (1 << self.channels) - 1


# -------------------------------------------------------------------- Hardware

class Board:
    """Kapselt das FTDI-Geraet; logisches Bit 1 = Relais an."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.dev = None
        self.info = None

    @property
    def connected(self):
        return self.dev is not None

    def find(self):
        """Board per Seriennummer finden. Ohne Seriennummer nur, wenn genau
        ein passendes FTDI-Geraet da ist (nur fuer --test erlaubt)."""
        devs = fb.find_devices(self.cfg.pids)
        if self.cfg.serial:
            devs = [d for d in devs if d.serial == self.cfg.serial]
            return devs[0] if devs else None
        return devs[0] if len(devs) == 1 else None

    def _hw(self, logical):
        return (logical ^ 0xFF) & 0xFF if self.cfg.invert else logical & 0xFF

    def connect(self, info, logical):
        dev = fb.FtdiBitbang(info)
        dev.open()
        try:
            dev.set_bitbang()
            dev.write(self._hw(logical))
        except OSError:
            dev.close()
            raise
        self.dev, self.info = dev, info

    def reinit(self, logical):
        self.dev.set_bitbang()
        self.dev.write(self._hw(logical))

    def write(self, logical):
        self.dev.write(self._hw(logical))

    def read(self):
        return self._hw(self.dev.read_pins())  # XOR ist symmetrisch

    def close(self):
        if self.dev is not None:
            self.dev.close()
        self.dev = None


# --------------------------------------------------------------- Venus D-Bus

def _p(n, sub):
    return "/SwitchableOutput/relay_%d/%s" % (n, sub)


class RelayService:
    def __init__(self, cfg, board, bus=None):
        self.cfg = cfg
        self.board = board
        self.bus = bus
        self.svc = None
        self.settings = None
        self.desired = 0
        self._last_error = None

    # --- Registrierung (erst, wenn das Board einmal gefunden wurde)

    def _register(self, info):
        from settingsdevice import SettingsDevice
        from vedbus import VeDbusService
        import dbus

        if self.bus is None:
            self.bus = dbus.SystemBus()
        sid = re.sub(r"[^A-Za-z0-9]", "", info.serial) or re.sub(r"\W", "_", info.sysname)
        base = "/Settings/Devices/ftdirelay_%s" % sid
        spec = {
            "instance": [base + "/ClassAndVrmInstance", "switch:%d" % self.cfg.device_instance, 0, 0],
            "customname": [base + "/CustomName", self.cfg.name, 0, 0],
        }
        for n in range(1, self.cfg.channels + 1):
            r = "%s/Relay%d/" % (base, n)
            spec["name%d" % n] = [r + "CustomName", self.cfg.names[n], 0, 0]
            spec["group%d" % n] = [r + "Group", self.cfg.group, 0, 0]
            spec["type%d" % n] = [r + "Type", TYPE_TOGGLE, 0, 1]
            spec["show%d" % n] = [r + "ShowUIControl", 1, 0, 7]
            spec["last%d" % n] = [r + "LastState", 0, 0, 1]
        self.settings = SettingsDevice(self.bus, spec, self._on_setting)

        name = "com.victronenergy.switch.ftdirelay_" + sid
        try:
            svc = VeDbusService(name, bus=self.bus, register=False)
            deferred = True
        except TypeError:  # aeltere velib_python
            svc = VeDbusService(name, bus=self.bus)
            deferred = False
        svc.add_mandatory_paths(__file__, VERSION, "USB FTDI %s" % (info.serial or info.sysname),
                                self._instance(), 0xFFFF, "USB Relay Board (FTDI)", "-", "-", 0)
        svc.add_path("/Serial", info.serial)
        svc.add_path("/CustomName", self.settings["customname"], writeable=True,
                     onchangecallback=self._on_devname)
        svc.add_path("/State", STATE_CONNECTED)
        for n in range(1, self.cfg.channels + 1):
            svc.add_path(_p(n, "Name"), "Relais %d" % n)
            svc.add_path(_p(n, "State"), 0, writeable=True, onchangecallback=self._on_state)
            svc.add_path(_p(n, "Status"), STATUS_DISABLED)
            svc.add_path(_p(n, "Settings/CustomName"), self.settings["name%d" % n],
                         writeable=True, onchangecallback=self._on_text("name"))
            svc.add_path(_p(n, "Settings/Group"), self.settings["group%d" % n] or None,
                         writeable=True, onchangecallback=self._on_text("group"))
            svc.add_path(_p(n, "Settings/Type"), self._type(n), writeable=True,
                         onchangecallback=self._on_type)
            svc.add_path(_p(n, "Settings/ValidTypes"), VALID_TYPES)
            svc.add_path(_p(n, "Settings/ShowUIControl"), int(self.settings["show%d" % n]),
                         writeable=True, onchangecallback=self._on_show)
        if deferred:
            svc.register()
        self.svc = svc
        log.info("%s registriert (Instanz %d)", name, self._instance())

    def _instance(self):
        try:
            return int(str(self.settings["instance"]).split(":")[1])
        except (IndexError, ValueError):
            return self.cfg.device_instance

    def _type(self, n):
        return int(self.settings["type%d" % n])

    # --- Callbacks aus der GUI

    @staticmethod
    def _chan(path):
        m = PATH_RE.match(path)
        return int(m.group(1)) if m else None

    def _on_state(self, path, value):
        n = self._chan(path)
        try:
            value = int(value)
        except (TypeError, ValueError):
            return False
        if value not in (0, 1) or not self.board.connected:
            return False
        if not self._set_channel(n, value):
            return False
        if self._type(n) == TYPE_TOGGLE:
            self.settings["last%d" % n] = value
        return True

    def _set_channel(self, n, value):
        bit = 1 << (n - 1)
        new = (self.desired | bit) if value else (self.desired & ~bit)
        try:
            self.board.write(new)
        except OSError as err:
            log.warning("Schreiben fehlgeschlagen: %s", err)
            self._lost()
            return False
        self.desired = new
        self.svc[_p(n, "Status")] = STATUS_ON if value else STATUS_OFF
        return True

    def _on_text(self, key):
        def cb(path, value):
            self.settings["%s%d" % (key, self._chan(path))] = str(value or "")
            return True
        return cb

    def _on_type(self, path, value):
        n = self._chan(path)
        try:
            value = int(value)
        except (TypeError, ValueError):
            return False
        if value not in (TYPE_MOMENTARY, TYPE_TOGGLE):
            return False
        self.settings["type%d" % n] = value
        if value == TYPE_MOMENTARY and self.desired & (1 << (n - 1)):
            # Spec: beim Wechsel auf Taster den Ausgang inaktiv schalten
            if self.board.connected and self._set_channel(n, 0):
                self.svc[_p(n, "State")] = 0
            self.settings["last%d" % n] = 0
        return True

    def _on_show(self, path, value):
        self.settings["show%d" % self._chan(path)] = int(value)
        return True

    def _on_devname(self, path, value):
        self.settings["customname"] = str(value)
        return True

    def _on_setting(self, setting, old, new):
        if self.svc is None:
            return
        m = re.match(r"^(name|group|type|show)(\d+)$", setting)
        if setting == "instance":
            self.svc["/DeviceInstance"] = self._instance()
        elif setting == "customname":
            self.svc["/CustomName"] = new
        elif m:
            sub = {"name": "Settings/CustomName", "group": "Settings/Group",
                   "type": "Settings/Type", "show": "Settings/ShowUIControl"}[m.group(1)]
            self.svc[_p(int(m.group(2)), sub)] = (new or None) if m.group(1) == "group" else new

    # --- Zyklische Pruefung

    def _startup_value(self):
        if self.cfg.startup != "restore":
            return 0
        value = 0
        for n in range(1, self.cfg.channels + 1):
            if self._type(n) == TYPE_TOGGLE and int(self.settings["last%d" % n]):
                value |= 1 << (n - 1)
        return value

    def _publish_all(self):
        for n in range(1, self.cfg.channels + 1):
            on = bool(self.desired & (1 << (n - 1)))
            self.svc[_p(n, "State")] = int(on)
            self.svc[_p(n, "Status")] = STATUS_ON if on else STATUS_OFF
        self.svc["/Connected"] = 1

    def _lost(self):
        self.board.close()
        if self.svc is not None:
            self.svc["/Connected"] = 0
            for n in range(1, self.cfg.channels + 1):
                self.svc[_p(n, "Status")] = STATUS_DISABLED

    def _note(self, msg):
        if msg != self._last_error:
            log.warning("%s", msg)
            self._last_error = msg

    def poll(self):
        try:
            if not self.board.connected:
                info = self.board.find()
                if info is None:
                    self._note("Kein passendes FTDI-Board gefunden%s" % (
                        " (Seriennummer %s)" % self.cfg.serial if self.cfg.serial else ""))
                    self._lost()
                    return True
                if self.svc is None:
                    self._register(info)
                start = self._startup_value()
                self.board.connect(info, start)
                self.desired = start
                self._publish_all()
                self._last_error = None
                log.info("Board %s verbunden, Relais 0x%02X", info.serial or info.sysname, start)
            else:
                pins = self.board.read()
                if (pins ^ self.desired) & self.cfg.chanmask:
                    log.warning("Board meldet 0x%02X statt 0x%02X, initialisiere neu",
                                pins & self.cfg.chanmask, self.desired)
                    self.board.reinit(self.desired)
        except OSError as err:
            self._note("USB-Fehler: %s" % err)
            self._lost()
        return True


# ------------------------------------------------------------------------ CLI

def cmd_list(pids):
    """Zeigt ALLE FTDI-Geraete; * = wird vom Dienst beruecksichtigt."""
    devs = fb.find_devices(None)
    if not devs:
        print("Kein FTDI-Geraet (Hersteller-ID 0403) gefunden.")
        return 1
    print("  %-12s %-9s %-10s %-10s %s" % ("Seriennr.", "VID:PID", "USB-Port", "Treiber", "Produkt"))
    for d in devs:
        mark = "*" if d.pid in pids else " "
        print("%s %-12s 0403:%04x %-10s %-10s %s" % (mark, d.serial or "-", d.pid, d.sysname,
                                                    d.driver, d.product))
    if any(d.pid not in pids for d in devs):
        print("\nOhne * = andere Product-ID, wird nicht angefasst. Nur wenn eines davon")
        print("sicher dein Relaisboard ist: seine ID in config.ini unter product_ids")
        print("ergaenzen (product_ids = 6001, <ID des Boards>) und serial= setzen.")
    return 0


def cmd_test(cfg):
    board = Board(cfg)
    info = board.find()
    if info is None:
        if not cfg.serial and len(fb.find_devices(cfg.pids)) > 1:
            print("Mehrere FTDI-Geraete gefunden. Bitte serial= in config.ini setzen (--list).")
        else:
            print("Kein passendes FTDI-Board gefunden.")
        return 1
    print("Teste %s (%s). Der Dienst muss gestoppt sein!" % (info.serial or "-", info.sysname))
    board.connect(info, 0)
    try:
        for n in range(1, cfg.channels + 1):
            board.write(1 << (n - 1))
            time.sleep(0.05)
            print("  Relais %d an  (Board meldet 0x%02X)" % (n, board.read() & cfg.chanmask))
            time.sleep(1.0)
            board.write(0)
            time.sleep(0.3)
    finally:
        board.write(0)
        board.close()
    print("Fertig, alle Relais aus.")
    return 0


# ---------------------------------------------------------------------- Setup

SERVICE_DIR = "/service/dbus-ftdi-relay"


def _tty_of(info, sysfs="/sys/bus/usb/devices"):
    import glob
    hits = glob.glob(os.path.join(sysfs, info.sysname, info.sysname + ":1.0", "ttyUSB*"))
    return os.path.basename(hits[0]) if hits else None


def _venus_users(tty, service_root="/service"):
    """Venus-Dienste, die serial-starter fuer dieses tty gestartet hat."""
    import glob
    if not tty:
        return []
    return [os.path.basename(p).rsplit(".", 1)[0]
            for p in glob.glob(os.path.join(service_root, "*." + tty))]


def update_config(path, values, example=None):
    """Setzt Schluessel in [general], Kommentare und Reihenfolge bleiben erhalten."""
    if not os.path.exists(path):
        import shutil
        shutil.copy(example or os.path.join(HERE, "config.example.ini"), path)
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    def section_at(i):
        sec = None
        for line in lines[:i + 1]:
            st = line.strip()
            if st.startswith("[") and st.endswith("]"):
                sec = st[1:-1].strip().lower()
        return sec

    key_re = re.compile(r"^\s*(#\s*)?([A-Za-z_]+)\s*=")

    def find(key, want_comment):
        hits = []
        for i, line in enumerate(lines):
            m = key_re.match(line)
            if (m and m.group(2) == key and bool(m.group(1)) == want_comment
                    and section_at(i) == "general"):
                hits.append(i)
        return hits

    for key, value in values.items():
        new = "%s = %s" % (key, value)
        active = find(key, False)
        commented = find(key, True)
        if active:
            lines[active[0]] = new
        elif commented:
            lines[commented[0]] = new
        else:
            hdr = next((i for i, l in enumerate(lines) if l.strip().lower() == "[general]"), None)
            if hdr is None:
                lines[:0] = ["[general]", new, ""]
            else:
                lines.insert(hdr + 1, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _ask(prompt):
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return "q"


def _svc(action):
    if os.path.exists(SERVICE_DIR):
        os.system("svc %s %s 2>/dev/null" % (action, SERVICE_DIR))
        return True
    return False


def cmd_setup(config_path):
    """Board auswaehlen, per Klick bestaetigen, Konfiguration schreiben."""
    devs = fb.find_devices(None)
    if not devs:
        print("Kein FTDI-Geraet gefunden. Board eingesteckt?")
        return 1
    print("Gefundene FTDI-Geraete:\n")
    rows = []
    for i, d in enumerate(devs, 1):
        tty = _tty_of(d)
        users = _venus_users(tty)
        note = []
        if d.pid not in fb.DEFAULT_PIDS:
            note.append("anderer Chip-Typ")
        if users:
            note.append("in Benutzung durch: " + ", ".join(users))
        rows.append((d, tty, users))
        print("  [%d] Seriennr. %-10s 0403:%04x  Port %-8s %-20s %s" % (
            i, d.serial or "-", d.pid, d.sysname, d.product[:20],
            ("<- " + "; ".join(note)) if note else ""))
    choice = _ask("\nWelches ist das Relaisboard? Nummer eingeben (q = Abbruch): ")
    if not choice.isdigit() or not 1 <= int(choice) <= len(rows):
        print("Abgebrochen, nichts geaendert.")
        return 1
    info, tty, users = rows[int(choice) - 1]
    if not info.serial:
        print("Dieses Geraet hat keine Seriennummer, automatische Zuordnung nicht moeglich.")
        return 1
    if info.pid not in fb.DEFAULT_PIDS or users:
        print("\nACHTUNG: Der Test schaltet den Chip in den Bitbang-Modus. Ist das NICHT das")
        print("Relaisboard (z. B. ein VE.Direct-Kabel), funktioniert es danach erst nach")
        print("erneutem Einstecken wieder.")
        if _ask("Wirklich dieses Geraet testen? 'ja' eintippen: ") != "ja":
            print("Abgebrochen, nichts geaendert.")
            return 1

    stopped = _svc("-d")
    if stopped:
        time.sleep(1.5)
    dev = fb.FtdiBitbang(info)
    try:
        dev.open()
        dev.set_bitbang()
        dev.write(0x00)
        time.sleep(0.3)
        invert = not _ask("\nSind jetzt ALLE Relais aus (keine Relais-LED an)? [j/n] ").startswith("j")
        off = 0xFF if invert else 0x00
        dev.write(off)
        time.sleep(0.3)
        print("Schalte Relais 1 fuer 1,5 s ein ...")
        dev.write(off ^ 0x01)
        time.sleep(1.5)
        dev.write(off)
        ok = _ask("Hat Relais 1 eben angezogen? [j/n] ").startswith("j")
    except OSError as err:
        print("USB-Fehler: %s" % err)
        ok = False
    finally:
        dev.close()
        if stopped:
            _svc("-u")
    if not ok:
        print("Nicht bestaetigt, config.ini bleibt unveraendert.")
        return 1

    values = {"serial": info.serial, "invert": "true" if invert else "false"}
    if info.pid not in fb.DEFAULT_PIDS:
        values["product_ids"] = "6001, %04x" % info.pid
    update_config(config_path, values)
    print("\nconfig.ini aktualisiert: %s" % ", ".join("%s = %s" % kv for kv in values.items()))
    if os.path.exists(SERVICE_DIR):
        os.system("sh %s 2>/dev/null" % os.path.join(HERE, "boot.sh"))  # udev-Regel
        _svc("-t")
        print("Dienst neu gestartet.")
    else:
        print("Naechster Schritt: sh %s" % os.path.join(HERE, "install.sh"))
    return 0


def run_service(cfg):
    import dbus.mainloop.glib
    from gi.repository import GLib
    import signal

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    board = Board(cfg)
    service = RelayService(cfg, board)
    mainloop = GLib.MainLoop()

    def on_signal(*_):
        mainloop.quit()
        return False

    for sig in (signal.SIGTERM, signal.SIGINT):
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, sig, on_signal)
    log.info("dbus-ftdi-relay %s gestartet, %d Kanaele", VERSION, cfg.channels)
    service.poll()
    GLib.timeout_add_seconds(cfg.poll_interval, service.poll)
    try:
        mainloop.run()
    finally:
        board.close()  # Relais bleiben stehen; Interface wird freigegeben


def main():
    ap = argparse.ArgumentParser(description="FTDI-USB-Relaisboard fuer Venus OS")
    ap.add_argument("-c", "--config", default=os.path.join(HERE, "config.ini"))
    ap.add_argument("--list", action="store_true", help="FTDI-Geraete auflisten")
    ap.add_argument("--setup", action="store_true",
                    help="Board auswaehlen, testen und in config.ini eintragen")
    ap.add_argument("--test", action="store_true", help="Relais nacheinander schalten (Dienst vorher stoppen)")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    if args.setup:
        return cmd_setup(args.config)
    if args.list:
        try:
            pids = Config(args.config).pids
        except ConfigError:
            pids = fb.DEFAULT_PIDS
        return cmd_list(pids)
    try:
        cfg = Config(args.config)
    except ConfigError as err:
        logging.basicConfig(level=logging.INFO)
        log.error("%s", err)
        if not args.test:
            time.sleep(300)  # nicht im Sekundentakt von daemontools neu starten
        return 1
    logging.basicConfig(level=logging.DEBUG if args.debug else
                        getattr(logging, cfg.log_level.upper(), logging.INFO),
                        format="%(levelname)s %(name)s: %(message)s")
    if args.test:
        return cmd_test(cfg)
    if not cfg.serial:
        log.error("serial= ist leer. Ohne Seriennummer koennte der Dienst ein anderes "
                  "FTDI-Geraet (z. B. VE.Direct-Kabel) erwischen. Mit --list ablesen.")
        time.sleep(300)
        return 1
    run_service(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
