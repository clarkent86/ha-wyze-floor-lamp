from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak, async_discovered_service_info
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN
from .protocol import LAMP_PRODUCT, WYZE_COMPANY_ID


def _is_lamp(info: BluetoothServiceInfoBleak) -> bool:
    data = info.manufacturer_data.get(WYZE_COMPANY_ID)
    return bool(data) and len(data) >= 2 and data[0] == 3 and data[1] == LAMP_PRODUCT


def _title(address: str) -> str:
    """Name with the end of the address, so several lamps can be told apart."""
    return f"Wyze Floor Lamp {address.replace(':', '')[-4:]}"


class WyzeFloorLampConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, str] = {}
        self._address: str | None = None

    async def async_step_bluetooth(self, info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        if not _is_lamp(info):
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(info.address)
        self._abort_if_unique_id_configured()
        self._address = info.address
        self.context["title_placeholders"] = {"name": _title(info.address)}
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        title = _title(self._address)
        if user_input is not None:
            return self.async_create_entry(title=title, data={CONF_ADDRESS: self._address})
        self._set_confirm_only()
        return self.async_show_form(step_id="confirm", description_placeholders={"name": title})

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=_title(address), data={CONF_ADDRESS: address})
        current = self._async_current_ids()
        for info in async_discovered_service_info(self.hass, connectable=True):
            if _is_lamp(info) and info.address not in current:
                self._discovered[info.address] = f"{_title(info.address)} ({info.address})"
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(self._discovered)}))
