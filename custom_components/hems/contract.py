"""Safe, read-only consumption of the HEMS machine-readable contract.

The contract is data owned by HEMS.  This module deliberately does not
evaluate its ``expression`` strings (or any other value from the contract).
It only validates the small structural surface that the client needs before
using a contract to build local UI and entities.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from threading import RLock
from types import MappingProxyType
from typing import Any, Mapping


class ContractError(ValueError):
    """The supplied contract cannot safely be used by this client."""


def _readonly(value: Any) -> Any:
    """Recursively freeze JSON-shaped data without interpreting it."""
    if isinstance(value, dict):
        return MappingProxyType({str(key): _readonly(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_readonly(item) for item in value)
    return value


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"invalid_{name}")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"invalid_{name}")
    return value


def _positive_int(value: Any, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ContractError(f"invalid_{name}")
    return value


@dataclass(frozen=True)
class ContractInput:
    """A declarative Home Assistant telemetry input from a valid contract."""

    key: str
    field: str
    required: bool
    domain: str
    device_class: str | None
    units: tuple[str, ...]
    stale_after_s: int | None
    definition: Mapping[str, Any]


@dataclass(frozen=True)
class HemsContract:
    """Validated contract metadata and read-only descriptions.

    ``raw`` is available for diagnostics and future declarative consumers.
    It is recursively immutable and never an instruction to execute code.
    """

    name: str
    version: int
    exchange: Mapping[str, Any]
    inputs: Mapping[str, ContractInput]
    outputs: Mapping[str, Mapping[str, Any]]
    raw: Mapping[str, Any]

    def input(self, key: str) -> ContractInput | None:
        """Return a known input description without raising for future fields."""
        return self.inputs.get(key)

    def output(self, key: str) -> Mapping[str, Any] | None:
        """Return a read-only output description, if the contract defines it."""
        return self.outputs.get(key)


def _validate_input(key: str, definition: Any) -> ContractInput:
    item = _mapping(definition, f"input_{key}")
    field = _text(item.get("field"), f"input_{key}_field")
    required = item.get("required")
    if type(required) is not bool:
        raise ContractError(f"invalid_input_{key}_required")
    domain = _text(item.get("domain"), f"input_{key}_domain")
    device_class = item.get("device_class")
    if device_class is not None and not isinstance(device_class, str):
        raise ContractError(f"invalid_input_{key}_device_class")
    raw_units = item.get("units", [item["unit"]] if "unit" in item else [])
    if not isinstance(raw_units, list) or not raw_units or not all(isinstance(unit, str) and unit for unit in raw_units):
        raise ContractError(f"invalid_input_{key}_units")
    stale_after_s = item.get("stale_after_s")
    if stale_after_s is not None:
        _positive_int(stale_after_s, f"input_{key}_stale_after_s")
    return ContractInput(
        key=key,
        field=field,
        required=required,
        domain=domain,
        device_class=device_class,
        units=tuple(raw_units),
        stale_after_s=stale_after_s,
        definition=_readonly(item),
    )


def parse_contract(data: Any) -> HemsContract:
    """Validate and freeze contract data without applying its rules.

    Unknown additive input/output fields are preserved.  The mandatory decision
    surface is deliberately strict, because an invalid dynamic contract must
    never replace the last one that the client knows is safe.
    """
    root = _mapping(data, "contract")
    name = _text(root.get("contract"), "contract_name")
    version = _positive_int(root.get("contract_version"), "contract_version")

    exchange = _mapping(root.get("exchange"), "exchange")
    if exchange.get("method") != "POST":
        raise ContractError("invalid_exchange_method")
    path = _text(exchange.get("path"), "exchange_path")
    if not path.startswith("/"):
        raise ContractError("invalid_exchange_path")
    _text(exchange.get("auth_header"), "exchange_auth_header")

    raw_inputs = _mapping(root.get("inputs"), "inputs")
    inputs: dict[str, ContractInput] = {}
    for key, definition in raw_inputs.items():
        if not isinstance(key, str) or not key:
            raise ContractError("invalid_input_key")
        inputs[key] = _validate_input(key, definition)

    raw_outputs = _mapping(root.get("outputs"), "outputs")
    decision = _mapping(raw_outputs.get("decision"), "decision")
    if decision.get("entity") != "sensor" or decision.get("state_from") != "action":
        raise ContractError("invalid_decision")
    values = decision.get("values")
    if not isinstance(values, list) or not values or not all(isinstance(value, str) and value for value in values):
        raise ContractError("invalid_decision_values")
    attributes = _mapping(decision.get("attributes"), "decision_attributes")
    for core in ("power_kw", "command_interval_seconds"):
        if core not in attributes or not isinstance(attributes[core], dict):
            raise ContractError(f"missing_decision_{core}")

    outputs: dict[str, Mapping[str, Any]] = {}
    for key, definition in raw_outputs.items():
        if not isinstance(key, str) or not key or not isinstance(definition, dict):
            raise ContractError("invalid_output")
        outputs[key] = _readonly(definition)
    return HemsContract(
        name=name,
        version=version,
        exchange=_readonly(exchange),
        inputs=MappingProxyType(inputs),
        outputs=MappingProxyType(outputs),
        raw=_readonly(root),
    )


def parse_contract_json(content: str | bytes) -> HemsContract:
    """Parse JSON text only; it is never evaluated as Python or a template."""
    try:
        return parse_contract(json.loads(content))
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ContractError("invalid_contract_json") from err


def bundled_contract_path() -> Path:
    """Locate the contract packaged with the installed integration.

    The authoritative source is maintained at repository root in
    ``contract/hems-contract.json``. CI verifies the packaged copy is byte for
    byte identical before release. Keeping the runtime lookup inside the
    integration prevents HACS installations from depending on repository-only
    files.
    """
    return Path(__file__).resolve().parent / "hems-contract.json"


def load_bundled_contract(path: Path | None = None) -> HemsContract:
    """Load the authoritative bundled contract from disk."""
    try:
        return parse_contract_json((path or bundled_contract_path()).read_text(encoding="utf-8"))
    except OSError as err:
        raise ContractError("bundled_contract_unavailable") from err


class ContractStore:
    """Keep the last structurally valid contract during future refreshes."""

    def __init__(self, contract: HemsContract | None = None) -> None:
        self._lock = RLock()
        self._current = contract
        self._last_error: str | None = None

    @property
    def current(self) -> HemsContract | None:
        with self._lock:
            return self._current

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def replace(self, candidate: Any) -> bool:
        """Accept a valid candidate; retain the last valid one on failure."""
        try:
            parsed = parse_contract(candidate)
        except ContractError as err:
            with self._lock:
                self._last_error = str(err)
            return False
        with self._lock:
            self._current = parsed
            self._last_error = None
        return True

    def replace_json(self, candidate: str | bytes) -> bool:
        """Accept downloaded JSON while retaining the current contract on failure."""
        try:
            parsed = parse_contract_json(candidate)
        except ContractError as err:
            with self._lock:
                self._last_error = str(err)
            return False
        with self._lock:
            self._current = parsed
            self._last_error = None
        return True
