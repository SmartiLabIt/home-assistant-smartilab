"""The part of the integration that needs no Home Assistant: descriptions become points, events become values.

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

# model.py alone, without the package (which needs Home Assistant). A dataclass wants its module known.
_SPEC = importlib.util.spec_from_file_location("smartilab_model", Path(__file__).parent.parent / "custom_components" / "smartilab" / "model.py")
model = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = model
_SPEC.loader.exec_module(model)

# As GET /devices/{id}/description gives it (the example of the contract, with more cases).
DESCRIPTION = {
    "device": {"id": "d_k3xw7pq2m4tz", "name": "Cellar"},
    "revision": "7b9e9a48d942",
    "modules": [
        {
            "id": "demo",
            "title": "Demo",
            "properties": [
                {"id": "catches", "kind": "number", "name": "Catches"},
                {"id": "catch", "kind": "flag", "class": "motion", "name": "Catch"},
                {"id": "liquid", "kind": "number", "name": "Liquid", "unit": "%", "decimals": 1},
                {"id": "ch0", "kind": "toggle", "class": "outlet", "name": "Table lamp", "named": True, "writable": True},
                {"id": "lamp", "kind": "light", "name": "Lamp", "writable": True},
                {"id": "level", "kind": "number", "name": "Level", "writable": True, "min": 0, "max": 10, "step": 0.5},
                {"id": "mode", "kind": "select", "name": "Mode", "writable": True, "options": [{"id": "a", "name": "Auto"}, {"id": "m", "name": "Manual"}]},
                {"id": "shown", "kind": "select", "name": "Shown", "options": [{"id": "x", "name": "X"}]},
                {"id": "empty", "kind": "select", "name": "No options", "writable": True},
                {"id": "label", "kind": "text", "name": "Label", "writable": True, "max": 24},
                {"id": "rssi", "kind": "number", "name": "Signal", "unit": "dBm", "technical": True},
                {"id": "future", "kind": "hologram", "name": "Not known yet"},
            ],
            "actions": [
                {"id": "measure", "name": "Measure the liquid", "scope": "devices:control", "simple": True, "input": []},
                {"id": "name", "name": "Gives a name", "scope": "devices:advanced", "input": [{"name": "channel", "type": "integer"}]},
                {"id": "wipe", "name": "Wipe", "scope": "devices:control", "simple": True, "confirm": True, "input": []},
                {"id": "pc", "name": "PC on", "scope": "devices:sensitive", "simple": True, "input": []},
                {"id": "beep", "name": "Beep", "scope": "devices:advanced", "input": []},
                {"id": "list", "name": "List", "scope": "devices:read", "readOnly": True, "input": []},
                {"id": "erase", "name": "Erase all", "scope": "devices:sensitive", "sensitive": True, "input": []},
            ],
            "settings": True,
        },
        {
            "id": "traps",
            "title": "Traps",
            "properties": [],
            "actions": [],
            "parts": {
                "properties": [{"id": "caught", "kind": "flag", "class": "problem", "name": "Caught"}, {"id": "battery", "kind": "number", "class": "battery", "unit": "%", "name": "Battery"}],
                "actions": [{"id": "reset", "name": "Reset", "simple": True, "scope": "devices:control", "input": []}],
                "items": [{"id": "t1", "name": "Kitchen"}, {"id": "t2", "name": "Garage"}],
                "next": None,
                # The cloud keeps these parts (from 0.2.0): sums of the period and service visits.
                "stats": True,
                "kinds": [{"id": "catch", "name": "Catture", "summary": True}, {"id": "lost", "name": "Non si sente"},
                          {"id": "service", "name": "Interventi", "summary": True}],
                "services": [{"id": "check", "name": "Controllo"}, {"id": "other", "name": "Altro"}],
            },
        },
    ],
}
ALARMS = [
    {"id": "al_aaaaaaaaaaaa", "module": "demo", "property": "liquid", "name": "Liquido", "unit": "%", "side": "below", "level": 20, "state": "raised"},
    {"id": "al_bbbbbbbbbbbb", "module": "traps", "property": "battery", "part": True, "name": "Batteria", "unit": "%", "side": "below", "level": 15,
     "state": "raised", "parts": [{"part": "t2", "name": "Garage", "state": "raised"}]},
    {"id": "al_cccccccccccc", "module": "demo", "property": "gone", "name": "gone", "side": "above", "level": 1, "state": "unknown"},
]
SILENCES = [{"id": "al_dddddddddddd", "module": "demo", "property": "liquid", "name": "Liquido", "minutes": 360, "state": "ok"}]
SETTINGS = {"demo": [
    {"id": "pulseMs", "type": "integer", "min": 50, "max": 60000, "value": 1500},
    {"id": "buttonToggles", "type": "boolean", "value": True},
    {"id": "label", "type": "string", "min": 0, "max": 32, "value": "Cellar"},
    {"id": "apiKey", "type": "string", "secret": True, "value": None},
    {"id": "blob", "type": "any", "value": None},
]}
STATS = {"traps": {"totals": {"catch": 5, "service": 1}, "parts": [{"id": "t1", "counts": {"catch": 5, "service": 1}}]}}


class PointsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.points, self.parts = model.points(DESCRIPTION)
        self.by = {(p.module, p.part, p.id): p for p in self.points}

    def test_each_kind_goes_to_its_platform(self) -> None:
        expect = {
            ("demo", None, "catches"): "sensor", ("demo", None, "catch"): "binary_sensor", ("demo", None, "liquid"): "sensor",
            ("demo", None, "ch0"): "switch", ("demo", None, "lamp"): "light", ("demo", None, "level"): "number",
            ("demo", None, "mode"): "select", ("demo", None, "shown"): "sensor", ("demo", None, "label"): "text",
            ("demo", None, "rssi"): "sensor", ("demo", None, "measure"): "button",
        }
        for key, platform in expect.items():
            self.assertEqual(self.by[key].platform, platform, key)

    def test_what_is_not_known_or_not_simple_is_left_out(self) -> None:
        for left in ("future", "empty", "name", "wipe", "pc", "beep", "list", "erase"):
            self.assertNotIn(("demo", None, left), self.by, left)

    def test_with_the_advanced_commands_the_commands_of_the_module_with_nothing_to_type(self) -> None:
        points, _ = model.points(DESCRIPTION, advanced=True)
        by = {(p.module, p.part, p.id): p for p in points}
        self.assertEqual(by[("demo", None, "beep")].platform, "button")
        # Never a sensitive one, nor one with input or to confirm, nor one that only reads.
        for left in ("name", "wipe", "pc", "list", "erase"):
            self.assertNotIn(("demo", None, left), by, left)

    def test_details_travel(self) -> None:
        liquid, level, ch0, rssi = self.by[("demo", None, "liquid")], self.by[("demo", None, "level")], self.by[("demo", None, "ch0")], self.by[("demo", None, "rssi")]
        self.assertEqual((liquid.unit, liquid.decimals), ("%", 1))
        self.assertEqual((level.minimum, level.maximum, level.step), (0.0, 10.0, 0.5))
        self.assertEqual(ch0.klass, "outlet")
        self.assertTrue(rssi.technical)
        self.assertEqual(self.by[("demo", None, "mode")].options, (("a", "Auto"), ("m", "Manual")))

    def test_parts_are_sub_devices_with_their_points(self) -> None:
        self.assertEqual([(p.id, p.name) for p in self.parts], [("t1", "Kitchen"), ("t2", "Garage")])
        for part in ("t1", "t2"):
            self.assertEqual(self.by[("traps", part, "caught")].platform, "binary_sensor")
            self.assertEqual(self.by[("traps", part, "battery")].klass, "battery")
            self.assertEqual(self.by[("traps", part, "reset")].platform, "button")

    def test_unique_ids_are_unique_and_stable(self) -> None:
        uids = [p.uid for p in self.points]
        self.assertEqual(len(uids), len(set(uids)))
        self.assertEqual(self.by[("traps", "t1", "caught")].uid, "d_k3xw7pq2m4tz/traps/t1/p:caught")
        self.assertEqual(self.by[("demo", None, "measure")].uid, "d_k3xw7pq2m4tz/demo/-/a:measure")


class ExtrasTest(unittest.TestCase):
    """What the cloud knows about a device besides what it declares (0.2.0): alarms, sums, service visits, settings."""

    def setUp(self) -> None:
        self.points = model.extras(DESCRIPTION, ALARMS, SILENCES, SETTINGS, "it")
        self.by = {(p.extra, p.module, p.part, p.id): p for p in self.points}

    def test_alarms_are_problems_with_their_names(self) -> None:
        liquid = self.by[("alarm", "demo", None, "al_aaaaaaaaaaaa")]
        self.assertEqual((liquid.platform, liquid.klass, liquid.name), ("binary_sensor", "problem", "Liquido sotto 20%"))
        # An alarm on the parts: one for each part.
        self.assertEqual(self.by[("alarm", "traps", "t1", "al_bbbbbbbbbbbb")].name, "Batteria sotto 15%")
        self.assertIn(("alarm", "traps", "t2", "al_bbbbbbbbbbbb"), self.by)
        self.assertEqual(self.by[("alarm", "demo", None, "al_dddddddddddd")].name, "Liquido: nessun dato da più di 6 h")

    def test_the_sums_of_the_summary_and_the_service_visits(self) -> None:
        for part in (None, "t1", "t2"):
            self.assertEqual(self.by[("count", "traps", part, "catch")].name, "Catture nel periodo")
            self.assertIn(("count", "traps", part, "service"), self.by)
            self.assertNotIn(("count", "traps", part, "lost"), self.by, "not of the summary")
            self.assertEqual(self.by[("service", "traps", part, "check")].platform, "button")
            self.assertNotIn(("service", "traps", part, "other"), self.by, "other wants a note: as an action only")
        self.assertEqual(self.by[("service", "traps", None, "check")].name, "Controllo (tutte)")
        self.assertEqual(self.by[("service", "traps", "t1", "check")].name, "Controllo")
        # Who only looks at the device records nothing.
        seen = model.extras(DESCRIPTION, ALARMS, SILENCES, SETTINGS, "it", control=False)
        self.assertEqual([p for p in seen if p.extra == "service"], [])

    def test_settings_are_configuration_without_secrets(self) -> None:
        pulse, toggles, label = (self.by[("setting", "demo", None, k)] for k in ("pulseMs", "buttonToggles", "label"))
        self.assertEqual((pulse.platform, pulse.minimum, pulse.maximum, pulse.step, pulse.name), ("number", 50.0, 60000.0, 1.0, "Pulse ms"))
        self.assertEqual((toggles.platform, toggles.name), ("switch", "Button toggles"))
        self.assertEqual((label.platform, label.maximum), ("text", 32.0))
        self.assertNotIn(("setting", "demo", None, "apiKey"), self.by)
        self.assertNotIn(("setting", "demo", None, "blob"), self.by)

    def test_their_values(self) -> None:
        value = lambda key: model.extra_value(self.by[key], ALARMS, SILENCES, STATS, SETTINGS)  # noqa: E731
        self.assertIs(value(("alarm", "demo", None, "al_aaaaaaaaaaaa")), True)
        self.assertIs(value(("alarm", "traps", "t2", "al_bbbbbbbbbbbb")), True)
        self.assertIs(value(("alarm", "traps", "t1", "al_bbbbbbbbbbbb")), False, "t1 is not among the parts that are not fine")
        self.assertIs(value(("alarm", "demo", None, "al_dddddddddddd")), False)
        self.assertEqual([value(("count", "traps", None, "catch")), value(("count", "traps", "t1", "catch")), value(("count", "traps", "t2", "catch"))], [5, 5, 0])
        self.assertEqual(value(("setting", "demo", None, "pulseMs")), 1500)
        gone = model.extras(DESCRIPTION, ALARMS, [], {}, "en")
        self.assertIsNone(model.extra_value(next(p for p in gone if p.id == "al_cccccccccccc"), ALARMS, [], {}, {}), "an alarm on a number that is no longer there")
        self.assertIsNone(model.extra_value(self.by[("count", "traps", None, "catch")], ALARMS, SILENCES, {}, SETTINGS), "sums not read: nothing, never a false zero")

    def test_unique_ids_with_the_points_of_the_device(self) -> None:
        own, _ = model.points(DESCRIPTION, advanced=True)
        uids = [p.uid for p in own + self.points]
        self.assertEqual(len(uids), len(set(uids)))
        self.assertEqual(self.by[("count", "traps", "t1", "catch")].uid, "d_k3xw7pq2m4tz/traps/t1/count:catch")


class ValuesTest(unittest.TestCase):
    def test_values_of_modules_and_parts_and_the_unknown(self) -> None:
        state = {"online": True, "modules": {"demo": {"properties": {"ch0": {"value": True, "at": "2026-10-12T08:40:55Z"}, "liquid": {"value": None, "at": None}}},
                                              "traps": {"properties": {}, "parts": {"t2": {"caught": {"value": True, "at": None}}}}}}
        points, _ = model.points(DESCRIPTION)
        by = {(p.module, p.part, p.id): p for p in points}
        self.assertIs(model.value_of(state, by[("demo", None, "ch0")]), True)
        self.assertIsNone(model.value_of(state, by[("demo", None, "liquid")]))
        self.assertIs(model.value_of(state, by[("traps", "t2", "caught")]), True)
        self.assertIsNone(model.value_of(state, by[("traps", "t1", "caught")]))
        self.assertIsNone(model.value_of(None, by[("demo", None, "ch0")]))

    def test_a_live_change_is_written_where_it_belongs(self) -> None:
        state: dict = {"online": True, "modules": {}}
        self.assertTrue(model.apply_change(state, {"module": "demo", "property": "liquid", "value": 38.5, "at": "2026-10-13T08:42:07Z"}))
        self.assertTrue(model.apply_change(state, {"module": "traps", "part": "t3", "property": "catches", "value": 4, "at": None}))
        self.assertFalse(model.apply_change(state, {"module": 7, "property": "x"}))
        self.assertEqual(state["modules"]["demo"]["properties"]["liquid"]["value"], 38.5)
        self.assertEqual(state["modules"]["traps"]["parts"]["t3"]["catches"]["value"], 4)


if __name__ == "__main__":
    unittest.main()
