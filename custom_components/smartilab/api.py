"""The SmartiLab Cloud API v1, as the integration uses it.

Every request carries the OAuth access of the config entry (renewed by Home Assistant when it
expires). Errors are RFC 9457 problems with a stable ``code``: they become ``SmartiLabError``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import json
from typing import Any
from urllib.parse import quote
import uuid

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import API_PATH, CLIENT_ID, LOGGER, REVOKE_PATH


class SmartiLabError(Exception):
    """An answer of the API that is not a success: ``code`` is the stable code of the problem."""

    def __init__(self, status: int, code: str, detail: str = "") -> None:
        super().__init__(f"{status} {code}{': ' + detail if detail else ''}")
        self.status = status
        self.code = code


class SmartiLabAuthError(SmartiLabError):
    """The access is no longer valid: sign in again."""


async def give_back(session: ClientSession, server: str, token: dict[str, Any] | None) -> None:
    """The access goes back to the cloud (RFC 7009): it closes there, and leaves the Accesses of the console.
    When the entry is removed, or an access was asked and is not used. Whatever happens, nothing is raised."""
    secret = str((token or {}).get("refresh_token") or (token or {}).get("access_token") or "")
    if secret == "":
        return
    try:
        async with session.post(server.rstrip("/") + REVOKE_PATH, data={"token": secret, "client_id": CLIENT_ID}, timeout=ClientTimeout(total=15)) as resp:
            LOGGER.debug("SmartiLab: access given back: %s %s", resp.status, (await resp.text())[:400])
    except (ClientError, TimeoutError) as err:
        LOGGER.debug("SmartiLab: the access could not be given back: %s", err)


class SmartiLabApi:
    """A small client of the API v1."""

    def __init__(self, session: ClientSession, server: str, token: Callable[[], Awaitable[str]], language: str) -> None:
        self._session = session
        self._base = server.rstrip("/") + API_PATH
        self._token = token
        self._language = language

    async def _request(self, method: str, path: str, body: dict[str, Any] | None = None, *, once: bool = False) -> Any:
        headers = {"Authorization": f"Bearer {await self._token()}", "Accept": "application/json", "Accept-Language": self._language}
        if once:
            # A command acts once even if the request is sent again (a lost answer, a retry).
            headers["Idempotency-Key"] = str(uuid.uuid4())
        for attempt in range(2):
            try:
                async with self._session.request(method, self._base + path, json=body, headers=headers, timeout=ClientTimeout(total=45)) as resp:
                    text = await resp.text()
                    try:
                        payload = json.loads(text) if text else None
                    except ValueError:
                        payload = None
                    if resp.status < 400:
                        return payload
                    problem = payload if isinstance(payload, dict) else {}
                    code = str(problem.get("code") or problem.get("error") or "error")
                    if resp.status == 429 and attempt == 0:
                        # The limit belongs to the account: wait as long as the cloud says, once.
                        wait = min(int(resp.headers.get("Retry-After", "5") or 5), 30)
                        LOGGER.debug("SmartiLab: too many requests, waiting %s s", wait)
                        await asyncio.sleep(wait)
                        continue
                    if resp.status == 401:
                        raise SmartiLabAuthError(resp.status, code, str(problem.get("detail") or ""))
                    raise SmartiLabError(resp.status, code, str(problem.get("detail") or ""))
            except (ClientError, TimeoutError) as err:
                raise SmartiLabError(0, "unreachable", str(err)) from err
        raise SmartiLabError(429, "slow_down")

    async def me(self) -> dict[str, Any]:
        return await self._request("GET", "/me")

    async def devices(self) -> list[dict[str, Any]]:
        """Every device the account sees: its own and the ones shared with it."""
        out: list[dict[str, Any]] = []
        after: str | None = None
        for _ in range(50):
            page = await self._request("GET", "/devices?limit=100" + (f"&after={quote(after)}" if after else ""))
            out.extend(i for i in page.get("items") or [] if isinstance(i, dict) and isinstance(i.get("id"), str))
            after = page.get("next")
            if not after:
                break
        return out

    async def description(self, device: str) -> dict[str, Any]:
        return await self._request("GET", f"/devices/{device}/description")

    async def state(self, device: str) -> dict[str, Any]:
        return await self._request("GET", f"/devices/{device}/state")

    async def write(self, device: str, module: str, part: str | None, prop: str, value: Any) -> dict[str, Any]:
        path = f"/devices/{device}/modules/{module}/properties/{prop}" + (f"?part={quote(part)}" if part else "")
        return await self._request("PUT", path, {"value": value}, once=True)

    async def run(self, device: str, module: str, part: str | None, action: str, data: dict[str, Any] | None = None, confirm: bool = False) -> dict[str, Any]:
        """An action: a button, or a command of the module with its input (``data``). ``confirm`` for one that asks it."""
        path = f"/devices/{device}/modules/{module}/actions/{action}" + (f"?part={quote(part)}" if part else "")
        body: dict[str, Any] = {"input": data} if data else {}
        if confirm:
            body["confirm"] = True
        return await self._request("POST", path, body, once=True)

    async def settings(self, device: str, module: str) -> dict[str, Any]:
        """The settings of a module, read from the device (it must be connected)."""
        return await self._request("GET", f"/devices/{device}/modules/{module}/settings")

    async def set_settings(self, device: str, module: str, values: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", f"/devices/{device}/modules/{module}/settings", {"values": values}, once=True)

    async def document(self, device: str, module: str) -> dict[str, Any]:
        """What a module says about itself, in its own shape (the schedules of a relay board…)."""
        return await self._request("GET", f"/devices/{device}/modules/{module}/document")

    async def alarms(self, device: str) -> dict[str, Any]:
        return await self._request("GET", f"/devices/{device}/alarms")

    async def silences(self, device: str) -> dict[str, Any]:
        return await self._request("GET", f"/devices/{device}/silences")

    async def alarm(self, device: str, alarm: str | None, no_data: bool, fields: dict[str, Any]) -> dict[str, Any]:
        """A new alarm (above or below a level, or "no data"), or a change of one (``alarm``: its id)."""
        route = f"/devices/{device}/" + ("silences" if no_data else "alarms")
        if alarm:
            return await self._request("PATCH", f"{route}/{quote(alarm)}", fields, once=True)
        return await self._request("POST", route, fields, once=True)

    async def unalarm(self, device: str, alarm: str, no_data: bool) -> None:
        await self._request("DELETE", f"/devices/{device}/" + ("silences" if no_data else "alarms") + f"/{quote(alarm)}", once=True)

    async def stats(self, device: str, module: str, since: str | None = None, until: str | None = None) -> dict[str, Any]:
        """The sums of the events of the parts the cloud keeps (the traps of a hub), in a period."""
        query = "&".join(f"{k}={quote(v)}" for k, v in (("from", since), ("to", until)) if v)
        return await self._request("GET", f"/devices/{device}/modules/{module}/parts/stats" + (f"?{query}" if query else ""))

    async def events(self, device: str, module: str, part: str, limit: int = 50) -> dict[str, Any]:
        return await self._request("GET", f"/devices/{device}/modules/{module}/parts/{part}/events?limit={int(limit)}")

    async def service(self, device: str, module: str, parts: list[str] | str, kind: str, note: str | None = None) -> dict[str, Any]:
        """A service visit on parts (their ids, or "all"): written on the cloud, the device can be off."""
        body: dict[str, Any] = {"parts": parts, "type": kind}
        if note:
            body["note"] = note
        return await self._request("POST", f"/devices/{device}/modules/{module}/parts/services", body, once=True)

    async def live_ticket(self) -> dict[str, Any]:
        return await self._request("POST", "/live/ticket", {})
