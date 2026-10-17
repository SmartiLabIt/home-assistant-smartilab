"""Switches: the ``toggle`` properties that can be written (a socket, a relay)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartiLabConfigEntry
from .entity import SmartiLabEntity


async def async_setup_entry(hass: HomeAssistant, entry: SmartiLabConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    rt = entry.runtime_data
    add(SmartiLabSwitch(rt.coordinator, p, rt.site) for p in rt.coordinator_points("switch"))


class SmartiLabSwitch(SmartiLabEntity, SwitchEntity):
    """A switch of a device."""

    @property
    def device_class(self) -> SwitchDeviceClass:
        return SwitchDeviceClass.OUTLET if self.point.klass == "outlet" else SwitchDeviceClass.SWITCH

    @property
    def is_on(self) -> bool | None:
        value = self.value
        return value if isinstance(value, bool) else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send(True, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(True, False)
