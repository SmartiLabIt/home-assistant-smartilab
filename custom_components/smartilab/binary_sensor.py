"""Yes or no: the ``flag`` properties (a catch, a problem, motion), and switches and lights that can only be read."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartiLabConfigEntry
from .entity import SmartiLabEntity

# The classes of the cloud that are not the name of a class of Home Assistant.
_ALIASES = {"outlet": "plug"}
_CLASSES = {c.value for c in BinarySensorDeviceClass}


async def async_setup_entry(hass: HomeAssistant, entry: SmartiLabConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    rt = entry.runtime_data
    add(SmartiLabBinarySensor(rt.coordinator, p, rt.site) for p in rt.coordinator_points("binary_sensor"))


class SmartiLabBinarySensor(SmartiLabEntity, BinarySensorEntity):
    """Something that is true or false."""

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        klass = _ALIASES.get(self.point.klass or "", self.point.klass)
        return BinarySensorDeviceClass(klass) if klass in _CLASSES else None

    @property
    def is_on(self) -> bool | None:
        value = self.value
        if isinstance(value, dict):
            value = value.get("on")
        return value if isinstance(value, bool) else None
