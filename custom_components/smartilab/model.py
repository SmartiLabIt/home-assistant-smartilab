"""What a SmartiLab device is made of, as Home Assistant sees it.

No Home Assistant code here: the description that the cloud gives (``GET /devices/{id}/description``)
becomes a list of points, each one a property or an action of a module or of one of its parts, with
the platform it belongs to. Kinds and classes that are not known are left out: the API may add new
ones at any time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Which platform a property goes to, by its kind and whether it can be written.
_WRITABLE = {"toggle": "switch", "light": "light", "number": "number", "text": "text", "select": "select"}
_READ_ONLY = {"toggle": "binary_sensor", "light": "binary_sensor", "number": "sensor", "flag": "binary_sensor",
              "text": "sensor", "select": "sensor"}
# The actions a button can run: simple ones (no input), with the scopes Home Assistant asks for.
_BUTTON_SCOPES = {"devices:control", "devices:read"}


@dataclass(frozen=True)
class Point:
    """A property or an action of a module, or of a part of a module."""

    device: str
    module: str
    part: str | None
    id: str
    action: bool
    platform: str
    name: str
    kind: str = ""
    klass: str | None = None
    unit: str | None = None
    decimals: int | None = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    options: tuple[tuple[str, str], ...] = ()
    technical: bool = False

    @property
    def uid(self) -> str:
        """Stable and unique: the device, the module, the part, and what it is."""
        return f"{self.device}/{self.module}/{self.part or '-'}/{'a' if self.action else 'p'}:{self.id}"


@dataclass(frozen=True)
class Part:
    """A sub-device reached through a module, such as a trap of a hub."""

    device: str
    module: str
    id: str
    name: str

    @property
    def uid(self) -> str:
        return f"{self.device}/{self.module}/{self.id}"


def platform_of(prop: dict[str, Any]) -> str | None:
    """The platform of a property, or None when its kind is not known."""
    kind = prop.get("kind")
    if not isinstance(kind, str):
        return None
    return (_WRITABLE if prop.get("writable") is True else _READ_ONLY).get(kind)


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _property(device: str, module: str, part: str | None, prop: dict[str, Any]) -> Point | None:
    platform = platform_of(prop)
    pid = prop.get("id")
    if platform is None or not isinstance(pid, str) or pid == "":
        return None
    options = tuple((str(o["id"]), str(o.get("name") or o["id"])) for o in prop.get("options") or [] if isinstance(o, dict) and "id" in o)
    if prop.get("kind") == "select" and not options:
        return None
    decimals = prop.get("decimals")
    return Point(device=device, module=module, part=part, id=pid, action=False, platform=platform,
                 name=str(prop.get("name") or pid), kind=str(prop["kind"]),
                 klass=prop["class"] if isinstance(prop.get("class"), str) else None,
                 unit=prop["unit"] if isinstance(prop.get("unit"), str) and prop["unit"] != "" else None,
                 decimals=decimals if isinstance(decimals, int) and not isinstance(decimals, bool) else None,
                 minimum=_number(prop.get("min")), maximum=_number(prop.get("max")), step=_number(prop.get("step")),
                 options=options, technical=prop.get("technical") is True)


def _action(device: str, module: str, part: str | None, act: dict[str, Any]) -> Point | None:
    aid = act.get("id")
    # A button runs a simple action only: nothing to type, nothing to confirm, within the scopes given.
    if not isinstance(aid, str) or aid == "" or act.get("simple") is not True or act.get("confirm") is True \
            or act.get("scope", "devices:control") not in _BUTTON_SCOPES:
        return None
    return Point(device=device, module=module, part=part, id=aid, action=True, platform="button", name=str(act.get("name") or aid))


def points(description: dict[str, Any]) -> tuple[list[Point], list[Part]]:
    """Every point of a device, and its parts."""
    device = str(description.get("device", {}).get("id", ""))
    out: list[Point] = []
    parts: list[Part] = []
    for module in description.get("modules") or []:
        mid = module.get("id")
        if not isinstance(mid, str) or mid == "":
            continue
        for prop in module.get("properties") or []:
            if (p := _property(device, mid, None, prop)) is not None:
                out.append(p)
        for act in module.get("actions") or []:
            if (a := _action(device, mid, None, act)) is not None:
                out.append(a)
        group = module.get("parts")
        if not isinstance(group, dict):
            continue
        for item in group.get("items") or []:
            part = item.get("id") if isinstance(item, dict) else None
            if not isinstance(part, str) or part == "":
                continue
            parts.append(Part(device=device, module=mid, id=part, name=str(item.get("name") or part)))
            for prop in group.get("properties") or []:
                if (p := _property(device, mid, part, prop)) is not None:
                    out.append(p)
            for act in group.get("actions") or []:
                if (a := _action(device, mid, part, act)) is not None:
                    out.append(a)
    return out, parts


def value_of(state: dict[str, Any] | None, point: Point) -> Any:
    """The last known value of a point; None when it is not known."""
    if not isinstance(state, dict):
        return None
    module = (state.get("modules") or {}).get(point.module)
    if not isinstance(module, dict):
        return None
    readings = module.get("properties") if point.part is None else (module.get("parts") or {}).get(point.part)
    reading = readings.get(point.id) if isinstance(readings, dict) else None
    return reading.get("value") if isinstance(reading, dict) else None


def apply_change(state: dict[str, Any], data: dict[str, Any]) -> bool:
    """A property.changed event of the live channel, written into the state held. True if it was valid."""
    module, prop = data.get("module"), data.get("property")
    if not isinstance(module, str) or not isinstance(prop, str):
        return False
    held = state.setdefault("modules", {}).setdefault(module, {})
    part = data.get("part")
    if isinstance(part, str) and part != "":
        readings = held.setdefault("parts", {}).setdefault(part, {})
    else:
        readings = held.setdefault("properties", {})
    readings[prop] = {"value": data.get("value"), "at": data.get("at")}
    return True
