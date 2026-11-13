"""Wyze Floor Lamp over Bluetooth (no Wyze cloud)."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval

from .lamp import WyzeFloorLamp

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.LIGHT]
RECONNECT_EVERY = timedelta(minutes=1)

WyzeLampConfigEntry = ConfigEntry[WyzeFloorLamp]


async def async_setup_entry(hass: HomeAssistant, entry: WyzeLampConfigEntry) -> bool:
    address = entry.data[CONF_ADDRESS]
    ble_device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if ble_device is None:
        raise ConfigEntryNotReady(f"Wyze Floor Lamp {address} is not in range of a connectable Bluetooth adapter or proxy")
    lamp = WyzeFloorLamp(ble_device, entry.title)
    entry.runtime_data = lamp

    @callback
    def _seen(service_info: bluetooth.BluetoothServiceInfoBleak, _change) -> None:
        lamp.set_ble_device(service_info.device)

    entry.async_on_unload(bluetooth.async_register_callback(
        hass, _seen, bluetooth.BluetoothCallbackMatcher(address=address, connectable=True),
        bluetooth.BluetoothScanningMode.PASSIVE))

    async def _keep_connected(_now=None) -> None:
        if not lamp.connected:
            try:
                await lamp.ensure_connected()
            except Exception as err:  # noqa: BLE001 - retried every minute
                _LOGGER.debug("%s: connect failed: %s", address, err)

    entry.async_on_unload(async_track_time_interval(hass, _keep_connected, RECONNECT_EVERY))
    entry.async_create_background_task(hass, _keep_connected(), "wyze_floor_lamp connect")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WyzeLampConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.stop()
    return ok
