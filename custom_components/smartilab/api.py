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

from .const import API_PATH, LOGGER


class SmartiLabError(Exception):
    """An answer of the API that is not a success: ``code`` is the stable code of the problem."""

    def __init__(self, status: int, code: str, detail: str = "") -> None:
        super().__init__(f"{status} {code}{': ' + detail if detail else ''}")
        self.status = status
        self.code = code


class SmartiLabAuthError(SmartiLabError):
    """The access is no longer valid: sign in again."""


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

    async def run(self, device: str, module: str, part: str | None, action: str) -> dict[str, Any]:
        path = f"/devices/{device}/modules/{module}/actions/{action}" + (f"?part={quote(part)}" if part else "")
        return await self._request("POST", path, {}, once=True)

    async def live_ticket(self) -> dict[str, Any]:
        return await self._request("POST", "/live/ticket", {})
