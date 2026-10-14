"""UI-only configuration. Creating an entry never sends fabricated measurements."""

import hashlib
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DOMAIN
from .contract import load_bundled_contract
from .protocol import ProtocolError, endpoint
from .telemetry_config import (
    defaults_for_contract,
    is_selectable,
    option_flag_key,
    option_key,
    selection_errors,
)


def measurement_schema(contract, defaults):
    """Build selectors from validated contract inputs, never rule expressions.

    Home Assistant's entity selector supports domain and device class filters.
    Units remain a runtime/configuration validation because the selector API has
    no unit filter; a wrong saved source produces a Repair, not a stale-data
    warning.
    """
    schema = {}
    for input_spec in contract.inputs.values():
        if not is_selectable(input_spec):
            continue
        key = option_key(input_spec.key)
        marker = vol.Required if input_spec.required else vol.Optional
        default = defaults.get(key, [] if input_spec.multiple else None)
        field = marker(key, default=default) if default is not None else marker(key)
        selector_config = {"domain": input_spec.domain, "multiple": input_spec.multiple}
        if input_spec.device_class:
            selector_config["device_class"] = input_spec.device_class
        schema[field] = selector.EntitySelector(selector.EntitySelectorConfig(**selector_config))
        for option in input_spec.options:
            flag = option_flag_key(input_spec.key, option)
            schema[vol.Optional(flag, default=defaults.get(flag, False))] = bool
    return vol.Schema(schema)


def measurement_errors(contract, data):
    """Return one translated form error for a malformed selection shape."""
    return {"base": "invalid_measurements"} if selection_errors(contract, data) else {}



class HemsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                user_input["endpoint"] = endpoint(user_input["endpoint"])
                if not user_input["api_key"].strip():
                    raise ProtocolError("invalid_key")
            except ProtocolError as err:
                errors["base"] = str(err)
            else:
                # One controller per endpoint. Avoid two writers using different keys.
                await self.async_set_unique_id(hashlib.sha256(user_input["endpoint"].encode()).hexdigest())
                self._abort_if_unique_id_configured()
                self.connection = user_input
                return await self.async_step_measurements()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default="HEMS"): str,
                    vol.Required("endpoint"): str,
                    vol.Required("api_key"): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_measurements(self, user_input=None):
        contract = load_bundled_contract()
        if user_input is not None and not measurement_errors(contract, user_input):
            return self.async_create_entry(
                title=self.connection["name"], data=self.connection, options=user_input
            )
        return self.async_show_form(
            step_id="measurements",
            data_schema=measurement_schema(contract, defaults_for_contract(contract, {})),
            errors=measurement_errors(contract, user_input) if user_input is not None else {},
        )
    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        if user_input and user_input.get("api_key", "").strip():
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data_updates=user_input)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("api_key"): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
        )
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HemsOptionsFlow()


class HemsOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        contract = load_bundled_contract()
        if user_input is not None and not measurement_errors(contract, user_input):
            # Saving migrates legacy a9 names to contract-derived keys.  The
            # client only reads selected sources and publishes HEMS decisions.
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=measurement_schema(contract, defaults_for_contract(contract, self.config_entry.options)),
            errors=measurement_errors(contract, user_input) if user_input is not None else {},
        )

    # This flow deliberately has no adapter/options step: local automations
    # consume the exposed decision and are solely responsible for execution.
