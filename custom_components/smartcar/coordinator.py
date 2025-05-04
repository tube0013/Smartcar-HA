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

INTERVAL_CHARGING = timedelta(minutes=15) # Poll more often when charging
INTERVAL_IDLE = timedelta(hours=4)      # Poll less often when idle

# Define path sets based on context and importance
# Always get charge status to determine state/interval and battery for range/soc
BASE_PATHS = ["/charge", "/battery"]
# Paths useful primarily when charging
CHARGING_PATHS = ["/charge/limit"]
# Paths useful when idle/driving (less frequent updates needed maybe?)
IDLE_PATHS = ["/odometer", "/location", "/security"] # Security likely fails anyway
# Paths for potentially static or infrequently changing data (or unsupported)
INFREQUENT_PATHS = ["/battery/capacity", "/engine/oil", "/fuel", "/tires/pressure"]

class SmartcarVehicleCoordinator(DataUpdateCoordinator):
    """Coordinates updates with selective batch paths and dynamic interval."""

    def __init__(self, hass: HomeAssistant, session: OAuth2Session, vehicle_id: str, vin: str, entry: ConfigEntry):
        """Initialize coordinator."""
        self.session = session
        self.vehicle_id = vehicle_id
        self.vin = vin
        self.entry = entry
        self.units = "metric"
        # Store granted scopes for smarter path selection
        self.granted_scopes = entry.data.get("token", {}).get("scope", "").split()

        super().__init__(
            hass, _LOGGER, name=f"{DOMAIN}_{vin}", update_interval=INTERVAL_IDLE,
        )
        _LOGGER.info("Coordinator %s: Initialized with interval %s", self.name, INTERVAL_IDLE)
        # Store map of path to required read scope
        self._path_to_scope = {
            "/odometer": "read_odometer", "/battery": "read_battery",
            "/charge": "read_charge", "/security": "read_security",
            "/location": "read_location", "/tires/pressure": "read_tires",
            "/engine/oil": "read_engine_oil", "/fuel": "read_fuel",
            "/battery/capacity": "read_battery", # Uses same scope as battery level
            "/charge/limit": "read_charge",      # Uses same scope as charge status
        }

    def _get_paths_for_context(self, is_charging: bool) -> list[str]:
        """Determine which paths to request based on state and granted scopes."""
        paths_to_request = list(BASE_PATHS)
        if is_charging:
            paths_to_request.extend(CHARGING_PATHS)
        else:
            paths_to_request.extend(IDLE_PATHS)
            # Maybe include infrequent paths less often when idle? For now, always include if charging=False
            paths_to_request.extend(INFREQUENT_PATHS)

        # Filter paths based on scopes the user actually granted
        final_paths = []
        for path in set(paths_to_request): # Use set to remove duplicates
            required_scope = self._path_to_scope.get(path)
            if required_scope and required_scope in self.granted_scopes:
                final_paths.append(path)
            elif not required_scope:
                 # Path not mapped to a scope, include cautiously or log warning
                 _LOGGER.warning("Path %s not mapped to a known scope, requesting anyway.", path)
                 final_paths.append(path) # Or maybe exclude?
            else:
                 _LOGGER.debug("Skipping path %s as required scope '%s' was not granted.", path, required_scope)

        return sorted(final_paths)


    async def _async_update_data(self):
        """Fetch data from API using selective batch endpoint and adjust interval."""

        # Determine context from previous data
        is_charging = False
        if self.data and (charge_data := self.data.get("charge")):
            is_charging = charge_data.get("state") == "CHARGING"

        # Select paths for this update
        paths_to_request = self._get_paths_for_context(is_charging)

        if not paths_to_request:
            _LOGGER.warning("Coordinator %s: No paths to request based on granted scopes and context.", self.name)
            # Return previous data or empty dict? Or raise UpdateFailed?
            # Let's return current data to avoid state becoming Unknown if possible
            return self.data or {} # Return previous data if available


        api_batch_url = f"{API_BASE_URL_V2}/vehicles/{self.vehicle_id}/batch"
        _LOGGER.debug("Coordinator %s: Requesting batch update (Interval: %s) for paths: %s", self.name, self.update_interval, paths_to_request)
        request_body = {"requests": [{"path": path} for path in paths_to_request]}

        try:
            response = await self.session.async_request("post", api_batch_url, json=request_body)
            if response.status in (401, 403): raise ConfigEntryAuthFailed(f"Auth error on batch request: {response.status}")
            response.raise_for_status()
            batch_response_data = await response.json()

            # Process results - start with previous data to keep values for paths not requested this time
            processed_data = self.data.copy() if self.data else {} # Start with old data
            units_header = None
            if "responses" not in batch_response_data: raise UpdateFailed("Invalid batch response format")

            for item in batch_response_data["responses"]:
                path = item.get("path"); code = item.get("code"); body = item.get("body"); headers = item.get("headers", {})
                data_key = path.strip('/').replace('/', '_') if path else None
                if not data_key: continue

                # Only update keys for paths we actually requested this time
                if path in paths_to_request:
                    if code == 200:
                        processed_data[data_key] = body
                        if data_key == "odometer" and not units_header: units_header = headers.get("sc-unit-system")
                    else:
                        # Store None only if we expected data but failed, otherwise keep old value
                        processed_data[data_key] = None
                        if code != 404: _LOGGER.info("Coordinator %s: Status %s for path %s", self.name, code, path)


            self.units = units_header if units_header else self.units
            processed_data["units"] = self.units

            # Adjust interval based on NEW data
            new_interval = INTERVAL_IDLE
            new_charge_data = processed_data.get("charge") # Use updated charge data
            if new_charge_data and new_charge_data.get("state") == "CHARGING":
                new_interval = INTERVAL_CHARGING

            if new_interval != self.update_interval:
                 _LOGGER.info("Coordinator %s: Setting update interval to %s", self.name, new_interval)
                 self.async_set_update_interval(new_interval)

            _LOGGER.debug("Coordinator %s: Batch update processed", self.name)
            return processed_data

        # ... (Exception handling remains the same) ...
        except ConfigEntryAuthFailed as err: ...
        except ClientResponseError as err: ...
        except Exception as err: ...