"""The actions of the integration: what the console does on a device that is not an entity (from 0.2.0).

    smartilab.run_action        a command of a module with its input (a schedule, the name of a trap, a favourite)
    smartilab.get_module_state  what a module says about itself (the schedules of a relay board, the list of the traps)
    smartilab.set_alarm         sets or changes an alarm on a number, or a "no data"
    smartilab.remove_alarm      removes one
    smartilab.record_service    a service visit on the traps, with a note
    smartilab.get_part_events   the last events of a trap
    smartilab.get_part_stats    the sums of the traps in a period

Each one is for a SmartiLab device (or a part of it, a trap) picked in Home Assistant. The sensitive commands are
never there: Home Assistant does not get that permission. The answers that read come back as the action's response.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .api import SmartiLabApi, SmartiLabError
from .const import DOMAIN
from .entity import _SAID, refused

_DEVICE = vol.Required("device_id")
_MODULE = vol.Required("module")
_SERVICES = ["cleaning", "refill", "battery", "replace", "move", "check", "other"]

_SCHEMAS: dict[str, vol.Schema] = {
    "run_action": vol.Schema({_DEVICE: cv.string, _MODULE: cv.string, vol.Required("action"): cv.string,
                              vol.Optional("input"): dict, vol.Optional("confirm", default=False): cv.boolean}),
    "get_module_state": vol.Schema({_DEVICE: cv.string, _MODULE: cv.string}),
    "set_alarm": vol.Schema({_DEVICE: cv.string, vol.Optional("alarm_id"): cv.string, vol.Optional("module"): cv.string,
                             vol.Optional("property"): cv.string, vol.Optional("part", default=False): cv.boolean,
                             vol.Optional("kind"): vol.In(["above", "below", "no_data"]), vol.Optional("level"): vol.Coerce(float),
                             vol.Optional("minutes"): vol.Coerce(int), vol.Optional("back"): cv.boolean}),
    "remove_alarm": vol.Schema({_DEVICE: cv.string, vol.Required("alarm_id"): cv.string, vol.Optional("no_data", default=False): cv.boolean}),
    "record_service": vol.Schema({_DEVICE: vol.Any(cv.string, [cv.string]), vol.Required("type"): vol.In(_SERVICES), vol.Optional("note"): cv.string}),
    "get_part_events": vol.Schema({_DEVICE: cv.string, vol.Optional("limit", default=50): vol.All(vol.Coerce(int), vol.Range(min=1, max=200))}),
    "get_part_stats": vol.Schema({_DEVICE: cv.string, _MODULE: cv.string, vol.Optional("from"): cv.string, vol.Optional("to"): cv.string}),
}
_READS = {"get_module_state", "get_part_events", "get_part_stats"}


def setup(hass: HomeAssistant) -> None:
    """The actions, once for the integration: each call finds the entry of its device."""

    async def handle(call: ServiceCall) -> ServiceResponse:
        try:
            answer = await _run(hass, call.service, dict(call.data))
        except SmartiLabError as err:
            key = err.code if err.code in _SAID else "command_failed"
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key=key, translation_placeholders={"error": str(err)}) from err
        return answer if call.return_response else None

    for name, schema in _SCHEMAS.items():
        hass.services.async_register(DOMAIN, name, handle, schema=schema,
                                     supports_response=SupportsResponse.ONLY if name in _READS else SupportsResponse.OPTIONAL)


def _target(hass: HomeAssistant, device_id: str) -> tuple[SmartiLabApi, str, str | None, str | None]:
    """The client of the entry, the SmartiLab device, and the module and part when a part (a trap) was picked."""
    entry = dr.async_get(hass).async_get(device_id)
    ours = next((i[1] for i in entry.identifiers if i[0] == DOMAIN), None) if entry else None
    if entry is None or ours is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_a_device")
    for config in entry.config_entries:
        loaded = hass.config_entries.async_get_entry(config)
        runtime = getattr(loaded, "runtime_data", None) if loaded else None
        if runtime is not None:
            device, _, rest = ours.partition("/")
            module, _, part = rest.partition("/")
            return runtime.coordinator.api, device, module or None, part or None
    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_a_device")


async def _run(hass: HomeAssistant, name: str, data: dict[str, Any]) -> dict[str, Any]:
    if name == "record_service":
        # One or more traps of the same hub, or the hub itself (all its traps).
        picked = data["device_id"] if isinstance(data["device_id"], list) else [data["device_id"]]
        targets = [_target(hass, d) for d in picked]
        api, device, module, _ = targets[0]
        if any(t[1] != device for t in targets):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="one_hub")
        parts = [t[3] for t in targets if t[3]]
        if module is None:
            module = await _kept_module(api, device)
        return await api.service(device, module, parts if parts and len(parts) == len(targets) else "all", data["type"], data.get("note"))
    api, device, module, part = _target(hass, data["device_id"])
    if name == "run_action":
        outcome = await api.run(device, data["module"], None, data["action"], data.get("input"), data.get("confirm", False))
        refused(outcome)
        return outcome
    if name == "get_module_state":
        return await api.document(device, data["module"])
    if name == "set_alarm":
        no_data = data.get("kind") == "no_data"
        fields = {k: data[k] for k in (("minutes", "back") if no_data else ("level", "minutes", "back")) if k in data}
        if data.get("kind") in ("above", "below"):
            fields["side"] = data["kind"]
        if not data.get("alarm_id"):
            if not data.get("module") or not data.get("property") or not data.get("kind"):
                raise ServiceValidationError(translation_domain=DOMAIN, translation_key="alarm_fields")
            fields |= {"module": data["module"], "property": data["property"], "part": data.get("part", False)}
        return await api.alarm(device, data.get("alarm_id"), no_data, fields)
    if name == "remove_alarm":
        await api.unalarm(device, data["alarm_id"], data.get("no_data", False))
        return {"removed": data["alarm_id"]}
    if name == "get_part_events":
        if module is None or part is None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_a_part")
        return await api.events(device, module, part, data.get("limit", 50))
    if name == "get_part_stats":
        return await api.stats(device, data["module"], data.get("from"), data.get("to"))
    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_a_device")


async def _kept_module(api: SmartiLabApi, device: str) -> str:
    """The module whose parts the cloud keeps (the traps of a hub), from the description."""
    for module in (await api.description(device)).get("modules") or []:
        if isinstance(module, dict) and isinstance(module.get("parts"), dict) and module["parts"].get("stats") is True:
            return str(module["id"])
    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_parts")
