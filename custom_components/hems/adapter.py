"""Public HA script contract; no imports from other custom integrations."""

import asyncio
import math
import time

from .const import WRITE_TIMEOUT


class VerificationError(Exception):
    """Actuator could not independently confirm the requested configuration."""

    def __init__(self, code, receipt=None):
        super().__init__(code)
        self.receipt = receipt


def validate_receipt(receipt, command, power_w, token, started, now):
    """A script acknowledgement or optimistic entity state is not a readback."""
    if not isinstance(receipt, dict):
        raise VerificationError("missing_receipt")
    stamp = receipt.get("readback_at")
    valid_stamp = type(stamp) in (int, float) and math.isfinite(stamp) and started <= stamp <= now
    if (
        receipt.get("verified") is not True
        or receipt.get("token") != token
        or receipt.get("command") != command
        or receipt.get("power_w") != power_w
        or type(receipt.get("power_w")) not in (int, float)
        or not valid_stamp
        or not isinstance(receipt.get("readback"), dict)
        or not receipt["readback"]
    ):
        raise VerificationError("verification_failed", receipt if isinstance(receipt, dict) else None)


class ScriptAdapter:
    def __init__(self, hass, apply_script, commands):
        self.hass, self.apply_script = hass, apply_script
        self.commands = set(commands)

    def service_name(self, entity):
        """Resolve a selected script entity to its callable script service."""
        # A user can customize an entity ID in the entity registry. For YAML
        # scripts, the registry's immutable unique_id remains the script key
        # used by the direct service, which is required for a response.
        try:
            from homeassistant.helpers import entity_registry as er
        except ImportError:  # Unit tests run without Home Assistant installed.
            return entity.split(".", 1)[1]

        entry = er.async_get(self.hass).async_get(entity)
        if entry and isinstance(entry.unique_id, str) and entry.unique_id:
            service = entry.unique_id.removeprefix("script.")
            if self.hass.services.has_service("script", service):
                return service
        return entity.split(".", 1)[1]

    async def stop_script(self, entity):
        try:
            async with asyncio.timeout(15):
                await self.hass.services.async_call(
                    "script",
                    "turn_off",
                    {"entity_id": entity},
                    blocking=True,
                )
        except Exception:
            # Do not expose an integration's raw exception (possibly credentials).
            return False
        return True

    async def execute(self, command, power_w, token):
        if command not in self.commands:
            raise VerificationError("unsupported_adapter_command")
        entity = self.apply_script
        if not entity or not entity.startswith("script."):
            raise VerificationError("missing_adapter_script")
        service = self.service_name(entity)
        started = time.time()
        try:
            async with asyncio.timeout(WRITE_TIMEOUT):
                # Call the script service directly so failures and return data propagate.
                result = await self.hass.services.async_call(
                    "script",
                    service,
                    {"command": command, "power_w": power_w, "token": token},
                    blocking=True,
                    return_response=True,
                )
        except asyncio.CancelledError:
            # Stop the in-flight adapter script; never issue a hardware fallback.
            await asyncio.shield(self.stop_script(entity))
            raise
        except Exception as err:
            # Script exceptions may include credentials; only a stable code escapes.
            await self.stop_script(entity)
            raise VerificationError("adapter_failed") from err
        validate_receipt(result, command, power_w, token, started, time.time())
        return result
