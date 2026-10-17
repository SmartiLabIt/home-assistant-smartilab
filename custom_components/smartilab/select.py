"""Choices that can be written: one of the fixed values a property declares."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartiLabConfigEntry
from .entity import SmartiLabEntity


async def async_setup_entry(hass: HomeAssistant, entry: SmartiLabConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    rt = entry.runtime_data
    add(SmartiLabSelect(rt.coordinator, p, rt.site) for p in rt.coordinator_points("select"))


class SmartiLabSelect(SmartiLabEntity, SelectEntity):
    """A choice of a device."""

    @property
    def options(self) -> list[str]:
        return [name for _, name in self.point.options]

    @property
    def current_option(self) -> str | None:
        value = self.value
        return next((name for oid, name in self.point.options if oid == value), None)

    async def async_select_option(self, option: str) -> None:
        chosen = next((oid for oid, name in self.point.options if name == option), None)
        if chosen is not None:
            await self._send(True, chosen)
