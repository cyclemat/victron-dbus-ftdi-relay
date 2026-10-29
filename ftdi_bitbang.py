"""FTDI-Bitbang (FT245R/FT232R) ueber Linux-usbfs, ohne libftdi oder pyusb.

Das Relaisboard haengt mit D0..D7 des FTDI-Chips direkt am ULN2803.
Im asynchronen Bitbang-Modus setzt jedes geschriebene Byte diese 8 Pins.

Wichtig: Der Kernel-Treiber ftdi_sio wird beim Oeffnen abgekoppelt und
bewusst NICHT wieder angehaengt. Sonst entstuende wieder ein /dev/ttyUSBx,
und alles, was darauf schreibt (z. B. Venus' serial-starter), wuerde im
Bitbang-Modus direkt Relais schalten.
"""

import ctypes
import errno
import glob
import os
from collections import namedtuple

FTDI_VID = 0x0403
# Nur FT245R/FT232R. Andere FTDI-Typen (z. B. FT231X im VE.Direct-USB-Kabel)
# werden nie automatisch angefasst; bei Bedarf per product_ids ergaenzen.
DEFAULT_PIDS = (0x6001,)

# FTDI-Vendor-Requests (wie libftdi)
REQ_OUT = 0x40
REQ_IN = 0xC0
SIO_SET_BITMODE = 0x0B
SIO_READ_PINS = 0x0C
BITMODE_RESET = 0x00
BITMODE_BITBANG = 0x01
INDEX_A = 1          # Interface A
EP_OUT = 0x02        # Bulk-OUT-Endpoint

# ---------------------------------------------------------------- usbfs ioctl

_IOC_NONE, _IOC_WRITE, _IOC_READ = 0, 1, 2


def _ioc(direction, typ, nr, size):
    return (direction << 30) | (size << 16) | (ord(typ) << 8) | nr


class CtrlTransfer(ctypes.Structure):
    _fields_ = [("bRequestType", ctypes.c_uint8), ("bRequest", ctypes.c_uint8),
                ("wValue", ctypes.c_uint16), ("wIndex", ctypes.c_uint16),
                ("wLength", ctypes.c_uint16), ("timeout", ctypes.c_uint32),
                ("data", ctypes.c_void_p)]


class BulkTransfer(ctypes.Structure):
    _fields_ = [("ep", ctypes.c_uint), ("len", ctypes.c_uint),
                ("timeout", ctypes.c_uint), ("data", ctypes.c_void_p)]


class UsbIoctl(ctypes.Structure):
    _fields_ = [("ifno", ctypes.c_int), ("ioctl_code", ctypes.c_int),
                ("data", ctypes.c_void_p)]


USBDEVFS_CONTROL = _ioc(_IOC_READ | _IOC_WRITE, "U", 0, ctypes.sizeof(CtrlTransfer))
USBDEVFS_BULK = _ioc(_IOC_READ | _IOC_WRITE, "U", 2, ctypes.sizeof(BulkTransfer))
USBDEVFS_CLAIMINTERFACE = _ioc(_IOC_READ, "U", 15, ctypes.sizeof(ctypes.c_uint))
USBDEVFS_RELEASEINTERFACE = _ioc(_IOC_READ, "U", 16, ctypes.sizeof(ctypes.c_uint))
USBDEVFS_IOCTL = _ioc(_IOC_READ | _IOC_WRITE, "U", 18, ctypes.sizeof(UsbIoctl))
USBDEVFS_DISCONNECT = _ioc(_IOC_NONE, "U", 22, 0)

_libc = None


def _ioctl(fd, request, arg_addr):
    global _libc
    if _libc is None:
        _libc = ctypes.CDLL(None, use_errno=True)
        _libc.ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
        _libc.ioctl.restype = ctypes.c_int
    res = _libc.ioctl(fd, request, arg_addr)
    if res < 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))
    return res


# ------------------------------------------------------------------- Geraete

FtdiInfo = namedtuple("FtdiInfo", "serial busnum devnum pid product sysname driver")


