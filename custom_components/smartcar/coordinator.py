from __future__ import annotations

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
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, API_BASE_URL_V2

_LOGGER = logging.getLogger(__name__)

INTERVAL_CHARGING = timedelta(minutes=15)  # Poll more often when charging
INTERVAL_IDLE = timedelta(hours=4)  # Poll less often when idle

# Define request sets based on context and importance
# Always get charge status to determine state/interval and battery for range/soc
BASE_REQUESTS = ["charging", "battery_level", "plug_status", "range"]
# Paths useful primarily when charging
CHARGING_REQUESTS = ["charge_limit"]
# Paths useful when idle/driving (less frequent updates needed maybe?)
IDLE_REQUESTS = ["odometer", "location", "door_lock"]  # Security likely fails anyway
# Paths for potentially static or infrequently changing data (or unsupported)
INFREQUENT_REQUESTS = [
    "battery_capacity",
    "engine_oil",
    "fuel",
    "tire_pressure_back_left",
    "tire_pressure_back_right",
    "tire_pressure_front_left",
    "tire_pressure_front_right",
]


class EntityConfig:
    endpoint: str  # the read (and batch) endpoint
    required_scopes: list[str]

    def __init__(self, endpoint, required_scopes):
        self.endpoint = endpoint
        self.required_scopes = required_scopes


ENTITY_CONFIG_MAP = {
    "battery_capacity": EntityConfig("/battery/capacity", ["read_battery"]),
    "battery_level": EntityConfig("/battery", ["read_battery"]),
    "charge_limit": EntityConfig("/charge/limit", ["read_charge", "control_charge"]),
    "charging": EntityConfig(  # for the switch
        "/charge", ["read_charge", "control_charge"]
    ),
    "charging_state": EntityConfig("/charge", ["read_charge"]),
    "door_lock": EntityConfig("/security", ["read_security", "control_security"]),
    "engine_oil": EntityConfig("/engine/oil", ["read_engine_oil"]),
    "fuel": EntityConfig("/fuel", ["read_fuel"]),
    "location": EntityConfig("/location", ["read_location"]),
    "odometer": EntityConfig("/odometer", ["read_odometer"]),
    "plug_status": EntityConfig("/charge", ["read_charge"]),
    "range": EntityConfig("/battery", ["read_battery"]),
    "tire_pressure_back_left": EntityConfig("/tires/pressure", ["read_tires"]),
    "tire_pressure_back_right": EntityConfig("/tires/pressure", ["read_tires"]),
    "tire_pressure_front_left": EntityConfig("/tires/pressure", ["read_tires"]),
    "tire_pressure_front_right": EntityConfig("/tires/pressure", ["read_tires"]),
}


