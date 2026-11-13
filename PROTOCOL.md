# Wyze Floor Lamp Bluetooth protocol

Worked out on 2026-11-13 from an Android HCI snoop capture of the Wyze app (3.25.0.1027)
and the app's `com.andon.floorlamp` code, for interoperability with our own lamp.

## GATT

| | UUID | ASCII (byte-reversed) |
|---|---|---|
| Service | `31305642-4c53-2e6e-6175-696a2e6d6f63` | `com.jiuan.SLBV01` |
| Write (without response) | `31305642-4c53-2e6e-6175-696a2e6e6573` | `sen.jiuan.SLBV01` |
| Notify | `31305642-4c53-2e6e-6175-696a2e636572` | `rec.jiuan.SLBV01` |
| OTA service | `44415247-5055-2e6e-6175-696a2e6d6f63` | `com.jiuan.UPGRAD` |

## Messages

`[auth, seq, op, type, args...]`. Bytes from index 2 are XORed with an LCG stream seeded by
`seq` (`j = j*214013 + 2531011`, key byte `(j >> 16) & 0xFF`), then `auth` = XOR of bytes 1..n.
`seq` increments per message and the lamp echoes it.

op: `01` GET, `02` SET, `06` status report from the lamp, `81`/`82` replies to GET/SET.

| type | Meaning | SET args | Reply / status |
|---|---|---|---|
| `01` | On/off | `state transition(8) delay(0)` | `state brightness` |
| `02` | Brightness | `percent transition(5) delay(0)` | `current target 00 fade` (target 0 = turning off) |
| `07` | UTC time | time + zone | |
| `30` | Device info | | |
| `31` | Paired remote | | `00 mac[6]` |
| `3f` | Key exchange | | |

## Session setup

1. Subscribe to notifications.
2. Pick `a` in [400000000, 616127803), `A = 5^a mod (2^32 - 59)`, needing `A >= 0x10000000`.
   Send `00 00 00 00 00 08` + message `(GET, 3f, A as 4 bytes big-endian)`.
3. The lamp answers `00 00 00 00 00 08` + message whose bytes 4–7 are its `B`.
4. Key = `"%08x" % (B^a mod p)` as ASCII, zero padded to 16 bytes.
5. Data frames are `02 00 00 00 00` + XXTEA(`[len] + message`, zero padded to 8 bytes), using
   standard XXTEA (little-endian words, no length word).

There is no stored secret: a 32-bit exchange gives no real protection. Anyone in Bluetooth range
can control the lamp, and a recorded session can be decrypted with a discrete log.
