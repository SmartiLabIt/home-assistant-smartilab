"""What a SmartiLab device is made of, as Home Assistant sees it.

No Home Assistant code here: the description that the cloud gives (``GET /devices/{id}/description``)
becomes a list of points, each one a property or an action of a module or of one of its parts, with
the platform it belongs to. Kinds and classes that are not known are left out: the API may add new
ones at any time.

From 0.2.0 also what the cloud knows about a device besides what it declares (``extras``): the alarms
set on its numbers and whether they went off, the sums of the period of the parts it keeps (the traps
of a hub) and the service visits on them, and the settings of the modules. Everything the console shows
and does on a device, except the sensitive commands and the system part.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Which platform a property goes to, by its kind and whether it can be written.
_WRITABLE = {"toggle": "switch", "light": "light", "number": "number", "text": "text", "select": "select"}
_READ_ONLY = {"toggle": "binary_sensor", "light": "binary_sensor", "number": "sensor", "flag": "binary_sensor",
              "text": "sensor", "select": "sensor"}
# The actions a button can run: simple ones (no input), with the scopes Home Assistant asks for; with the
# advanced commands also the commands of the module that need nothing to type.
_BUTTON_SCOPES = {"devices:control", "devices:read"}

# The words around the names the cloud gives, in the languages of the site.
_WORDS = {
    "it": {"below": "sotto", "above": "sopra", "no_data": "nessun dato da più di {h} h", "period": "nel periodo", "all": "(tutte)"},
    "en": {"below": "below", "above": "above", "no_data": "no data for over {h} h", "period": "this period", "all": "(all)"},
    "de": {"below": "unter", "above": "über", "no_data": "seit über {h} h keine Daten", "period": "im Zeitraum", "all": "(alle)"},
    "fr": {"below": "sous", "above": "au-dessus de", "no_data": "aucune donnée depuis plus de {h} h", "period": "sur la période", "all": "(toutes)"},
    "es": {"below": "por debajo de", "above": "por encima de", "no_data": "sin datos desde hace más de {h} h", "period": "en el periodo", "all": "(todas)"},
}
# The types of a setting (GET …/modules/{m}/settings) and the platform they go to; "any" has no box.
_SETTING_PLATFORMS = {"boolean": "switch", "string": "text", "integer": "number", "number": "number"}


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
    # What the cloud knows besides what the device declares: "alarm" (an alarm or a "no data", on if it went
    # off), "count" (a sum of the period), "service" (a service visit, ``id`` its type; on the module: all the
    # parts), "setting" (a setting of the module). Empty: a property or an action of the device.
    extra: str = ""

    @property
    def uid(self) -> str:
        """Stable and unique: the device, the module, the part, and what it is."""
        what = self.extra if self.extra else ("a" if self.action else "p")
        return f"{self.device}/{self.module}/{self.part or '-'}/{what}:{self.id}"


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


def _action(device: str, module: str, part: str | None, act: dict[str, Any], advanced: bool = False) -> Point | None:
    aid = act.get("id")
    # A button runs an action with nothing to type and nothing to confirm: a simple one within the scopes given, or with
    # the advanced commands a command of the module. Never a sensitive one, nor one that only reads (nothing would show).
    if not isinstance(aid, str) or aid == "" or act.get("confirm") is True or act.get("sensitive") is True or act.get("input") \
            or act.get("anyInput") is True:
        return None
    scope = act.get("scope", "devices:control")
    simple = act.get("simple") is True and scope in _BUTTON_SCOPES
    if not simple and not (advanced and scope == "devices:advanced" and act.get("readOnly") is not True):
        return None
    return Point(device=device, module=module, part=part, id=aid, action=True, platform="button", name=str(act.get("name") or aid))


def points(description: dict[str, Any], advanced: bool = False) -> tuple[list[Point], list[Part]]:
    """Every point of a device, and its parts. ``advanced``: the access has the advanced commands."""
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
            if (a := _action(device, mid, None, act, advanced)) is not None:
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
                if (a := _action(device, mid, part, act, advanced)) is not None:
                    out.append(a)
    return out, parts


def extras(description: dict[str, Any], alarms: list[dict[str, Any]], silences: list[dict[str, Any]],
           settings: dict[str, list[dict[str, Any]]], lang: str, control: bool = True) -> list[Point]:
    """What the cloud knows about a device besides what it declares, as points (``extra``).

    ``alarms`` and ``silences`` as ``GET …/alarms`` and ``GET …/silences`` give them; ``settings`` the items of
    ``GET …/modules/{m}/settings`` by module (only the modules that could be read: the device must be connected).
    ``control``: the access is not read-only on this device (the service visits are buttons).
    """
    words = _WORDS.get(lang[:2], _WORDS["en"])
    device = str(description.get("device", {}).get("id", ""))
    out: list[Point] = []
    for module in description.get("modules") or []:
        mid = module.get("id")
        if not isinstance(mid, str) or mid == "":
            continue
        group = module.get("parts") if isinstance(module.get("parts"), dict) else {}
        items = [str(i["id"]) for i in group.get("items") or [] if isinstance(i, dict) and isinstance(i.get("id"), str) and i["id"] != ""]
        # The alarms on the numbers of the module, or of its parts: one for each part.
        for rule, silent in [(r, False) for r in alarms] + [(r, True) for r in silences]:
            if not isinstance(rule, dict) or rule.get("module") != mid or not isinstance(rule.get("id"), str):
                continue
            name = str(rule.get("name") or rule.get("property") or rule["id"])
            if silent:
                name = f"{name}: " + words["no_data"].replace("{h}", str(max(1, round(int(rule.get("minutes") or 60) / 60))))
            else:
                level = rule.get("level")
                unit = str(rule.get("unit") or "")
                shown = f"{level}{unit}" if unit == "%" else (f"{level} {unit}" if unit else f"{level}")
                name = f"{name} {words['above' if rule.get('side') == 'above' else 'below']} {shown}"
            for part in items if rule.get("part") is True else [None]:
                out.append(Point(device=device, module=mid, part=part, id=rule["id"], action=False, platform="binary_sensor",
                                 name=name, kind="flag", klass="problem", extra="alarm"))
        # The parts the cloud keeps (the traps): the sums of the summary in the period, and the service visits.
        if group.get("stats") is True:
            summary = [k for k in group.get("kinds") or [] if isinstance(k, dict) and k.get("summary") is True and isinstance(k.get("id"), str)]
            services = [s for s in group.get("services") or [] if isinstance(s, dict) and isinstance(s.get("id"), str) and s["id"] != "other"]
            for part in [None, *items]:
                for kind in summary:
                    out.append(Point(device=device, module=mid, part=part, id=kind["id"], action=False, platform="sensor",
                                     name=f"{kind.get('name') or kind['id']} {words['period']}", kind="number", extra="count"))
                for service in services if control else []:
                    out.append(Point(device=device, module=mid, part=part, id=service["id"], action=True, platform="button",
                                     name=str(service.get("name") or service["id"]) + ("" if part else f" {words['all']}"), extra="service"))
        # The settings of the module, as configuration: a switch, a number within its limits, a text. Never a secret.
        for item in settings.get(mid, []):
            sid, kind = item.get("id"), str(item.get("type") or "")
            if not isinstance(sid, str) or sid == "" or item.get("secret") is True:
                continue
            platform = _SETTING_PLATFORMS.get(kind)
            if platform is None:
                continue
            whole = kind == "integer"
            out.append(Point(device=device, module=mid, part=None, id=sid, action=False, platform=platform, name=str(item.get("name") or _label(sid)),
                             kind="number" if platform == "number" else ("toggle" if platform == "switch" else "text"),
                             decimals=0 if whole else None, minimum=_number(item.get("min")), maximum=_number(item.get("max")),
                             step=1.0 if whole else None, extra="setting"))
    return out


def _label(key: str) -> str:
    """A name from the key of a setting, until the firmware gives one: pulseMs → Pulse ms, liquid_low → Liquid low."""
    spaced = "".join(" " + c.lower() if c.isupper() else (" " if c in "_-." else c) for c in key).strip()
    return spaced[:1].upper() + spaced[1:] if spaced else key


def extra_value(point: Point, alarms: list[dict[str, Any]], silences: list[dict[str, Any]], stats: dict[str, dict[str, Any]],
                settings: dict[str, list[dict[str, Any]]]) -> Any:
    """The value now of a point of ``extras``; None when it is not known."""
    if point.extra == "alarm":
        rule = next((r for r in [*alarms, *silences] if isinstance(r, dict) and r.get("id") == point.id), None)
        if rule is None or rule.get("state") == "unknown":
            return None
        if point.part is None:
            return rule.get("state") == "raised"
        # The parts that are not fine are listed with their state; the others are fine.
        return next((p.get("state") for p in rule.get("parts") or [] if isinstance(p, dict) and p.get("part") == point.part), "ok") == "raised"
    if point.extra == "count":
        sums = stats.get(point.module)
        if not isinstance(sums, dict):
            return None
        if point.part is None:
            return int((sums.get("totals") or {}).get(point.id) or 0)
        part = next((p for p in sums.get("parts") or [] if isinstance(p, dict) and p.get("id") == point.part), None)
        return int(((part or {}).get("counts") or {}).get(point.id) or 0)
    if point.extra == "setting":
        item = next((i for i in settings.get(point.module, []) if i.get("id") == point.id), None)
        return None if item is None else item.get("value")
    return None


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
