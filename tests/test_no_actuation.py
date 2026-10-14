"""Guard the integration boundary: HEMS Client must not control equipment."""

from pathlib import Path


RUNTIME = Path(__file__).parents[1] / "custom_components" / "hems" / "runtime.py"


def test_runtime_has_no_adapter_or_service_invocation():
    source = RUNTIME.read_text(encoding="utf-8")
    for forbidden in (
        "ScriptAdapter",
        "VerificationError",
        "async_call(",
        ".services.",
        "async_create_task(self.apply",
    ):
        assert forbidden not in source


def test_legacy_control_state_is_migrated_only_to_telemetry():
    source = RUNTIME.read_text(encoding="utf-8")
    assert 'stored.get("telemetry_enabled", stored.get("requested", True))' in source
    assert "self.telemetry_enabled = enabled" in source
