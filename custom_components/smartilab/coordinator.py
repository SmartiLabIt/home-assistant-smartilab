"""The devices of a SmartiLab account, with what they are made of and their last values.

The whole state is read at the start and then rarely: while the live channel is connected every
change arrives by itself (live.py) and is written here. Without it the state is read every minute.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SmartiLabApi, SmartiLabAuthError, SmartiLabError
from .const import ADVANCED, DOMAIN, LOGGER, POLL_WITH_LIVE, POLL_WITHOUT_LIVE
from .model import Part, Point, apply_change, extras, points

# Answers that concern one device and not the account: the device stays, unavailable, with the reason.
_DEVICE_PROBLEMS = {"no_remote", "offline", "on_hold", "not_found"}


@dataclass
class DeviceData:
    """One device: as the list gives it, its description, its state, what the cloud knows besides (the alarms,
    the sums of the period of the parts, the settings of the modules), and what Home Assistant makes of them."""

    info: dict[str, Any]
    description: dict[str, Any] | None = None
    state: dict[str, Any] | None = None
    points: list[Point] = field(default_factory=list)
    parts: list[Part] = field(default_factory=list)
    problem: str | None = None
    alarms: list[dict[str, Any]] = field(default_factory=list)
    silences: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    settings: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    settings_at: float = 0.0
    # The points of the description alone; ``points`` adds the ones of what the cloud knows besides.
    own: list[Point] = field(default_factory=list)

    @property
    def online(self) -> bool:
        return bool(self.info.get("online"))

    @property
    def control(self) -> bool:
        """The access to this device is not read-only."""
        return self.info.get("role") != "viewer"


class SmartiLabCoordinator(DataUpdateCoordinator[dict[str, DeviceData]]):
    """Reads the devices of the account; the live channel keeps them current in between."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: SmartiLabApi) -> None:
        super().__init__(hass, LOGGER, config_entry=entry, name=DOMAIN, update_interval=timedelta(seconds=POLL_WITHOUT_LIVE))
        self.api = api
        # The devices with parts, by their id in the device registry of Home Assistant (__init__.py).
        self.parents: dict[str, str] = {}
        # The scopes of the access (GET /me): with the advanced commands, the commands of the modules, the settings, the alarms.
        self.scopes: list[str] = []
        self.lang = hass.config.language
        # The devices whose sums are to be read again shortly (soon()).
        self._soon: dict[str, Any] = {}

    def set_live(self, up: bool) -> None:
        """The live channel is connected, or not: read the whole state rarely, or every minute."""
        self.update_interval = timedelta(seconds=POLL_WITH_LIVE if up else POLL_WITHOUT_LIVE)

    @property
    def advanced(self) -> bool:
        return ADVANCED in self.scopes

    async def _async_update_data(self) -> dict[str, DeviceData]:
        try:
            if not self.scopes:
                self.scopes = [str(s) for s in (await self.api.me()).get("scopes") or []]
            devices = await self.api.devices()
        except SmartiLabAuthError as err:
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="auth_failed") from err
        except SmartiLabError as err:
            raise UpdateFailed(translation_domain=DOMAIN, translation_key="update_failed", translation_placeholders={"error": str(err)}) from err
        held = self.data or {}

        async def one(info: dict[str, Any]) -> DeviceData:
            did = info["id"]
            before = held.get(did)
            data = DeviceData(info=info)
            if before is not None and before.description is not None and before.description.get("revision") == info.get("revision"):
                data.description, data.own, data.parts = before.description, before.own, before.parts
                data.settings, data.settings_at = before.settings, before.settings_at
            if before is not None:
                data.alarms, data.silences, data.stats = before.alarms, before.silences, before.stats
            try:
                if data.description is None:
                    data.description = await self.api.description(did)
                    data.own, data.parts = points(data.description, self.advanced)
                data.state = await self.api.state(did)
                await self._extras(data)
            except SmartiLabAuthError as err:
                raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="auth_failed") from err
            except SmartiLabError as err:
                if err.code not in _DEVICE_PROBLEMS:
                    raise UpdateFailed(translation_domain=DOMAIN, translation_key="update_failed", translation_placeholders={"error": str(err)}) from err
                # A Professional without a licence that gives remote control, a board on hold: it stays, unavailable.
                data.problem = err.code
                if before is not None and data.description is None:
                    data.description, data.own, data.parts, data.state = before.description, before.own, before.parts, before.state
            self._points(data)
            return data

        # The devices together: one slow to answer does not hold the others.
        read = await asyncio.gather(*(one(info) for info in devices))
        return {data.info["id"]: data for data in read}

    def _points(self, data: DeviceData) -> None:
        """The points of the description, and those of what the cloud knows besides."""
        data.points = list(data.own)
        if data.description is not None:
            data.points += extras(data.description, data.alarms, data.silences, data.settings, self.lang, data.control)

    async def _extras(self, data: DeviceData) -> None:
        """What the cloud knows about a device besides its description and state. What cannot be read now (the alarms
        of a device that is off, the settings that only the device gives) stays as it was."""
        did = data.info["id"]
        modules = [m for m in (data.description or {}).get("modules") or [] if isinstance(m, dict) and isinstance(m.get("id"), str)]
        # The settings are read from the device: at most every quarter of an hour, and only when it is connected.
        settle = self.advanced and data.online and time.monotonic() - data.settings_at > POLL_WITH_LIVE and any(m.get("settings") is True for m in modules)
        # All together: what is read does not wait for the rest. The alarms of a device that is off are not read (the cloud
        # answers only for a connected one): they stay as they were. The sums are the cloud's: also with the device off.
        asks: list[tuple[str, str | None, Any]] = []
        if data.online:
            asks += [("alarms", None, self.api.alarms(did)), ("silences", None, self.api.silences(did))]
        for m in modules:
            if isinstance(m.get("parts"), dict) and m["parts"].get("stats") is True:
                asks.append(("stats", m["id"], self.api.stats(did, m["id"])))
            if settle and m.get("settings") is True:
                asks.append(("settings", m["id"], self.api.settings(did, m["id"])))
        answers = await asyncio.gather(*(a[2] for a in asks), return_exceptions=True)
        for (what, mid, _), answer in zip(asks, answers):
            if isinstance(answer, SmartiLabAuthError):
                raise answer
            if isinstance(answer, BaseException):
                LOGGER.debug("SmartiLab: %s of %s %s is not read now: %s", what, did, mid or "", answer)
                continue
            if what in ("alarms", "silences"):
                setattr(data, what, list((answer or {}).get(what) or []))
            elif what == "stats":
                data.stats[str(mid)] = answer or {}
            else:
                data.settings[str(mid)] = [i for i in (answer or {}).get("items") or [] if isinstance(i, dict)]
        if settle:
            data.settings_at = time.monotonic()

    def soon(self, device: str, data: dict[str, Any]) -> None:
        """A value of a part the cloud keeps changed: its sums read again in half a minute, once for many changes."""
        dev = (self.data or {}).get(device)
        module = next((m for m in (dev.description or {}).get("modules") or [] if isinstance(m, dict) and m.get("id") == data.get("module")), None) if dev else None
        if module is None or not isinstance(data.get("part"), str) or not (isinstance(module.get("parts"), dict) and module["parts"].get("stats") is True):
            return
        if device not in self._soon:
            self._soon[device] = self.hass.loop.call_later(30, self._again, device)

    def _again(self, device: str) -> None:
        self._soon.pop(device, None)
        self.hass.async_create_task(self.refresh_extras(device))

    async def refresh_extras(self, device: str) -> None:
        """An alarm went off or came back, a catch: what the cloud knows about that device, read again now."""
        dev = (self.data or {}).get(device)
        if dev is None or dev.description is None:
            return
        try:
            await self._extras(dev)
        except SmartiLabError as err:
            LOGGER.debug("SmartiLab: %s not read again: %s", device, err)
            return
        self._points(dev)
        self.async_update_listeners()

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
