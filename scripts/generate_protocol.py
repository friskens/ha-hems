"""Generate the human-readable HEMS protocol from the maintained JSON contract.

The generator intentionally uses only the Python standard library so the same
command can run locally and in GitHub Actions without another runtime package.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "contract" / "hems-contract.json"
DEFAULT_PROTOCOL = ROOT / "docs" / "PROTOCOL.md"


class ContractError(ValueError):
    """Raised when the contract cannot be used as protocol source data."""


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{name} must be an object")
    return value


def _require_string(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{name} must be a non-empty string")


def validate_contract(contract: Any) -> dict[str, Any]:
    """Perform dependency-free structural validation before documentation is made."""
    root = _require_mapping(contract, "contract")
    for key in ("contract", "describes"):
        _require_string(root.get(key), key)

    version = root.get("contract_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ContractError("contract_version must be a positive integer")

    exchange = _require_mapping(root.get("exchange"), "exchange")
    for key in ("method", "path", "auth_header", "owner"):
        _require_string(exchange.get(key), f"exchange.{key}")
    cadence = _require_mapping(exchange.get("cadence"), "exchange.cadence")
    for key in ("every_s", "min_spacing_s", "backoff_after_failure_s"):
        value = cadence.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ContractError(f"exchange.cadence.{key} must be a positive integer")

    for section in ("inputs", "rules", "outputs"):
        _require_mapping(root.get(section), section)

    for name, definition in root["inputs"].items():
        _require_mapping(definition, f"inputs.{name}")
        _require_string(definition.get("field"), f"inputs.{name}.field")
        if not isinstance(definition.get("required"), bool):
            raise ContractError(f"inputs.{name}.required must be a boolean")

    decision = _require_mapping(root["outputs"].get("decision"), "outputs.decision")
    _require_string(decision.get("entity"), "outputs.decision.entity")
    if not isinstance(decision.get("values"), list) or not all(
        isinstance(value, str) and value for value in decision["values"]
    ):
        raise ContractError("outputs.decision.values must be a list of non-empty strings")

    _validate_json_values(root, "contract")
    return root


def _validate_json_values(value: Any, location: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError(f"{location} contains a non-finite number")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ContractError(f"{location} has a non-string key")
            _validate_json_values(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_json_values(child, f"{location}[{index}]")


def load_contract(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read {path}: {error}") from error
    return validate_contract(raw)


def _title(key: str) -> str:
    return key.replace("_", " ").replace("[]", " entries").capitalize()


def _inline(value: Any) -> str:
    if value is None:
        return "`null`"
    if value is True:
        return "`true`"
    if value is False:
        return "`false`"
    if isinstance(value, str):
        return f"`{value}`"
    return f"`{json.dumps(value, ensure_ascii=False, separators=(',', ': '))}`"


def _render_value(value: Any, level: int) -> list[str]:
    if not isinstance(value, (dict, list)):
        return [_inline(value)]
    if isinstance(value, list):
        if not value:
            return ["`[]`"]
        if all(not isinstance(item, (dict, list)) for item in value):
            return [", ".join(_inline(item) for item in value)]
        lines: list[str] = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append("-")
                lines.extend(f"  {line}" for line in _render_value(item, level + 1))
            else:
                lines.append(f"- {_inline(item)}")
        return lines
    lines = []
    for key, child in value.items():
        if isinstance(child, (dict, list)):
            lines.append(f"{'#' * min(level + 1, 6)} {_title(key)}")
            lines.append("")
            lines.extend(_render_value(child, level + 1))
        else:
            lines.append(f"- **{_title(key)}:** {_inline(child)}")
    return lines


def render_protocol(contract: dict[str, Any]) -> str:
    """Render a stable Markdown view of every field in the contract."""
    exchange = contract["exchange"]
    lines = [
        "<!-- GENERATED FILE — do not edit directly. Source: contract/hems-contract.json; run python scripts/generate_protocol.py -->",
        "",
        "# HEMS protocol",
        "",
        f"**Contract:** `{contract['contract']}`",
        f"**Contract version:** `{contract['contract_version']}`",
        "",
        contract["describes"],
        "",
        "## Source of truth",
        "",
        "This document is generated from `contract/hems-contract.json`. Change the JSON contract, run the generator, and commit both files. CI rejects a stale generated document.",
        "",
        "## Exchange",
        "",
        "| Property | Value |",
        "| --- | --- |",
    ]
    for key in ("method", "path", "auth_header", "owner", "unknown_response_fields", "max_response_bytes"):
        if key in exchange:
            lines.append(f"| {_title(key)} | {_inline(exchange[key])} |")
    lines.extend(["", "### Cadence", ""])
    lines.extend(_render_value(exchange["cadence"], 3))

    lines.extend(["", "## Request inputs", ""])
    for name, definition in contract["inputs"].items():
        lines.extend([f"### `{name}`", ""])
        lines.extend(_render_value(definition, 3))
        lines.append("")

    lines.extend(["## Local transformation rules", ""])
    for name, definition in contract["rules"].items():
        lines.extend([f"### `{name}`", ""])
        lines.extend(_render_value(definition, 3))
        lines.append("")

    lines.extend(["## Response outputs", ""])
    for name, definition in contract["outputs"].items():
        lines.extend([f"### `{name}`", ""])
        lines.extend(_render_value(definition, 3))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--check", action="store_true", help="fail if the committed document is stale")
    args = parser.parse_args()

    try:
        generated = render_protocol(load_contract(args.contract))
    except ContractError as error:
        parser.error(str(error))

    existing = args.output.read_text(encoding="utf-8") if args.output.exists() else None
    if args.check:
        if existing != generated:
            print(f"{args.output} is not generated from {args.contract}; run python scripts/generate_protocol.py")
            return 1
        print(f"{args.output} matches {args.contract}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(generated, encoding="utf-8", newline="\n")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
