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
from .model import Point, value_of

# The codes of the API that Home Assistant says in words (translations, "exceptions").
_SAID = {"offline", "on_hold", "timeout", "no_remote", "not_writable", "read_only", "slow_down", "unreachable", "no_scope"}
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
        dev = coordinator.data[point.device]
        self._attr_device_info = device_info(dev, site) if point.part is None else _part_info(dev, point, coordinator.parents.get(point.device))

    @property
    def device_data(self) -> DeviceData | None:
        return (self.coordinator.data or {}).get(self.point.device)

    @property
    def available(self) -> bool:
        dev = self.device_data
        return super().available and dev is not None and dev.problem is None and dev.online

    @property
    def value(self) -> Any:
        dev = self.device_data
        return value_of(dev.state if dev else None, self.point)

    async def _send(self, write: bool, value: Any = None, shown: Any = None) -> None:
        """Writes the property, or runs the action. The device must be connected; the outcome is said.
        ``shown``: what to show until the live channel confirms, when it is not ``value`` (a light)."""
        api = self.coordinator.api
        p = self.point
        try:
            outcome = await (api.write(p.device, p.module, p.part, p.id, value) if write else api.run(p.device, p.module, p.part, p.id))
        except SmartiLabError as err:
            key = err.code if err.code in _SAID else "command_failed"
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key=key, translation_placeholders={"error": str(err)}) from err
        status = (outcome or {}).get("status")
        if status == "not_found":
            # The description changed: read it again, the entities follow.
            await self.coordinator.async_request_refresh()
        if status not in ("ok", "pending"):
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="refused", translation_placeholders={"status": str(status)})
        if write and status == "ok":
            # The device said yes: show it now, the live channel confirms.
            self.coordinator.changed(p.device, {"module": p.module, "part": p.part, "property": p.id,
                                                "value": value if shown is None else shown, "at": None})


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
