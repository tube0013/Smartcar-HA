from __future__ import annotations

import asyncio
import logging
from aiohttp import ClientResponseError
from typing import Any, Mapping
import voluptuous as vol
from urllib.parse import urlencode, urlparse, parse_qs

from homeassistant.const import CONF_ACCESS_TOKEN, CONF_TOKEN
from homeassistant.data_entry_flow import AbortFlow, FlowResult
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import (
    AbstractOAuth2FlowHandler,
    async_get_implementations,
)
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import DOMAIN, SMARTCAR_MODE, DEFAULT_NAME, API_BASE_URL_V2

_LOGGER = logging.getLogger(__name__)

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


class SmartcarOAuth2FlowHandler(AbstractOAuth2FlowHandler, domain=DOMAIN):
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
                    implementations = await async_get_implementations(
                        self.hass, self.DOMAIN
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

        session = async_get_clientsession(self.hass)
        token = data[CONF_TOKEN][CONF_ACCESS_TOKEN]
        await self._store_all_vehicles(data, session, token)

        _LOGGER.debug("Creating config entry with final data.")
        return self.async_create_entry(title=DEFAULT_NAME, data=data)

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

    async def _store_all_vehicles(self, data, session, token):
        data["vehicles"] = {}

        try:
            _LOGGER.info("Fetching Smartcar vehicle IDs...")
            vehicle_list_resp = await session.request(
                "get",
                f"{API_BASE_URL_V2}/vehicles",
                headers={"authorization": f"Bearer {token}"},
            )
            vehicle_list_resp.raise_for_status()
            vehicle_list_data = await vehicle_list_resp.json()
            vehicle_ids = vehicle_list_data.get("vehicles", [])
            _LOGGER.info("Found %d vehicle IDs", len(vehicle_ids))
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise ConfigEntryAuthFailed(
                    f"Auth error fetching vehicle list: {err.status}"
                ) from err
            else:
                _LOGGER.exception("HTTP Error fetching vehicle list")
                return False
        except ConfigEntryAuthFailed:
            raise  # Already logged by helper potentially
        except Exception:
            _LOGGER.exception("Unexpected error fetching vehicle list")
            return False

        if not vehicle_ids:
            _LOGGER.warning("No vehicle IDs found.")
            return True

        setup_tasks = [
            self._store_vehicle_details(data, session, token, vid)
            for vid in vehicle_ids
        ]
        results = await asyncio.gather(*setup_tasks, return_exceptions=True)

        auth_failed = any(
            isinstance(res, ConfigEntryAuthFailed)
            for res in results
            if isinstance(res, Exception)
        )
        any_failed = any(isinstance(res, Exception) for res in results)

        if auth_failed:
            _LOGGER.error("Authentication failed during setup of at least one vehicle.")
            return False

        if any_failed:
            _LOGGER.warning("One or more vehicles failed non-critical setup steps.")

    async def _store_vehicle_details(
        self,
        data: dict,
        session: asyncio.ClientSession,
        token: str,
        vehicle_id: str,
    ) -> None:
        """Fetch data for a single vehicle. Raises exceptions on failure."""
        try:
            # Get VIN (read_vin scope)
            _LOGGER.debug("Fetching VIN for vehicle ID: %s", vehicle_id)
            vin_resp = await session.request(
                "get",
                f"{API_BASE_URL_V2}/vehicles/{vehicle_id}/vin",
                headers={"authorization": f"Bearer {token}"},
            )
            vin_resp.raise_for_status()
            vin_data = await vin_resp.json()
            vin = vin_data.get("vin")
            if not vin:
                raise ValueError("Missing VIN")

            data["vehicles"][vehicle_id] = {
                "vin": vin,
            }

            # Get Attributes (read_vehicle_info scope)
            _LOGGER.debug("Fetching attributes for VIN: %s (ID: %s)", vin, vehicle_id)
            attr_resp = await session.request(
                "get",
                f"{API_BASE_URL_V2}/vehicles/{vehicle_id}",
                headers={"authorization": f"Bearer {token}"},
            )
            attr_resp.raise_for_status()
            vehicle_info = await attr_resp.json()
            make = vehicle_info.get("make")
            model = vehicle_info.get("model")
            year = vehicle_info.get("year")

            data["vehicles"][vehicle_id].update(
                {
                    "make": make,
                    "model": model,
                    "year": year,
                }
            )
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise ConfigEntryAuthFailed(
                    f"Auth error [{err.status}] during vehicle setup"
                ) from err
            else:
                raise UpdateFailed(f"API error during setup: {err.status}") from err
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            raise err
