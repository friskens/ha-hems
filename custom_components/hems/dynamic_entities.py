"""Informational entities whose identity is assigned by HEMS.

The service owns the identifiers in a decision response.  This module never
interprets a load action as an instruction to operate Home Assistant equipment.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.components.sensor import SensorEntity

from .entity import HemsEntity


def stable_hems_id(entry: dict[str, Any]) -> str:
    """Return the contract-defined durable identity for one output entry."""
    uid = entry.get("uid")
    if entry.get("kind") == "ev" and isinstance(uid, str) and uid.strip():
        return uid
    output_id = entry.get("id")
    if not isinstance(output_id, str) or not output_id.strip():
        raise ValueError("output entry is missing a stable HEMS id")
    return output_id


class OutputTracker:
    """Keep discovered outputs registered without treating an omission as deletion.

    The current contract has no tombstone or authoritative complete-inventory
    marker.  Consequently this tracker deliberately has no removal operation.
    """

    def __init__(self) -> None:
        self._known: dict[str, dict[str, Any]] = {}
        self._current: set[str] = set()

    def update(self, entries: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Record a response and return entries first seen in this response."""
        current: set[str] = set()
        created: list[dict[str, Any]] = []
        for entry in entries or ():
            output_id = stable_hems_id(entry)
            current.add(output_id)
            if output_id not in self._known:
                created.append(entry)
            # A display name is mutable metadata, never identity.  Preserve
            # omitted optional metadata from the last observation rather than
            # replacing a useful short name with a generated fallback.
            self._known[output_id] = {**self._known.get(output_id, {}), **entry}
        self._current = current
        return created

    def entry(self, output_id: str) -> dict[str, Any] | None:
        """Return the latest entry only while it appears in the current response."""
        if output_id not in self._current:
            return None
        return self._known.get(output_id)

    def known_ids(self) -> set[str]:
        """Return all entities ever observed for tests and diagnostics."""
        return set(self._known)


class HemsOutputSensor(HemsEntity, SensorEntity):
    """One HEMS-owned, informational sensor for a load or charger output."""

    _attr_translation_key = "output"

    def __init__(self, runtime, tracker: OutputTracker, entry: dict[str, Any]):
        self._tracker = tracker
        self._output_id = stable_hems_id(entry)
        super().__init__(runtime, f"load_{self._output_id}")
        self._attr_translation_placeholders = {"id": self._output_id}

    @property
    def available(self) -> bool:
        return self._tracker.entry(self._output_id) is not None

    @property
    def native_value(self):
        entry = self._tracker.entry(self._output_id)
        # Keep unknown future action strings visible.  This sensor intentionally
        # is not an enum entity with a closed options list.
        return entry.get("action") if entry else None

    @property
    def name(self):
        entry = self._tracker.entry(self._output_id)
        if entry and isinstance(entry.get("name"), str) and entry["name"].strip():
            return entry["name"]
        return super().name

    @property
    def extra_state_attributes(self):
        entry = self._tracker.entry(self._output_id)
        if entry is None:
            return {"hems_id": self._output_id, "present": False}
        return {
            "hems_id": self._output_id,
            "present": True,
            **{
                key: entry[key]
                for key in (
                    "id",
                    "uid",
                    "kind",
                    "power_w",
                    "power_kw",
                    "current_a",
                    "target_pct",
                    "reason",
                    "enabled",
                    "reports_power",
                )
                if key in entry
            },
        }
