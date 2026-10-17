"""What every SmartiLab entity shares: its device, whether it is available, how it sends a command."""

from __future__ import annotations

from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SmartiLabError
from .const import DOMAIN, MANUFACTURER
from .coordinator import DeviceData, SmartiLabCoordinator
from .model import Point, extra_value, value_of

# The codes of the API that Home Assistant says in words (translations, "exceptions").
_SAID = {"offline", "on_hold", "timeout", "no_remote", "not_writable", "read_only", "slow_down", "unreachable", "no_scope", "owner_only"}
# What the device answered when it did not do it, in words (translations, "exceptions": refused_<status>).
_REFUSED = {"denied", "invalid", "not_found"}
# What the cloud keeps by itself: it is there even when the device is off.
_KEPT = {"alarm", "count", "service"}
# From Home Assistant 2026.8 a part names its device by the id in the device registry (via_device_id);
# before, by the identifiers of the device (via_device, which stops working with 2027.8).
_VIA_ID = "via_device_id" in DeviceInfo.__annotations__


class SmartiLabEntity(CoordinatorEntity[SmartiLabCoordinator]):
    """A property or an action of a SmartiLab device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SmartiLabCoordinator, point: Point, site: str) -> None:
        """``site``: the address of the SmartiLab site, as a browser opens it (for "Visit")."""
        super().__init__(coordinator)
        self.point = point
        self._attr_unique_id = point.uid
        self._attr_name = point.name
        if point.technical:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif point.extra == "setting":
            # How the module works: with the configuration of the device, as in the console its Settings.
            self._attr_entity_category = EntityCategory.CONFIG
        dev = coordinator.data[point.device]
        self._attr_device_info = device_info(dev, site) if point.part is None else _part_info(dev, point, coordinator.parents.get(point.device))

    @property
    def device_data(self) -> DeviceData | None:
        return (self.coordinator.data or {}).get(self.point.device)

    @property
    def available(self) -> bool:
        dev = self.device_data
        if not (super().available and dev is not None and dev.problem is None):
            return False
        # The alarms, the sums and the service visits the cloud keeps: also with the device off.
        return dev.online or self.point.extra in _KEPT

    @property
    def value(self) -> Any:
        dev = self.device_data
        if self.point.extra:
            return None if dev is None else extra_value(self.point, dev.alarms, dev.silences, dev.stats, dev.settings)
        return value_of(dev.state if dev else None, self.point)

    async def _send(self, write: bool, value: Any = None, shown: Any = None) -> None:
        """Writes the property, or runs the action; a setting goes to the settings of the module, a service visit is
        written on the cloud. The outcome is said: never "done" when the device said no.
        ``shown``: what to show until the live channel confirms, when it is not ``value`` (a light)."""
        api = self.coordinator.api
        p = self.point
        try:
            if p.extra == "service":
                await api.service(p.device, p.module, [p.part] if p.part else "all", p.id)
                await self.coordinator.refresh_extras(p.device)
                return
            if p.extra == "setting":
                outcome = await api.set_settings(p.device, p.module, {p.id: value})
            else:
                outcome = await (api.write(p.device, p.module, p.part, p.id, value) if write else api.run(p.device, p.module, p.part, p.id))
        except SmartiLabError as err:
            key = err.code if err.code in _SAID else "command_failed"
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key=key, translation_placeholders={"error": str(err)}) from err
        status = (outcome or {}).get("status")
        if status == "not_found":
            # The description changed: read it again, the entities follow.
            await self.coordinator.async_request_refresh()
        refused(outcome)
        if p.extra == "setting":
            # The device took it: the value of now is the new one.
            dev = self.device_data
            for item in (dev.settings.get(p.module, []) if dev else []):
                if item.get("id") == p.id:
                    item["value"] = value
            self.async_write_ha_state()
            return
        if write and status == "ok":
            # The device said yes: show it now, the live channel confirms.
            self.coordinator.changed(p.device, {"module": p.module, "part": p.part, "property": p.id,
                                                "value": value if shown is None else shown, "at": None})


def refused(outcome: dict[str, Any] | None) -> None:
    """The device answered and did not do it: an error, in words (a schedule holding the channel, a value it did not take)."""
    status = (outcome or {}).get("status", "ok")
    if status in ("ok", "pending"):
        return
    field = str((outcome or {}).get("field") or "")
    raise HomeAssistantError(translation_domain=DOMAIN, translation_key=f"refused_{status}" if status in _REFUSED else "refused",
                             translation_placeholders={"status": str(status), "field": field})


def device_info(dev: DeviceData, site: str) -> DeviceInfo:
    """A SmartiLab device in the device registry: name, product, firmware, the console to open it."""
    info = dev.info
    product = info.get("product") or {}
    firmware = info.get("firmware") or {}
    did = str(info.get("id"))
    return DeviceInfo(identifiers={(DOMAIN, did)}, name=str(info.get("name") or did), manufacturer=MANUFACTURER,
                      model=product.get("title"), model_id=product.get("code"), sw_version=firmware.get("version"),
                      hw_version=firmware.get("board"), configuration_url=site.rstrip("/") + "/console/")


def _part_info(dev: DeviceData, point: Point, parent: str | None) -> DeviceInfo:
    """A part (a trap of a hub) as a device of its own, under its device. ``parent``: the id of the device in
    the device registry, where it went first (__init__.py)."""
    part = next((x for x in dev.parts if x.module == point.module and x.id == point.part), None)
    out = DeviceInfo(identifiers={(DOMAIN, f"{point.device}/{point.module}/{point.part}")}, name=part.name if part else point.part,
                     manufacturer=MANUFACTURER)
    if _VIA_ID and parent is not None:
        out["via_device_id"] = parent
    elif not _VIA_ID:
        out["via_device"] = (DOMAIN, point.device)
    return out
