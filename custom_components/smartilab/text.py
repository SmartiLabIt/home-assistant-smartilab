"""Texts that can be written, up to the length the device declares (never more than 64 bytes)."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartiLabConfigEntry
from .entity import SmartiLabEntity

_LONGEST = 64


async def async_setup_entry(hass: HomeAssistant, entry: SmartiLabConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    rt = entry.runtime_data
    add(SmartiLabText(rt.coordinator, p, rt.site) for p in rt.coordinator_points("text"))


class SmartiLabText(SmartiLabEntity, TextEntity):
    """A text of a device."""

    @property
    def native_min(self) -> int:
        return int(self.point.minimum or 0)

    @property
    def native_max(self) -> int:
        return min(_LONGEST, int(self.point.maximum)) if self.point.maximum is not None else _LONGEST

    @property
    def native_value(self) -> str | None:
        value = self.value
        return value if isinstance(value, str) else None

    async def async_set_value(self, value: str) -> None:
        await self._send(True, value)
