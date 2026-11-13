# Wyze Floor Lamp for Home Assistant (Bluetooth)

Local control of the Bluetooth-only **Wyze Floor Lamp** from Home Assistant. No Wyze account,
cloud or hub is involved: the integration talks to the lamp over Bluetooth, directly or through
an [ESPHome Bluetooth proxy](https://esphome.io/projects/?type=bluetooth).

The Wyze cloud integrations can't control this lamp because it has no Wi-Fi
(see [ha-wyzeapi#218](https://github.com/SecKatie/ha-wyzeapi/issues/218)).

## Features

- On/off and brightness (1–100%). The lamp has no color temperature control.
- Live state: changes made with the lamp's own remote show up in Home Assistant within a second.
- Automatic discovery, and several lamps can be added.

## Requirements

- Home Assistant with Bluetooth: a local adapter, or an ESPHome Bluetooth proxy with active
  connections (the default for the ready-made proxy firmware) within range of the lamp.
- The lamp set up once in the Wyze app (so it's paired to its remote), then **close the Wyze app**.
  The lamp accepts one Bluetooth connection at a time, and this integration keeps one open, so the
  Wyze app can't reach the lamp while the integration is running. The remote keeps working.

## Install

**HACS:** HACS → ⋮ → Custom repositories → add `https://github.com/clarkent86/ha-wyze-floor-lamp`
as an *Integration*, install **Wyze Floor Lamp (Bluetooth)**, then restart Home Assistant.

**Manual:** copy `custom_components/wyze_floor_lamp` into your `config/custom_components/` and restart.

After the restart, Home Assistant should show the lamp as discovered (Settings → Devices &
services). Confirm it, or add it with **Add integration → Wyze Floor Lamp (Bluetooth)**.

## Troubleshooting

- *Not discovered:* make sure an adapter or proxy is within range and the Wyze app isn't connected
  to the lamp. The lamp advertises Wyze Labs manufacturer data (`0x0870`) starting `03 06`; its
  remote advertises `03 07` and is ignored.
- *Unavailable:* the integration retries every minute. Debug logs:
  `logger: logs: custom_components.wyze_floor_lamp: debug`.

## How it works

The lamp uses an Andon Health (iHealth) Bluetooth module. Each connection sets up a session key
with a small Diffie-Hellman exchange, and commands are encrypted with XXTEA. The full protocol is
in [PROTOCOL.md](PROTOCOL.md). It was worked out from Bluetooth captures of the official app for
interoperability; no Wyze code is included. `python tests/test_protocol.py` checks the
implementation byte for byte against captured app traffic.

**Security note:** the lamp's own pairing scheme has no stored secret, so anything in Bluetooth
range that speaks this protocol can control the lamp, with or without this integration.

## Disclaimer

Not affiliated with or endorsed by Wyze Labs or Andon Health. "Wyze" is a trademark of Wyze Labs,
Inc. Use at your own risk.
