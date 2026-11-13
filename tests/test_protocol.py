"""Checks the protocol against a real capture from the Wyze app (2026-11-13)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "wyze_floor_lamp"))
import protocol as p

# Phone's private exponent recovered from its public key by discrete log.
PRIV = 538994879
KX_SENT = bytes.fromhex("0000000000083027a4a46e2cd085")
KX_RECV = bytes.fromhex("000000000008b72724a4f6156794")
CAPTURE = [  # (direction, frame) from the btsnoop log
    ("->", "0200000000cd41f8beb5c42929"),  # SET on/off = 0
    ("<-", "0200000000be7bd789bd604858"),
    ("->", "0200000000b04660619ce9d10f"),  # SET on/off = 1
    ("->", "0200000000a868046d77e2df96"),  # SET brightness 97
    ("<-", "0200000000bd09609a19dab5da87cda65249b7fc61"),
]

def test_key_exchange():
    assert pow(p.G, PRIV, p.P) == 0x1B4623CE
    assert p.key_exchange_frame(0x27, 0x1B4623CE) == KX_SENT
    assert p.session_key(PRIV, KX_RECV) == b"cdfc9f5c"

def test_decrypt_capture():
    key = b"cdfc9f5c"
    msgs = [p.open_frame(bytes.fromhex(f), key) for _, f in CAPTURE]
    assert msgs[0][1:] == bytes([0x2D, 0x02, 0x01, 0x00, 0x08, 0x00])
    assert msgs[1][1:] == bytes([0x2D, 0x82, 0x01, 0x00, 0x64])
    assert msgs[2][1:] == bytes([0x2E, 0x02, 0x01, 0x01, 0x08, 0x00])
    assert msgs[3][1:] == bytes([0x31, 0x02, 0x02, 0x61, 0x05, 0x00])
    assert msgs[4][2:4] == bytes([0x81, 0x02])

def test_build_matches_app_byte_for_byte():
    key = b"cdfc9f5c"
    assert p.data_frame(p.build(0x2D, p.OP_SET, p.T_ONOFF, 0, 8, 0), key) == bytes.fromhex(CAPTURE[0][1])
    assert p.data_frame(p.build(0x2E, p.OP_SET, p.T_ONOFF, 1, 8, 0), key) == bytes.fromhex(CAPTURE[2][1])
    assert p.data_frame(p.build(0x31, p.OP_SET, p.T_BRIGHTNESS, 0x61, 5, 0), key) == bytes.fromhex(CAPTURE[3][1])

def test_roundtrip_new_key():
    a, pub = p.new_private()
    assert pub >= 0x10000000 and pow(p.G, a, p.P) == pub
    key = b"0123abcd"
    m = p.build(7, p.OP_GET, p.T_BRIGHTNESS)
    assert p.open_frame(p.data_frame(m, key), key)[1:] == bytes([7, 1, 2])

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
