"""Wyze Floor Lamp (Andon JA_SL10) Bluetooth protocol.

Reverse engineered from the Wyze app (com.andon.floorlamp) for interoperability:

* Service 31305642-4c53-2e6e-6175-696a2e6d6f63 ("com.jiuan.SLBV01"). Write commands
  without response to ...6e6573 ("sen."), notifications arrive on ...636572 ("rec.").
* Each connection starts with a 32-bit Diffie-Hellman exchange (p = 2^32 - 59, g = 5).
  The session key is the shared secret as 8 lowercase hex characters, zero padded to
  16 bytes, and is used with XXTEA (no length word).
* A message is [auth, seq, op, type, args...]. Bytes from index 2 are XORed with an LCG
  stream seeded by seq, and auth is the XOR of bytes 1.. after that.
* Key exchange frames are 00 00 00 00 00 len msg (sent) / 00 00 00 00 00 len msg (received).
  Data frames are 02 00 00 00 00 + XXTEA([len] + msg, zero padded to 8 bytes).
"""
from __future__ import annotations

import secrets
import struct

SERVICE_UUID = "31305642-4c53-2e6e-6175-696a2e6d6f63"
WRITE_UUID = "31305642-4c53-2e6e-6175-696a2e6e6573"
NOTIFY_UUID = "31305642-4c53-2e6e-6175-696a2e636572"

WYZE_COMPANY_ID = 0x0870
LAMP_PRODUCT = 0x06
REMOTE_PRODUCT = 0x07

P = 4294967237
G = 5
_DELTA = 0x9E3779B9

OP_GET, OP_SET, OP_STATUS = 0x01, 0x02, 0x06
OP_GET_RSP, OP_SET_RSP = 0x81, 0x82
T_ONOFF, T_BRIGHTNESS, T_KEY_EXCHANGE = 0x01, 0x02, 0x3F

TRANSITION_ONOFF = 8
TRANSITION_BRIGHTNESS = 5


def lcg_xor(data: bytes) -> bytes:
    """Obfuscate or de-obfuscate (the same operation) bytes 2.. seeded by byte 1."""
    out = bytearray(data)
    j = out[1]
    for i in range(2, len(out)):
        j = (j * 214013 + 2531011) & 0xFFFFFFFFFFFFFFFF
        out[i] ^= (j >> 16) & 0xFF
    return bytes(out)


def _auth(data: bytes) -> int:
    x = 0
    for v in data[1:]:
        x ^= v
    return x


def build(seq: int, op: int, typ: int, *args: int) -> bytes:
    """A plain message, obfuscated and with its auth byte set."""
    raw = lcg_xor(bytes([0, seq & 0xFF, op, typ, *[a & 0xFF for a in args]]))
    return bytes([_auth(raw)]) + raw[1:]


def parse(msg: bytes) -> bytes | None:
    """De-obfuscate a received message; None if too short or the auth byte is wrong."""
    if len(msg) < 4 or msg[0] != _auth(msg):
        return None
    return lcg_xor(msg)


def _ints(b: bytes) -> list[int]:
    b = b + b"\0" * (-len(b) % 4)
    return list(struct.unpack("<%dI" % (len(b) // 4), b))


def _mx(s: int, y: int, z: int, p: int, e: int, k: list[int]) -> int:
    return ((((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))) ^ ((s ^ y) + (k[(p & 3) ^ e] ^ z))) & 0xFFFFFFFF


def xxtea_encrypt(data: bytes, key: bytes) -> bytes:
    v, k = _ints(data), _ints((key + b"\0" * 16)[:16])
    n = len(v)
    if n < 2:
        return data
    z, s = v[-1], 0
    for _ in range(6 + 52 // n):
        s = (s + _DELTA) & 0xFFFFFFFF
        e = (s >> 2) & 3
        for p in range(n):
            y = v[(p + 1) % n]
            v[p] = (v[p] + _mx(s, y, z, p, e, k)) & 0xFFFFFFFF
            z = v[p]
    return struct.pack("<%dI" % n, *v)


def xxtea_decrypt(data: bytes, key: bytes) -> bytes:
    v, k = _ints(data), _ints((key + b"\0" * 16)[:16])
    n = len(v)
    if n < 2:
        return data
    s = ((6 + 52 // n) * _DELTA) & 0xFFFFFFFF
    y = v[0]
    while s:
        e = (s >> 2) & 3
        for p in range(n - 1, -1, -1):
            z = v[(p - 1) % n]
            v[p] = (v[p] - _mx(s, y, z, p, e, k)) & 0xFFFFFFFF
            y = v[p]
        s = (s - _DELTA) & 0xFFFFFFFF
    return struct.pack("<%dI" % n, *v)


def new_private() -> tuple[int, int]:
    """A private exponent in the app's range whose public value is a full 4 bytes."""
    while True:
        a = 400000000 + secrets.randbelow(216127803)
        pub = pow(G, a, P)
        if pub >= 0x10000000:
            return a, pub


def key_exchange_frame(seq: int, pub: int) -> bytes:
    msg = build(seq, OP_GET, T_KEY_EXCHANGE, *pub.to_bytes(4, "big"))
    return b"\0\0\0\0\0" + bytes([len(msg)]) + msg


def session_key(private: int, frame: bytes) -> bytes:
    """Session key from the lamp's key exchange reply."""
    body = lcg_xor(frame[6:])
    lamp_pub = int.from_bytes(body[4:8], "big")
    return ("%08x" % pow(lamp_pub, private, P)).encode()


def data_frame(msg: bytes, key: bytes) -> bytes:
    body = bytes([len(msg)]) + msg
    body += b"\0" * (-len(body) % 8)
    return b"\x02\0\0\0\0" + xxtea_encrypt(body, key)


def open_frame(frame: bytes, key: bytes) -> bytes | None:
    """Decrypted, de-obfuscated message from a data frame, or None."""
    if len(frame) < 13 or frame[0] == 0:
        return None
    dec = xxtea_decrypt(frame[5:], key)
    n = dec[0]
    if n < 4 or n + 1 > len(dec):
        return None
    return parse(dec[1 : 1 + n])
