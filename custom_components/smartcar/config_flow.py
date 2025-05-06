# custom_components/smartcar/config_flow.py
# --- Manually append selected scope & mode to authorize URL ---

import logging
from typing import Any, Mapping
import voluptuous as vol
from urllib.parse import urlencode, urlparse, parse_qs

from homeassistant.data_entry_flow import AbortFlow, FlowResult
from homeassistant.helpers import config_entry_oauth2_flow

# Import constants
from .const import DOMAIN, SMARTCAR_MODE, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

# --- Scopes definitions ---
REQUIRED_SCOPES = [
    "read_vehicle_info",
    "read_vin",
]
CONFIGURABLE_SCOPES = [
    "read_odometer",
    "read_location",
    "read_battery",
    "read_charge",
    "read_security",
    "read_engine_oil",
    "read_tires",
    "read_fuel",
    "read_climate",
    "read_alerts",
    "read_charge_events",
    "read_charge_locations",
    "read_charge_records",
    "read_compass",
    "read_diagnostics",
    "read_extended_vehicle_info",
    "read_service_history",
    "read_speedometer",
    "read_thermometer",
    "read_user_profile",
    "control_charge",
    "control_security",
    "control_climate",
    "control_navigation",
    "control_pin",
    "control_trunk",
]
DEFAULT_SCOPES = [
    "read_vehicle_info",
    "read_vin",
    "read_odometer",
    "read_location",
    "read_battery",
    "read_charge",
    "read_security",
    "control_charge",
]
# --- End Scopes Definition ---


class SmartcarOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Config flow to handle Smartcar OAuth2 authentication."""

    DOMAIN = DOMAIN
    VERSION = 1
    _selected_scopes: str | None = None

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        _LOGGER.debug(
            "Handler %s: Starting step_user, proceeding to scopes step", self.flow_id
        )
        return await self.async_step_scopes()

    async def async_step_scopes(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle scope selection and manually construct redirect URL."""
        _LOGGER.debug(
            "Handler %s: Starting step_scopes, input: %s", self.flow_id, user_input
        )
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_scopes_list = [
                scope for scope, selected in user_input.items() if selected
            ]
            if not selected_scopes_list:
                errors["base"] = "no_scopes"
            else:
                self._selected_scopes = " ".join(
                    sorted(set(selected_scopes_list + REQUIRED_SCOPES))
                )
                _LOGGER.info(
                    "Handler %s: User selected scopes: %s",
                    self.flow_id,
                    self._selected_scopes,
                )
                _LOGGER.debug(
                    "Handler %s: Scopes selected, checking implementation/credentials",
                    self.flow_id,
                )
                try:
                    implementations = (
                        await config_entry_oauth2_flow.async_get_implementations(
                            self.hass, self.DOMAIN
                        )
                    )
                    if len(implementations) != 1:
                        return self.async_abort(reason="oauth_impl_error")
                    self.flow_impl = list(implementations.values())[0]
                    _LOGGER.debug(
                        "Handler %s: Found OAuth implementation", self.flow_id
                    )

                    # --- Generate BASE URL ---
                    _LOGGER.debug(
                        "Handler %s: Generating base authorize URL", self.flow_id
                    )
                    base_authorize_url = (
                        await self.flow_impl.async_generate_authorize_url(self.flow_id)
                    )

                    # --- Manually Add Scope and Mode Params ---
                    _LOGGER.debug(
                        "Handler %s: Manually adding scope and mode parameters",
                        self.flow_id,
                    )
                    url_obj = urlparse(base_authorize_url)
                    params = parse_qs(url_obj.query)
                    params["mode"] = SMARTCAR_MODE
                    params["scope"] = self._selected_scopes
                    final_authorize_url = url_obj._replace(
                        query=urlencode(params, doseq=True)
                    ).geturl()
                    # --- End Manual Addition ---

                    _LOGGER.info(
                        "Handler %s: Redirecting user (manual URL)", self.flow_id
                    )
                    return self.async_external_step(
                        step_id="auth", url=final_authorize_url
                    )

                except AbortFlow as err:
                    _LOGGER.debug("Aborting flow: %s", err.reason)
                    return self.async_abort(
                        reason=err.reason,
                        description_placeholders=err.description_placeholders,
                    )
                except Exception as err:
                    _LOGGER.exception(
                        "Unexpected error preparing external step: %s", err
                    )
                    return self.async_abort(reason="unknown")

        # --- Show Form Logic (remains the same) ---
        _LOGGER.debug("Handler %s: Showing scopes form", self.flow_id)
        schema_dict = {}
        for scope in sorted(CONFIGURABLE_SCOPES):
            is_default = scope in DEFAULT_SCOPES
            current_value = (
                user_input.get(scope, is_default) if user_input else is_default
            )
            schema_dict[vol.Optional(scope, default=current_value)] = bool
        return self.async_show_form(
            step_id="scopes",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            last_step=False,
        )
        # --- End Show Form ---

    # Inject selected scopes into stored token data
    async def async_oauth_create_entry(self, data: dict) -> FlowResult:
        _LOGGER.info("OAuth authentication successful, processing token data")
        scopes_requested_in_flow = getattr(self, "_selected_scopes", None)
        if "token" in data and scopes_requested_in_flow:
            if (
                "scope" not in data["token"]
                or data["token"].get("scope") != scopes_requested_in_flow
            ):
                _LOGGER.warning(
                    "Injecting scopes requested in flow: %s", scopes_requested_in_flow
                )
                data["token"]["scope"] = scopes_requested_in_flow
        # ... (error logging as before) ...
        title = DEFAULT_NAME
        _LOGGER.debug("Creating config entry with final data.")
        return self.async_create_entry(title=title, data=data)

    # Reauth step
    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        _LOGGER.info(
            "Starting Smartcar re-authentication flow for %s",
            entry_data.get("title", "entry"),
        )
        self._selected_scopes = entry_data.get("token", {}).get("scope")
        _LOGGER.debug("Re-using stored scopes for re-auth: %s", self._selected_scopes)
        # This still shows scope selection on re-auth - needs refinement if that's undesired
        return await self.async_step_user()
