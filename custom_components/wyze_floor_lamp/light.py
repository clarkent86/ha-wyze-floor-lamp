from __future__ import annotations

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WyzeLampConfigEntry
from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: WyzeLampConfigEntry, add: AddEntitiesCallback) -> None:
    add([WyzeFloorLampLight(entry)])


class WyzeFloorLampLight(LightEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, entry: WyzeLampConfigEntry) -> None:
        self._lamp = entry.runtime_data
        self._attr_unique_id = self._lamp.address
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._lamp.address)},
            connections={(CONNECTION_BLUETOOTH, self._lamp.address)},
            name=entry.title, manufacturer="Wyze", model="Floor Lamp (JA_SL10)",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._lamp.add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return self._lamp.connected

    @property
    def is_on(self) -> bool | None:
        return self._lamp.is_on

    @property
    def brightness(self) -> int | None:
        b = self._lamp.brightness
        return None if b is None else round(b * 255 / 100)

    @property
    def extra_state_attributes(self):
        return {"remote": self._lamp.remote} if self._lamp.remote else None

    async def async_turn_on(self, **kwargs) -> None:
        pct = None
        if ATTR_BRIGHTNESS in kwargs:
            pct = max(1, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255))
        await self._lamp.turn_on(pct)

    async def async_turn_off(self, **kwargs) -> None:
        await self._lamp.turn_off()
