"""The devices of a SmartiLab account, with what they are made of and their last values.

The whole state is read at the start and then rarely: while the live channel is connected every
change arrives by itself (live.py) and is written here. Without it the state is read every minute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SmartiLabApi, SmartiLabAuthError, SmartiLabError
from .const import DOMAIN, LOGGER, POLL_WITH_LIVE, POLL_WITHOUT_LIVE
from .model import Part, Point, apply_change, points

# Answers that concern one device and not the account: the device stays, unavailable, with the reason.
_DEVICE_PROBLEMS = {"no_remote", "offline", "on_hold", "not_found"}


@dataclass
class DeviceData:
    """One device: as the list gives it, its description, its state, and what Home Assistant makes of them."""

    info: dict[str, Any]
    description: dict[str, Any] | None = None
    state: dict[str, Any] | None = None
    points: list[Point] = field(default_factory=list)
    parts: list[Part] = field(default_factory=list)
    problem: str | None = None

    @property
    def online(self) -> bool:
        return bool(self.info.get("online"))


class SmartiLabCoordinator(DataUpdateCoordinator[dict[str, DeviceData]]):
    """Reads the devices of the account; the live channel keeps them current in between."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: SmartiLabApi) -> None:
        super().__init__(hass, LOGGER, config_entry=entry, name=DOMAIN, update_interval=timedelta(seconds=POLL_WITHOUT_LIVE))
        self.api = api

    def set_live(self, up: bool) -> None:
        """The live channel is connected, or not: read the whole state rarely, or every minute."""
        self.update_interval = timedelta(seconds=POLL_WITH_LIVE if up else POLL_WITHOUT_LIVE)

    async def _async_update_data(self) -> dict[str, DeviceData]:
        try:
            devices = await self.api.devices()
        except SmartiLabAuthError as err:
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="auth_failed") from err
        except SmartiLabError as err:
            raise UpdateFailed(translation_domain=DOMAIN, translation_key="update_failed", translation_placeholders={"error": str(err)}) from err
        held = self.data or {}
        out: dict[str, DeviceData] = {}
        for info in devices:
            did = info["id"]
            before = held.get(did)
            data = DeviceData(info=info)
            if before is not None and before.description is not None and before.description.get("revision") == info.get("revision"):
                data.description, data.points, data.parts = before.description, before.points, before.parts
            try:
                if data.description is None:
                    data.description = await self.api.description(did)
                    data.points, data.parts = points(data.description)
                data.state = await self.api.state(did)
            except SmartiLabAuthError as err:
                raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="auth_failed") from err
            except SmartiLabError as err:
                if err.code not in _DEVICE_PROBLEMS:
                    raise UpdateFailed(translation_domain=DOMAIN, translation_key="update_failed", translation_placeholders={"error": str(err)}) from err
                # A Professional without a licence that gives remote control, a board on hold: it stays, unavailable.
                data.problem = err.code
                if before is not None and data.description is None:
                    data.description, data.points, data.parts, data.state = before.description, before.points, before.parts, before.state
            out[did] = data
        return out

    def structure(self) -> frozenset[str]:
        """What entities and devices there are: when it changes, the entry is loaded again."""
        out: set[str] = set()
        for did, dev in (self.data or {}).items():
            out.add(did)
            out.update(p.uid for p in dev.points)
            out.update(p.uid for p in dev.parts)
        return frozenset(out)

    def changed(self, device: str, data: dict[str, Any]) -> None:
        """A value that the live channel brought."""
        dev = (self.data or {}).get(device)
        if dev is None:
            return
        if dev.state is None:
            dev.state = {"online": dev.online, "modules": {}}
        if apply_change(dev.state, data):
            self.async_update_listeners()

    def connected(self, device: str, online: bool) -> None:
        """The live channel says that a device connected or disappeared."""
        dev = (self.data or {}).get(device)
        if dev is None:
            return
        dev.info["online"] = online
        if dev.state is not None:
            dev.state["online"] = online
        self.async_update_listeners()
