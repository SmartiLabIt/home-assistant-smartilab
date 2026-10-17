"""Buttons: the simple actions of a module (nothing to type, nothing to confirm)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartiLabConfigEntry
from .entity import SmartiLabEntity


async def async_setup_entry(hass: HomeAssistant, entry: SmartiLabConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    rt = entry.runtime_data
    add(SmartiLabButton(rt.coordinator, p, rt.site) for p in rt.coordinator_points("button"))


class SmartiLabButton(SmartiLabEntity, ButtonEntity):
    """An action of a device."""

    async def async_press(self) -> None:
        await self._send(False)
