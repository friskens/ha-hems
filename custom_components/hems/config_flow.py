"""UI-only configuration. Creating an entry never sends fabricated measurements."""

import hashlib
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import COMMANDS, DOMAIN
from .protocol import ProtocolError, endpoint


def measurement_schema(defaults):
    schema = {}
    for key in (
        "soc_entity",
        "grid_entity",
        "battery_entity",
        "ev_power_entity",
        "ev_soc_entity",
    ):
        required = key in ("soc_entity", "grid_entity", "battery_entity")
        marker = vol.Required if required else vol.Optional
        field = marker(key, default=defaults[key]) if defaults.get(key) else marker(key)
        schema[field] = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
    schema[vol.Required("solar_entities", default=defaults.get("solar_entities", []))] = (
        selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", multiple=True))
    )
    for key in ("invert_grid_power", "invert_battery_power"):
        schema[vol.Optional(key, default=defaults.get(key, False))] = bool
    return vol.Schema(schema)


def adapter_schema(defaults):
    schema = {}
    for key in ("apply_script", "auto_script"):
        marker = vol.Optional(key, default=defaults[key]) if defaults.get(key) else vol.Optional(key)
        schema[marker] = selector.EntitySelector(selector.EntitySelectorConfig(domain="script"))
    schema[vol.Optional("commands", default=defaults.get("commands", []))] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[v for v in COMMANDS if v != "observe"], multiple=True, translation_key="commands"
        )
    )
    return vol.Schema(schema)


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
        if user_input is not None and user_input.get("solar_entities"):
            return self.async_create_entry(
                title=self.connection["name"], data=self.connection, options=user_input
            )
        return self.async_show_form(
            step_id="measurements",
            data_schema=measurement_schema({}),
            errors={"base": "missing_solar"} if user_input is not None else {},
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
        if user_input is not None and user_input.get("solar_entities"):
            self.pending = user_input
            return await self.async_step_adapter()
        return self.async_show_form(
            step_id="init",
            data_schema=measurement_schema(self.config_entry.options),
            errors={"base": "missing_solar"} if user_input is not None else {},
        )

    async def async_step_adapter(self, user_input=None):
        errors = {}
        if user_input is not None:
            selected = (
                bool(user_input.get("apply_script"))
                or bool(user_input.get("auto_script"))
                or bool(user_input.get("commands"))
            )
            complete = all(user_input.get(k) for k in ("apply_script", "auto_script", "commands"))
            if selected and not complete:
                errors["base"] = "incomplete_adapter"
            else:
                return self.async_create_entry(title="", data={**self.pending, **user_input})
        return self.async_show_form(
            step_id="adapter", data_schema=adapter_schema(self.config_entry.options), errors=errors
        )
