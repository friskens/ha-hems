"""Tests for the generated protocol document guard."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_protocol import ContractError, load_contract, render_protocol, validate_contract  # noqa: E402


def test_repository_contract_generates_markdown() -> None:
    rendered = render_protocol(load_contract(ROOT / "contract" / "hems-contract.json"))

    assert rendered.startswith("<!-- GENERATED FILE")
    assert "# HEMS protocol" in rendered
    assert "### `battery_soc`" in rendered
    assert "### `decision`" in rendered


def test_committed_protocol_matches_contract() -> None:
    rendered = render_protocol(load_contract(ROOT / "contract" / "hems-contract.json"))

    assert (ROOT / "docs" / "PROTOCOL.md").read_text(encoding="utf-8") == rendered


def test_contract_requires_decision_values() -> None:
    with pytest.raises(ContractError, match="outputs.decision.values"):
        validate_contract(
            {
                "contract": "test",
                "contract_version": 1,
                "describes": "test",
                "exchange": {
                    "method": "POST",
                    "path": "/battery",
                    "auth_header": "X-Api-Key",
                    "owner": "engine",
                    "cadence": {"every_s": 20, "min_spacing_s": 20, "backoff_after_failure_s": 60},
                },
                "inputs": {},
                "rules": {},
                "outputs": {"decision": {"entity": "sensor", "values": "charge"}},
            }
        )
