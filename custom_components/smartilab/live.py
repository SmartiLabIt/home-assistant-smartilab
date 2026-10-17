"""The live channel of the SmartiLab cloud: a WebSocket on which the changes of the devices arrive.

A ticket from ``POST /live/ticket`` (one minute), the WebSocket at the address it gives, the ticket as
the first message, then ``subscribe`` to every device of the account. A connection lasts one hour at
most; when it drops the channel is opened again and resumed from the last cursor, so no change is
lost (the cloud keeps one hour of events). If resuming is no longer possible the state is read again.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import ClientError, WSMsgType
from yarl import URL

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SmartiLabApi, SmartiLabAuthError, SmartiLabError
from .const import LOGGER
from .coordinator import SmartiLabCoordinator

# Close codes of the channel (docs: the AsyncAPI of the live channel).
_BAD_TICKET = 4401
_TOO_MANY = 4429
_FIRST_WAIT = 5
_LONGEST_WAIT = 300


class LiveChannel:
    """Keeps the live channel open while the config entry is loaded."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, coordinator: SmartiLabCoordinator, api: SmartiLabApi,
                 server: str, browser: str) -> None:
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._api = api
        self._server = URL(server)
        self._browser = URL(browser)
        self._cursor: str | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = self._entry.async_create_background_task(self._hass, self._run(), "smartilab live channel")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self._coordinator.set_live(False)

    def _address(self, url: str) -> str:
        """The address of the WebSocket. A development console can be reached from Home Assistant at another
        address than the one the browser uses: the address given for the browser is turned into the other."""
        given = URL(url)
        if self._server == self._browser or (given.host, given.port) != (self._browser.host, self._browser.port):
            return url
        scheme = "wss" if self._server.scheme == "https" else "ws"
        return str(given.with_scheme(scheme).with_host(self._server.host or "").with_port(self._server.port))

    async def _run(self) -> None:
        wait = _FIRST_WAIT
        while True:
            try:
                closed = await self._connect()
                wait = _FIRST_WAIT if closed != _TOO_MANY else 60
            except asyncio.CancelledError:
                raise
            except (SmartiLabAuthError, ConfigEntryAuthFailed):
                # The access is no longer valid: Home Assistant asks to sign in again.
                self._coordinator.set_live(False)
                self._entry.async_start_reauth(self._hass)
                return
            except SmartiLabError as err:
                LOGGER.debug("SmartiLab live channel: %s", err)
                wait = 300 if err.code == "not_available" else min(wait * 2, _LONGEST_WAIT)
            except (ClientError, TimeoutError, ValueError) as err:
                LOGGER.debug("SmartiLab live channel lost: %s", err)
                wait = min(wait * 2, _LONGEST_WAIT)
            self._coordinator.set_live(False)
            await asyncio.sleep(wait)

    async def _connect(self) -> int | None:
        ticket = await self._api.live_ticket()
        session = async_get_clientsession(self._hass)
        async with session.ws_connect(self._address(str(ticket["url"])), heartbeat=55, timeout=20) as ws:
            await ws.send_json({"type": "auth", "ticket": ticket["ticket"]})
            ready = await ws.receive_json(timeout=15)
            if not isinstance(ready, dict) or ready.get("type") != "ready":
                raise SmartiLabError(0, "not_ready", str(ready)[:120])
            subscribe: dict[str, Any] = {"type": "subscribe", "devices": "all"}
            if self._cursor:
                subscribe["after"] = self._cursor
            await ws.send_json(subscribe)
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    break
                self._message(json.loads(msg.data))
            return ws.close_code

    def _message(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        if kind == "subscribed":
            self._cursor = msg.get("cursor") or self._cursor
            self._coordinator.set_live(True)
            # The first time, or after too long away: what changed in between is read again.
            if msg.get("resumed") is not True:
                self._hass.async_create_task(self._coordinator.async_request_refresh())
            return
        if kind == "unsubscribed":
            # A device the account can no longer see: the list is read again.
            self._hass.async_create_task(self._coordinator.async_request_refresh())
            return
        if kind != "event":
            return
        self._cursor = msg.get("cursor") or self._cursor
        device, event, data = msg.get("device"), msg.get("event"), msg.get("data") or {}
        if not isinstance(device, str):
            return
        if event == "property.changed":
            self._coordinator.changed(device, data)
        elif event in ("device.online", "device.offline"):
            self._coordinator.connected(device, event == "device.online")
        elif event in ("description.changed", "license.changed", "firmware.done"):
            # What the device is made of, or what it may do, changed: read it again.
            self._hass.async_create_task(self._coordinator.async_request_refresh())
