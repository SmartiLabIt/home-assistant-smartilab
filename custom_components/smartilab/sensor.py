"""Sensors: the values that can only be read, numbers with their unit and class, texts and choices."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartiLabConfigEntry
from .entity import SmartiLabEntity

_CLASSES = {c.value for c in SensorDeviceClass} - {SensorDeviceClass.ENUM.value, SensorDeviceClass.TIMESTAMP.value, SensorDeviceClass.DATE.value}


async def async_setup_entry(hass: HomeAssistant, entry: SmartiLabConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    rt = entry.runtime_data
    add(SmartiLabSensor(rt.coordinator, p, rt.site) for p in rt.coordinator_points("sensor"))


class SmartiLabSensor(SmartiLabEntity, SensorEntity):
    """A value of a device."""

    @property
    def device_class(self) -> SensorDeviceClass | None:
        if self.point.kind == "select":
            return SensorDeviceClass.ENUM
        klass = self.point.klass
        return SensorDeviceClass(klass) if self.point.kind == "number" and klass in _CLASSES else None

    @property
    def options(self) -> list[str] | None:
        return [name for _, name in self.point.options] if self.point.kind == "select" else None

    @property
    def state_class(self) -> SensorStateClass | None:
        return SensorStateClass.MEASUREMENT if self.point.kind == "number" else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self.point.unit if self.point.kind == "number" else None

    @property
    def suggested_display_precision(self) -> int | None:
        return self.point.decimals if self.point.kind == "number" else None

    @property
    def native_value(self) -> float | int | str | None:
        value = self.value
        if self.point.kind == "number":
            return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        if self.point.kind == "select":
            return next((name for oid, name in self.point.options if oid == value), None)
        return value[:255] if isinstance(value, str) else None
