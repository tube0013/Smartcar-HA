# custom_components/smartcar/config_flow.py
# --- Should correctly handle scope selection and URL generation ---

import logging
from typing import Any, Mapping
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import AbortFlow, FlowResult
from homeassistant.helpers import config_entry_oauth2_flow
# Import the correct AbortFlow location
# Removed OAuth2AuthorizeError import

from .const import DOMAIN, SMARTCAR_MODE, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

# --- ALL_SCOPES and DEFAULT_SCOPES definitions remain the same ---
ALL_SCOPES = {
    "read_vehicle_info": "Know make, model, and year (Recommended)", "read_vin": "Read VIN (Recommended)",
    "read_odometer": "Retrieve total distance traveled", "read_location": "Access the vehicle's location",
    "read_battery": "Read EV battery data", "read_charge": "Read charging data",
    "read_security": "Read lock status", "read_engine_oil": "Read engine oil health",
    "read_tires": "Read tire status", "read_fuel": "Read fuel tank level",
    "read_climate": "Read climate settings", "read_alerts": "Read vehicle alerts",
    "read_charge_events": "Receive charging event notifications", "read_charge_locations": "Access previous charging locations",
    "read_charge_records": "Read charge records", "read_compass": "Read compass direction",
    "read_diagnostics": "Read vehicle diagnostics", "read_extended_vehicle_info": "Read vehicle configuration",
    "read_service_history": "Read service records", "read_speedometer": "Read vehicle speed",
    "read_thermometer": "Read temperatures", "read_user_profile": "Read user profile",
    "control_charge": "Control charging (Start/Stop, Set Limit)", "control_security": "Lock or unlock vehicle",
    "control_climate": "Control climate system", "control_navigation": "Send navigation destinations",
    "control_pin": "Modify PIN / PIN to Drive", "control_trunk": "Control trunk/frunk",
}
DEFAULT_SCOPES = [
    "read_vehicle_info", "read_vin", "read_odometer", "read_location",
    "read_battery", "read_charge", "read_security",
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
        _LOGGER.debug("Handler %s: Starting step_user, proceeding to scopes step", self.flow_id)
        return await self.async_step_scopes()

    async def async_step_scopes(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle scope selection from the user."""
        _LOGGER.debug("Handler %s: Starting step_scopes, input: %s", self.flow_id, user_input)
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_scopes_list = [scope for scope, selected in user_input.items() if selected]
            if not selected_scopes_list:
                errors["base"] = "no_scopes"
            else:
                self._selected_scopes = " ".join(sorted(selected_scopes_list))
                _LOGGER.info("Handler %s: User selected scopes: %s", self.flow_id, self._selected_scopes)
                _LOGGER.debug("Handler %s: Scopes selected, checking implementation/credentials", self.flow_id)
                try:
                    implementations = await config_entry_oauth2_flow.async_get_implementations(self.hass, self.DOMAIN)
                    if len(implementations) != 1: return self.async_abort(reason="oauth_impl_error")
                    self.flow_impl = list(implementations.values())[0]
                    _LOGGER.debug("Handler %s: Found OAuth implementation", self.flow_id)

                    # --- Generate URL and return external step (Corrected call) ---
                    _LOGGER.debug("Handler %s: Generating authorize URL", self.flow_id)
                    # Pass flow_id, NO self argument
                    authorize_url = await self.flow_impl.async_generate_authorize_url(self.flow_id)
                    _LOGGER.info("Handler %s: Redirecting user", self.flow_id)
                    return self.async_external_step(step_id="auth", url=authorize_url)
                    # --- End Correction ---

                except AbortFlow as err:
                    _LOGGER.debug("Aborting flow: %s", err.reason)
                    return self.async_abort(reason=err.reason, description_placeholders=err.description_placeholders)
                except Exception as err:
                    _LOGGER.exception("Unexpected error preparing external step: %s", err)
                    return self.async_abort(reason="unknown")

        # Show Form Logic
        _LOGGER.debug("Handler %s: Showing scopes form", self.flow_id)
        sorted_scopes = dict(sorted(ALL_SCOPES.items()))
        schema_dict = {}
        for scope, description in sorted_scopes.items():
            is_default = scope in DEFAULT_SCOPES
            current_value = user_input.get(scope, is_default) if user_input else is_default
            schema_dict[vol.Optional(scope, default=current_value)] = bool
        return self.async_show_form(
            step_id="scopes", data_schema=vol.Schema(schema_dict),
            description_placeholders={"app_name": "Smartcar", "scope_info": "..."},
            errors=errors, last_step=False
        )

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra parameters for authorize url."""
        _LOGGER.debug("Generating extra authorize data...")
        # Read selected scopes stored by async_step_scopes
        scopes_to_request = getattr(self, "_selected_scopes", None)
        if not scopes_to_request:
            _LOGGER.error("extra_authorize_data called but _selected_scopes is not set!")
            scopes_to_request = "" # Should not happen in correct flow
        _LOGGER.debug("Generating extra authorize data with selected scopes: %s", scopes_to_request)
        return { "scope": scopes_to_request, "response_type": "code", "mode": SMARTCAR_MODE }

    async def async_oauth_create_entry(self, data: dict) -> FlowResult:
        # Inject selected scopes into stored token data
        _LOGGER.info("OAuth authentication successful, processing token data")
        scopes_requested_in_flow = getattr(self, "_selected_scopes", None)
        if "token" in data:
            if "scope" not in data["token"] or data["token"].get("scope") != scopes_requested_in_flow:
                _LOGGER.warning("Injecting scopes requested in flow: %s", scopes_requested_in_flow)
                data["token"]["scope"] = scopes_requested_in_flow
        # ... (error logging as before) ...
        title = DEFAULT_NAME
        _LOGGER.debug("Creating config entry with final data.")
        return self.async_create_entry(title=title, data=data)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        # ... (remains the same) ...
        _LOGGER.info("Starting Smartcar re-authentication flow for %s", entry_data.get("title", "entry"))
        self._selected_scopes = entry_data.get("token", {}).get("scope")
        _LOGGER.debug("Re-using stored scopes for re-auth: %s", self._selected_scopes)
        return await self.async_step_user() # Still shows scope selection on reauth