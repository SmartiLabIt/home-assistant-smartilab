"""Lights: the ``light`` properties. On and off; brightness and colour when the device gives them."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartiLabConfigEntry
from .entity import SmartiLabEntity


async def async_setup_entry(hass: HomeAssistant, entry: SmartiLabConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    rt = entry.runtime_data
    add(SmartiLabLight(rt.coordinator, p, rt.site) for p in rt.coordinator_points("light"))


def _to_ha(level: int) -> int:
    """The brightness of the cloud (1 to 100) in Home Assistant (1 to 255)."""
    return max(1, min(255, round(level * 255 / 100)))


def _to_cloud(level: int) -> int:
    return max(1, min(100, round(level * 100 / 255)))


class SmartiLabLight(SmartiLabEntity, LightEntity):
    """A light of a device."""

    @property
    def _light(self) -> dict[str, Any]:
        value = self.value
        return value if isinstance(value, dict) else {}

    @property
    def color_mode(self) -> ColorMode:
        light = self._light
        if all(isinstance(light.get(c), int) for c in ("r", "g", "b")):
            return ColorMode.RGB
        if isinstance(light.get("brightness"), int):
            return ColorMode.BRIGHTNESS
        return ColorMode.ONOFF

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        return {self.color_mode}

    @property
    def is_on(self) -> bool | None:
        on = self._light.get("on")
        return on if isinstance(on, bool) else None

    @property
    def brightness(self) -> int | None:
        level = self._light.get("brightness")
        return _to_ha(level) if isinstance(level, int) else None

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        light = self._light
        return (light["r"], light["g"], light["b"]) if self.color_mode == ColorMode.RGB else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        change: dict[str, Any] = {"on": True}
        if ATTR_BRIGHTNESS in kwargs:
            change["brightness"] = _to_cloud(int(kwargs[ATTR_BRIGHTNESS]))
        if ATTR_RGB_COLOR in kwargs:
            change["r"], change["g"], change["b"] = (int(c) for c in kwargs[ATTR_RGB_COLOR])
        await self._send(True, change, {**self._light, **change})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(True, {"on": False}, {**self._light, "on": False})
