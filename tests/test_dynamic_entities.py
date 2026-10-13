import importlib
import sys
import types

import pytest


@pytest.fixture
def dynamic_entities(monkeypatch):
    for name in (
        "homeassistant",
        "homeassistant.components",
        "homeassistant.components.sensor",
        "homeassistant.helpers",
        "homeassistant.helpers.entity",
    ):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    sys.modules["homeassistant.components.sensor"].SensorEntity = type("SensorEntity", (), {})
    entity_module = sys.modules["homeassistant.helpers.entity"]
    entity_module.DeviceInfo = lambda **kwargs: kwargs
    entity_module.Entity = type("Entity", (), {})
    sys.modules.pop("custom_components.hems.entity", None)
    sys.modules.pop("custom_components.hems.dynamic_entities", None)
    return importlib.import_module("custom_components.hems.dynamic_entities")


def test_charger_uid_is_stable_identity_and_name_is_not(dynamic_entities):
    stable_hems_id = dynamic_entities.stable_hems_id
    first = {"kind": "ev", "id": "charger-at-home", "uid": "uid-42", "name": "Driveway"}
    renamed = {**first, "name": "Garage"}
    assert stable_hems_id(first) == "uid-42"
    assert stable_hems_id(renamed) == "uid-42"


def test_load_id_is_stable_identity_when_there_is_no_charger_uid(dynamic_entities):
    assert dynamic_entities.stable_hems_id({"kind": "deferrable", "id": "water-heater"}) == "water-heater"


def test_tracker_never_auto_deletes_an_absent_output(dynamic_entities):
    tracker = dynamic_entities.OutputTracker()
    entry = {"kind": "ev", "id": "charger-a", "uid": "uid-a", "action": "charge"}
    assert tracker.update([entry]) == [entry]
    assert tracker.entry("uid-a") == entry

    # An empty or omitted list is not an authoritative deletion signal.
    assert tracker.update([]) == []
    assert tracker.entry("uid-a") is None
    assert tracker.known_ids() == {"uid-a"}
    assert tracker.update(None) == []
    assert tracker.known_ids() == {"uid-a"}


def test_new_unknown_action_is_data_not_a_new_entity(dynamic_entities):
    tracker = dynamic_entities.OutputTracker()
    entry = {"kind": "deferrable", "id": "heater", "action": "future_action"}
    assert tracker.update([entry]) == [entry]
    assert tracker.entry("heater")["action"] == "future_action"
    assert tracker.update([{**entry, "action": "another_action"}]) == []
    assert tracker.known_ids() == {"heater"}


def test_omitted_display_name_does_not_change_the_stable_entity(dynamic_entities):
    tracker = dynamic_entities.OutputTracker()
    tracker.update([{"kind": "ev", "id": "charger-a", "uid": "uid-a", "name": "Driveway", "action": "charge"}])
    tracker.update([{"kind": "ev", "id": "charger-a", "uid": "uid-a", "action": "stop"}])
    assert tracker.entry("uid-a")["name"] == "Driveway"


def test_missing_stable_id_is_rejected(dynamic_entities):
    with pytest.raises(ValueError, match="stable HEMS id"):
        dynamic_entities.stable_hems_id({"kind": "ev", "name": "No identifier"})
