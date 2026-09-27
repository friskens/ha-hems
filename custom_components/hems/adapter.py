"""Public HA script contract; no imports from other custom integrations."""

import asyncio
import math
import time

from .const import WRITE_TIMEOUT


class VerificationError(Exception):
    """Actuator could not independently confirm the requested configuration."""


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
        raise VerificationError("readback_mismatch")


class ScriptAdapter:
    def __init__(self, hass, apply_script, auto_script, commands):
        self.hass, self.apply_script, self.auto_script = hass, apply_script, auto_script
        self.commands = set(commands)

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
        if command != "auto" and command not in self.commands:
            raise VerificationError("unsupported_adapter_command")
        entity = self.auto_script if command == "auto" else self.apply_script
        if not entity or not entity.startswith("script."):
            raise VerificationError("missing_adapter_script")
        started = time.time()
        try:
            async with asyncio.timeout(WRITE_TIMEOUT):
                # Call the script service directly so failures and return data propagate.
                result = await self.hass.services.async_call(
                    "script",
                    entity.split(".", 1)[1],
                    {"command": command, "power_w": power_w, "token": token},
                    blocking=True,
                    return_response=True,
                )
        except asyncio.CancelledError:
            # Stop the independent HA script before a recovery Auto can run.
            await asyncio.shield(self.stop_script(entity))
            raise
        except Exception as err:
            # Script exceptions may include credentials; only a stable code escapes.
            await self.stop_script(entity)
            raise VerificationError("adapter_failed") from err
        validate_receipt(result, command, power_w, token, started, time.time())
