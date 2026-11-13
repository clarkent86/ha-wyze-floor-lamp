"""Connection to one Wyze Floor Lamp through Home Assistant's Bluetooth stack (works via ESPHome proxies)."""
from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Callable

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from . import protocol as p

_LOGGER = logging.getLogger(__name__)

KEY_TIMEOUT = 10.0
REPLY_TIMEOUT = 5.0
# A whole connection attempt. Bluetooth proxies can stall a connection with no
# error; without a cap, the attempt holds the lock and every retry (and unload)
# waits behind it forever.
CONNECT_TIMEOUT = 45.0
DISCONNECT_TIMEOUT = 10.0


class WyzeFloorLamp:
    """Keeps a connection open so the lamp's own status reports (remote presses) arrive live."""

    def __init__(self, ble_device: BLEDevice, name: str) -> None:
        self._ble_device = ble_device
        self.name = name
        self.address = ble_device.address
        self._client: BleakClientWithServiceCache | None = None
        self._key: bytes | None = None
        self._private = 0
        self._seq = 0
        self._lock = asyncio.Lock()
        self._key_ready: asyncio.Future[bytes] | None = None
        self._waiters: dict[int, asyncio.Future[bytes]] = {}
        self._listeners: list[Callable[[], None]] = []
        self.is_on: bool | None = None
        self.brightness: int | None = None  # 1-100
        self.remote: str | None = None

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected and self._key is not None

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        self._ble_device = ble_device

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    def _notify_listeners(self) -> None:
        for cb in list(self._listeners):
            cb()

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    async def ensure_connected(self) -> None:
        async with self._lock:
            if self.connected:
                return
            try:
                async with asyncio.timeout(CONNECT_TIMEOUT):
                    await self._connect()
            except TimeoutError:
                _LOGGER.debug("%s: connection attempt timed out", self.address)
                await self._drop()
                raise BleakError("connection attempt timed out") from None

    async def _connect(self) -> None:
        self._key = None
        client = await establish_connection(
            BleakClientWithServiceCache, self._ble_device, self.name,
            disconnected_callback=self._on_disconnect, max_attempts=3,
        )
        self._client = client
        try:
            await client.start_notify(p.NOTIFY_UUID, self._on_notify)
            loop = asyncio.get_running_loop()
            self._key_ready = loop.create_future()
            self._private, pub = p.new_private()
            self._seq = secrets.randbelow(200) + 1
            await client.write_gatt_char(p.WRITE_UUID, p.key_exchange_frame(self._seq, pub), response=False)
            self._key = await asyncio.wait_for(self._key_ready, KEY_TIMEOUT)
        except (BleakError, TimeoutError):
            await self._drop()
            raise
        _LOGGER.debug("%s: connected, session key set", self.address)
        await self._send(p.OP_GET, p.T_ONOFF)
        await self._send(p.OP_GET, p.T_BRIGHTNESS)
        self._notify_listeners()

    async def _drop(self) -> None:
        client, self._client, self._key = self._client, None, None
        if client is not None:
            try:
                async with asyncio.timeout(DISCONNECT_TIMEOUT):
                    await client.disconnect()
            except (BleakError, TimeoutError):
                pass

    def _on_disconnect(self, _client) -> None:
        _LOGGER.debug("%s: disconnected", self.address)
        self._key = None
        self._client = None
        for fut in self._waiters.values():
            if not fut.done():
                fut.set_exception(BleakError("disconnected"))
        self._waiters.clear()
        self._notify_listeners()

    def _on_notify(self, _char, data: bytearray) -> None:
        frame = bytes(data)
        if frame[:1] == b"\0":
            if self._key_ready is not None and not self._key_ready.done():
                self._key_ready.set_result(p.session_key(self._private, frame))
            return
        if self._key is None:
            return
        msg = p.open_frame(frame, self._key)
        if msg is None:
            _LOGGER.debug("%s: undecodable frame %s", self.address, frame.hex())
            return
        self._handle(msg)

    def _handle(self, msg: bytes) -> None:
        seq, op, typ, args = msg[1], msg[2], msg[3], msg[4:]
        changed = False
        if typ == p.T_ONOFF and op in (p.OP_GET_RSP, p.OP_SET_RSP, p.OP_STATUS) and args:
            self.is_on = args[0] == 1
            changed = True
        elif typ == p.T_BRIGHTNESS and op in (p.OP_GET_RSP, p.OP_SET_RSP, p.OP_STATUS) and len(args) >= 2:
            # [current, target, ...]: the target is where a fade ends; 0 means turning off.
            target = args[1]
            if target > 0:
                self.brightness = target
                self.is_on = True
            elif op == p.OP_STATUS:
                self.is_on = False
            changed = True
        elif typ == 0x31 and len(args) >= 7:
            self.remote = ":".join(f"{b:02X}" for b in args[1:7])
        fut = self._waiters.pop(seq, None)
        if fut is not None and not fut.done() and op in (p.OP_GET_RSP, p.OP_SET_RSP):
            fut.set_result(msg)
        if changed:
            self._notify_listeners()

    async def _send(self, op: int, typ: int, *args: int) -> bytes | None:
        if self._client is None or self._key is None:
            raise BleakError("not connected")
        seq = self._next_seq()
        fut: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
        self._waiters[seq] = fut
        await self._client.write_gatt_char(p.WRITE_UUID, p.data_frame(p.build(seq, op, typ, *args), self._key), response=False)
        try:
            return await asyncio.wait_for(fut, REPLY_TIMEOUT)
        except asyncio.TimeoutError:
            self._waiters.pop(seq, None)
            _LOGGER.debug("%s: no reply to %02x/%02x", self.address, op, typ)
            return None

    async def _command(self, op: int, typ: int, *args: int) -> None:
        for attempt in (1, 2):
            try:
                await self.ensure_connected()
                await self._send(op, typ, *args)
                return
            except BleakError:
                if attempt == 2:
                    raise
                await self._drop()

    async def turn_on(self, brightness: int | None = None) -> None:
        if not self.is_on:
            await self._command(p.OP_SET, p.T_ONOFF, 1, p.TRANSITION_ONOFF, 0)
            self.is_on = True
        if brightness is not None:
            await self._command(p.OP_SET, p.T_BRIGHTNESS, max(1, min(100, brightness)), p.TRANSITION_BRIGHTNESS, 0)
            self.brightness = brightness
        self._notify_listeners()

    async def turn_off(self) -> None:
        await self._command(p.OP_SET, p.T_ONOFF, 0, p.TRANSITION_ONOFF, 0)
        self.is_on = False
        self._notify_listeners()

    async def stop(self) -> None:
        # Don't wait for the lock: a connection attempt may be in progress.
        await self._drop()

