# custom_components/smartcar/config_flow.py

import logging
from typing import Any, Mapping

from homeassistant import config_entries
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, SMARTCAR_MODE, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

# Define SCOPES (Ensure this is accurate for your needs)
SCOPES_CONTROL = [
    "control_climate", "control_charge", "control_navigation",
    "control_pin", "control_security", "control_trunk",
]
SCOPES_READ = [
    "read_alerts", "read_battery", "read_charge", "read_charge_locations",
    "read_climate", "read_compass", "read_diagnostics", "read_engine_oil",
    "read_extended_vehicle_info", "read_fuel", "read_location", "read_odometer",
    "read_security", "read_service_history", "read_speedometer",
    "read_thermometer", "read_tires", "read_user_profile", "read_vehicle_info",
    "read_vin",
]
SCOPES = " ".join(SCOPES_CONTROL + SCOPES_READ)

class SmartcarOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Config flow to handle Smartcar OAuth2 authentication."""
    DOMAIN = DOMAIN
    VERSION = 1

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra parameters for authorize url."""
        # _LOGGER.debug("Generating extra authorize data...") # Removed debug log
        return { "scope": SCOPES, "response_type": "code", "mode": SMARTCAR_MODE }

    async def async_oauth_create_entry(self, data: dict) -> FlowResult:
        """Create an entry for the flow, adding scope to token data."""
        _LOGGER.info("OAuth authentication successful, processing token data")
        if "token" in data:
            if "scope" not in data["token"] or data["token"].get("scope") != SCOPES:
                _LOGGER.warning("Scope missing/differs in token data, manually injecting requested scopes.")
                data["token"]["scope"] = SCOPES
        else:
            _LOGGER.error("Token data missing from OAuth callback data!")
        title = DEFAULT_NAME
        _LOGGER.debug("Creating config entry with final data.") # Keep brief debug maybe
        return self.async_create_entry(title=title, data=data)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Perform reauth when requested by Home Assistant."""
        _LOGGER.info("Starting Smartcar re-authentication flow for %s", entry_data.get("title", "entry"))
        return await self.async_step_user()