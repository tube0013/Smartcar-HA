# custom_components/smartcar/coordinator.py

import asyncio
import logging
from datetime import timedelta

from aiohttp import ClientResponseError
from homeassistant.exceptions import ConfigEntryAuthFailed

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session

from .const import DOMAIN, API_BASE_URL_V2

_LOGGER = logging.getLogger(__name__)

INTERVAL_CHARGING = timedelta(minutes=30)
INTERVAL_IDLE = timedelta(hours=6)

BATCH_PATHS = [
    "/odometer", "/battery", "/charge", "/security", "/location",
    "/tires/pressure", "/engine/oil", "/fuel", "/battery/capacity",
    "/charge/limit",
]

class SmartcarVehicleCoordinator(DataUpdateCoordinator):
    """Coordinates updates for a single Smartcar vehicle using batch requests."""

    def __init__(self, hass: HomeAssistant, session: OAuth2Session, vehicle_id: str, vin: str, entry: ConfigEntry):
        """Initialize coordinator."""
        self.session = session
        self.vehicle_id = vehicle_id
        self.vin = vin
        self.entry = entry
        self.units = "metric"
        current_interval = INTERVAL_IDLE

        super().__init__(
            hass, _LOGGER, name=f"{DOMAIN}_{vin}", update_interval=current_interval,
        )
        _LOGGER.info("Coordinator %s: Initialized with update interval %s", self.name, current_interval)

    async def _async_update_data(self):
        """Fetch data from API using the batch endpoint and adjust interval."""
        api_batch_url = f"{API_BASE_URL_V2}/vehicles/{self.vehicle_id}/batch"
        _LOGGER.debug("Coordinator %s: Requesting batch update (Current Interval: %s)", self.name, self.update_interval)
        request_body = {"requests": [{"path": path} for path in BATCH_PATHS]}

        try:
            response = await self.session.async_request("post", api_batch_url, json=request_body)
            if response.status in (401, 403): raise ConfigEntryAuthFailed(f"Auth error on batch request: {response.status}")
            response.raise_for_status()
            batch_response_data = await response.json()

            processed_data = {}
            units_header = None
            if "responses" not in batch_response_data: raise UpdateFailed("Invalid batch response format")

            for item in batch_response_data["responses"]:
                path = item.get("path"); code = item.get("code"); body = item.get("body"); headers = item.get("headers", {})
                data_key = path.strip('/').replace('/', '_') if path else None
                if not data_key: continue

                if code == 200:
                    processed_data[data_key] = body
                    if data_key == "odometer" and not units_header: units_header = headers.get("sc-unit-system")
                else:
                    processed_data[data_key] = None
                    # Log only permission errors or unexpected codes, not 404s often
                    if code != 404: _LOGGER.info("Coordinator %s: Status %s for path %s", self.name, code, path)
                    # Note: Auth check is primarily on the main request now

            self.units = units_header if units_header else self.units
            processed_data["units"] = self.units
            _LOGGER.debug("Coordinator %s: Batch update processed", self.name)

            # Adjust Update Interval
            new_interval = INTERVAL_IDLE
            charge_data = processed_data.get("charge")
            if charge_data and charge_data.get("state") == "CHARGING": new_interval = INTERVAL_CHARGING
            if new_interval != self.update_interval:
                _LOGGER.info("Coordinator %s: Setting update interval to %s", self.name, new_interval)
                self.async_set_update_interval(new_interval)

            return processed_data

        except ConfigEntryAuthFailed as err:
             _LOGGER.warning("Coordinator %s: Auth error during update: %s", self.name, err)
             raise UpdateFailed(f"Authentication failed: {err}") from err
        except ClientResponseError as err:
            _LOGGER.error("Coordinator %s: HTTP error during update [%s]: %s", self.name, err.status, err)
            raise UpdateFailed(f"API error: {err}") from err
        except Exception as err:
            _LOGGER.exception("Coordinator %s: Unexpected error during update: %s", self.name, err)
            raise UpdateFailed(f"Unexpected API error: {err}") from err