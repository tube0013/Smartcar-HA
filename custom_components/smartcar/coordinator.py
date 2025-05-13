from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .auth import AbstractAuth
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

INTERVAL_CHARGING = timedelta(minutes=15)  # poll more often when charging
INTERVAL_IDLE = timedelta(hours=4)  # poll less often when idle

# fequests based on context/importance with keys matching entity keys
BASE_REQUESTS = ["charging", "battery_level", "plug_status", "range"]
CHARGING_REQUESTS = ["charge_limit"]
IDLE_REQUESTS = [
    "odometer",
    "location",
    "door_lock",
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
    "battery_capacity": EntityConfig("/battery/nominal_capacity", ["read_battery"]),
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

    update_interval: timedelta

    def __init__(
        self,
        hass: HomeAssistant,
        auth: AbstractAuth,
        vehicle_id: str,
        vin: str,
        entry: ConfigEntry,
    ):
        """Initialize coordinator."""
        self.auth = auth
        self.vehicle_id = vehicle_id
        self.vin = vin
        self.entry = entry
        self.batch_requests: set[str] = set()

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{vin}",
            update_interval=INTERVAL_IDLE,
        )

        _LOGGER.debug(
            f"Coordinator {self.name}: Initialized with interval {INTERVAL_IDLE}"
        )

    def is_scope_enabled(self, sensor_key: str, verbose=False):
        token_scopes = self.config_entry.data.get("token", {}).get("scopes", [])
        required_scopes = ENTITY_CONFIG_MAP[sensor_key].required_scopes
        missing = [scope for scope in required_scopes if scope not in token_scopes]
        enabled = len(missing) == 0

        if not enabled and verbose:
            _LOGGER.warning(
                f"Skipping `{sensor_key}` which requires {repr(required_scopes)}, but "
                f"user is missing {repr(missing)} with enabled scopes of {repr(token_scopes)}."
            )

        return enabled

    def batch_sensor(self, sensor: CoordinatorEntity):
        """Mark a sensor to be included in the next update batch."""
        self._batch_add(sensor.entity_description.key)

    def _batch_add(self, key: str):
        """Mark data as needing to be fetched in the next update batch."""

        assert self.is_scope_enabled(key)

        self.batch_requests.add(key)

    def _batch_add_defaults(self):
        """
        Add default batch paths to request when none were explicitly requested.

        Explicit requests are considered to have been made when:

        - There are already requests that have been made (via the
          `home_assistant.update_entity` action). This method will
          short-circuit and not add additional items to the batch.
        - When polling is disabled, no defaults are added to the batch. This
          prevents requests being made across all endpoints that apply to
          (enabled) entities when Home Assistant starts or the config entry is
          reloaded.

        When polling is enabled and there have been no explicit update requests:

        - BASE_REQUESTS will always be added.
        - CHARGING_REQUESTS will be added when charging
        - IDLE_REQUESTS will be added when not charging

        The resulting list is filtered to only include keys that are associated
        with entities that are active (not marked as disabled) in the entity
        registry. (Note: this means that during config entry setup, platform
        initialization needs to occur before the first refresh or the entity
        registry will be empty.)
        """
        if self.batch_requests:
            return
        if self.config_entry.pref_disable_polling:
            return

        requests = []
        current_data = self.data or {}
        charge_data = current_data.get("charge", {})
        is_charging = charge_data.get("state") == "CHARGING"

        requests.extend(BASE_REQUESTS)
        requests.extend(CHARGING_REQUESTS if is_charging else IDLE_REQUESTS)

        entities: list[er.RegistryEntry] = er.async_entries_for_config_entry(
            er.async_get(self.hass), self.config_entry.entry_id
        )

        for entity in entities:
            vin, key = entity.unique_id.split("_", 1)
            if key in requests and not entity.disabled:
                self._batch_add(key)

    def _batch_proccess(self) -> list[str]:
        """
        Process a batch of paths to request.
        """
        self._batch_add_defaults()

        result: list[str] = list(self.batch_requests)

        self.batch_requests.clear()

        return result

    async def _async_update_data(self):
        """Fetch data from API using selective batch endpoint and adjust interval."""

        batch_requests = self._batch_proccess()
        request_path = f"vehicles/{self.vehicle_id}/batch"
        request_batch_paths = sorted(
            {ENTITY_CONFIG_MAP[key].endpoint for key in batch_requests}
        )
        request_body = {"requests": [{"path": path} for path in request_batch_paths]}

        if not batch_requests:
            _LOGGER.warning(
                f"Coordinator {self.name}: No updates to request based on granted scopes and context.",
            )
            return self.data

        _LOGGER.debug(
            f"Coordinator {self.name}: Requesting batch update (Interval: {self.update_interval}) for paths: {request_batch_paths}",
        )

        response = await self.auth.request("post", request_path, json=request_body)
        response.raise_for_status()
        response_data = await response.json()

        if "responses" not in response_data:
            raise UpdateFailed("Invalid batch response format")

        merged_data = self._merge_batch_data(response_data)

        self._adjust_update_interval(merged_data)

        return merged_data

    def _merge_batch_data(self, batch_data):
        """Fetch data from API using selective batch endpoint and adjust interval."""
        updated_data = dict(self.data or {})

        for item in batch_data["responses"]:
            path = item["path"]
            code = item["code"]
            body = item["body"]
            headers = item.get("headers") or {}
            unit_system = headers.get("sc-unit-system")
            key = path.strip("/").replace("/", "_")
            updated_data[key] = body if code == 200 else None

            if code == 200 and unit_system:
                updated_data[f"{key}:unit_system"] = unit_system

            if code not in (200, 404):
                _LOGGER.warning(
                    f"Coordinator {self.name}: Status {code} for path {path}",
                )

        _LOGGER.debug(f"Coordinator {self.name}: Batch update processed")

        return updated_data

    def _adjust_update_interval(self, updated_data):
        """Adjust the update interval based on charging state."""

        is_charging = updated_data.get("charge", {}).get("state") == "CHARGING"
        interval = INTERVAL_CHARGING if is_charging else INTERVAL_IDLE

        if interval != self.update_interval:
            _LOGGER.info(
                f"Coordinator {self.name}: Setting update interval to {interval}",
            )
            self.update_interval = interval
