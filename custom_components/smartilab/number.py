"""Numbers that can be written: a level, a time, a threshold of the device, within its limits."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartiLabConfigEntry
from .entity import SmartiLabEntity

# Without limits from the device the box takes any number; the device itself says if it refuses.
_WIDE = 1_000_000_000


async def async_setup_entry(hass: HomeAssistant, entry: SmartiLabConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    rt = entry.runtime_data
    add(SmartiLabNumber(rt.coordinator, p, rt.site) for p in rt.coordinator_points("number"))


class SmartiLabNumber(SmartiLabEntity, NumberEntity):
    """A number of a device."""

    _attr_mode = NumberMode.BOX

    @property
    def native_min_value(self) -> float:
        return self.point.minimum if self.point.minimum is not None else -_WIDE

    @property
    def native_max_value(self) -> float:
        return self.point.maximum if self.point.maximum is not None else _WIDE

    @property
    def native_step(self) -> float:
        if self.point.step is not None:
            return self.point.step
        return 10 ** -self.point.decimals if self.point.decimals else 1

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self.point.unit

    @property
    def native_value(self) -> float | None:
        value = self.value
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    async def async_set_native_value(self, value: float) -> None:
        # A whole number travels as one: the device may want an integer.
        await self._send(True, int(value) if float(value).is_integer() and not self.point.decimals else value)