def _read(path, name, default=None):
    try:
        with open(os.path.join(path, name)) as f:
            return f.read().strip()
    except OSError:
        if default is None:
            raise
        return default


def find_devices(pids=DEFAULT_PIDS, sysfs="/sys/bus/usb/devices"):
    """Alle angeschlossenen FTDI-Geraete mit passender Product-ID
    (pids=None: alle FTDI-Geraete, egal welche Product-ID)."""
    out = []
    for path in glob.glob(os.path.join(sysfs, "*")):
        try:
            vid = int(_read(path, "idVendor"), 16)
            pid = int(_read(path, "idProduct"), 16)
            if vid != FTDI_VID or (pids is not None and pid not in pids):
                continue
            busnum = int(_read(path, "busnum"))
            devnum = int(_read(path, "devnum"))
        except (OSError, ValueError):
            continue
        name = os.path.basename(path)
        drv = os.path.join(path, name + ":1.0", "driver")
        driver = os.path.basename(os.readlink(drv)) if os.path.islink(drv) else "-"
        out.append(FtdiInfo(_read(path, "serial", ""), busnum, devnum, pid,
                            _read(path, "product", ""), name, driver))
    return sorted(out, key=lambda i: i.sysname)


class FtdiBitbang:
    def __init__(self, info, mask=0xFF, timeout_ms=1000):
        self.info = info
        self.mask = mask
        self.timeout = timeout_ms
        self.fd = None

    def open(self):
        path = "/dev/bus/usb/%03d/%03d" % (self.info.busnum, self.info.devnum)
        fd = os.open(path, os.O_RDWR)
        try:
            self._detach_kernel_driver(fd, 0)
            iface = ctypes.c_uint(0)
            _ioctl(fd, USBDEVFS_CLAIMINTERFACE, ctypes.addressof(iface))
        except OSError:
            os.close(fd)
            raise
        self.fd = fd

    @staticmethod
    def _detach_kernel_driver(fd, ifno):
        cmd = UsbIoctl(ifno, USBDEVFS_DISCONNECT, None)
        try:
            _ioctl(fd, USBDEVFS_IOCTL, ctypes.addressof(cmd))
        except OSError as err:
            if err.errno != errno.ENODATA:  # ENODATA: kein Treiber gebunden
                raise

    def _control(self, reqtype, request, value, length=0):
        buf = ctypes.create_string_buffer(max(length, 1))
        ct = CtrlTransfer(reqtype, request, value, INDEX_A, length, self.timeout,
                          ctypes.addressof(buf) if length else None)
        n = _ioctl(self.fd, USBDEVFS_CONTROL, ctypes.addressof(ct))
        return buf.raw[:n] if length else b""

    def set_bitbang(self):
        self._control(REQ_OUT, SIO_SET_BITMODE, (BITMODE_BITBANG << 8) | self.mask)

    def reset_mode(self):
        self._control(REQ_OUT, SIO_SET_BITMODE, BITMODE_RESET << 8)

    def read_pins(self):
        data = self._control(REQ_IN, SIO_READ_PINS, 0, 1)
        if len(data) != 1:
            raise OSError(errno.EIO, "READ_PINS lieferte %d Bytes" % len(data))
        return data[0]

    def write(self, value):
        buf = ctypes.create_string_buffer(bytes([value & 0xFF]), 1)
        bt = BulkTransfer(EP_OUT, 1, self.timeout, ctypes.addressof(buf))
        if _ioctl(self.fd, USBDEVFS_BULK, ctypes.addressof(bt)) != 1:
            raise OSError(errno.EIO, "Bulk-Write unvollstaendig")

    def close(self):
        """Interface freigeben. Relais bleiben, wie sie sind; ftdi_sio bleibt
        abgekoppelt (siehe Moduldoku)."""
        if self.fd is None:
            return
        try:
            iface = ctypes.c_uint(0)
            _ioctl(self.fd, USBDEVFS_RELEASEINTERFACE, ctypes.addressof(iface))
        except OSError:
            pass
        finally:
            os.close(self.fd)
            self.fd = None