class SmartcarVehicleCoordinator(DataUpdateCoordinator):
    """Coordinates updates with selective batch paths and dynamic interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: OAuth2Session,
        vehicle_id: str,
        vin: str,
        entry: ConfigEntry,
    ):
        """Initialize coordinator."""
        self.session = session
        self.vehicle_id = vehicle_id
        self.vin = vin
        self.entry = entry
        self.units = "metric"
        self.batch_requests = set()

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{vin}",
            update_interval=INTERVAL_IDLE,
        )
        _LOGGER.info(
            "Coordinator %s: Initialized with interval %s", self.name, INTERVAL_IDLE
        )
        # Store map of path to required read scope
        self._path_to_scope = {
            "/odometer": "read_odometer",
            "/battery": "read_battery",
            "/charge": "read_charge",
            "/security": "read_security",
            "/location": "read_location",
            "/tires/pressure": "read_tires",
            "/engine/oil": "read_engine_oil",
            "/fuel": "read_fuel",
            "/battery/capacity": "read_battery",  # Uses same scope as battery level
            "/charge/limit": "read_charge",  # Uses same scope as charge status
        }

    def is_scope_enabled(self, sensor_key: str, verbose=False):
        token_scopes = self.config_entry.data.get("token", {}).get("scope", "").split()
        required_scopes = ENTITY_CONFIG_MAP[sensor_key].required_scopes
        enabled = all([scope in token_scopes for scope in required_scopes])

        if not enabled and verbose:
            _LOGGER.warning(
                f"Skipping `{sensor_key}` because not all required scopes {repr(required_scopes)} were enabled."
            )

        return enabled

    def batch_sensor(self, sensor: SmartcarCoordinatorEntity):
        """Mark a sensor to be included in the next update batch."""
        self._batch_add(sensor.entity_description.key)

    def _batch_add(self, key: str):
        """Mark data as needing to be fetched in the next update batch."""

        if self.is_scope_enabled(key):
            self.batch_requests.add(key)

    def _batch_add_defaults(self, is_charging: bool) -> list[str]:
        """
        Determine which paths to request based on whether the entity is
        enabled and granted scopes.
        """
        requests = list(BASE_REQUESTS)

        if is_charging:
            requests.extend(CHARGING_REQUESTS)
        else:
            requests.extend(IDLE_REQUESTS)
            # Maybe include infrequent paths less often when idle? For now, always include if charging=False
            requests.extend(INFREQUENT_REQUESTS)

        enabled_keys: set[str] = set()
        entities: list[er.RegistryEntry] = er.async_entries_for_config_entry(
            er.async_get(self.hass), self.config_entry.entry_id
        )
        for entity in entities:
            vin, key = entity.unique_id.split("_", 1)

            if not entity.disabled:
                enabled_keys.add(key)

        for key in requests:
            if key in enabled_keys:
                self._batch_add(key)

    async def _async_update_data(self):
        """Fetch data from API using selective batch endpoint and adjust interval."""

        # Determine context from previous data
        is_charging = False
        if self.data and (charge_data := self.data.get("charge")):
            is_charging = charge_data.get("state") == "CHARGING"

        # Ensure batch requests have been populated for this update
        if not self.batch_requests:
            self._batch_add_defaults(is_charging)

        paths_to_request = sorted(
            {ENTITY_CONFIG_MAP[key].endpoint for key in self.batch_requests}
        )

        if not paths_to_request:
            _LOGGER.warning(
                "Coordinator %s: No paths to request based on granted scopes and context.",
                self.name,
            )
            # Return previous data or empty dict? Or raise UpdateFailed?
            # Let's return current data to avoid state becoming Unknown if possible
            return self.data or {}  # Return previous data if available

        api_batch_url = f"{API_BASE_URL_V2}/vehicles/{self.vehicle_id}/batch"
        _LOGGER.debug(
            "Coordinator %s: Requesting batch update (Interval: %s) for paths: %s",
            self.name,
            self.update_interval,
            paths_to_request,
        )
        request_body = {"requests": [{"path": path} for path in paths_to_request]}

        try:
            response = await self.session.async_request(
                "post", api_batch_url, json=request_body
            )
            if response.status in (401, 403):
                raise ConfigEntryAuthFailed(
                    f"Auth error on batch request: {response.status}"
                )
            response.raise_for_status()
            batch_response_data = await response.json()

            # Process results - start with previous data to keep values for paths not requested this time
            processed_data = (
                self.data.copy() if self.data else {}
            )  # Start with old data
            units_header = None
            if "responses" not in batch_response_data:
                raise UpdateFailed("Invalid batch response format")

            for item in batch_response_data["responses"]:
                path = item.get("path")
                code = item.get("code")
                body = item.get("body")
                headers = item.get("headers", {})
                data_key = path.strip("/").replace("/", "_") if path else None
                if not data_key:
                    continue

                # Only update keys for paths we actually requested this time
                if path in paths_to_request:
                    if code == 200:
                        processed_data[data_key] = body
                        if data_key == "odometer" and not units_header:
                            units_header = headers.get("sc-unit-system")
                    else:
                        # Store None only if we expected data but failed, otherwise keep old value
                        processed_data[data_key] = None
                        if code != 404:
                            _LOGGER.info(
                                "Coordinator %s: Status %s for path %s",
                                self.name,
                                code,
                                path,
                            )

            self.units = units_header if units_header else self.units
            processed_data["units"] = self.units

            # Adjust interval based on NEW data
            new_interval = INTERVAL_IDLE
            new_charge_data = processed_data.get("charge")  # Use updated charge data
            if new_charge_data and new_charge_data.get("state") == "CHARGING":
                new_interval = INTERVAL_CHARGING

            if new_interval != self.update_interval:
                _LOGGER.info(
                    "Coordinator %s: Setting update interval to %s",
                    self.name,
                    new_interval,
                )
                self.async_set_update_interval(new_interval)

            _LOGGER.debug("Coordinator %s: Batch update processed", self.name)
            return processed_data

        except ConfigEntryAuthFailed:
            ...
        except ClientResponseError:
            ...
        except Exception:
            ...
        finally:
            self.batch_requests.clear()


class SmartcarCoordinatorEntity(CoordinatorEntity[SmartcarVehicleCoordinator]):
    def __init__(
        self, coordinator: SmartcarVehicleCoordinator, description: EntityDescription
    ):
        super().__init__(coordinator)
        self.vin = coordinator.vin
        self.entity_description = description

    async def async_update(self) -> None:
        if not self.enabled:
            return

        self.coordinator.batch_sensor(self)

        await super().async_update()
