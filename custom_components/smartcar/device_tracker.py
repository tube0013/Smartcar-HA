# custom_components/smartcar/device_tracker.py

import logging
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import SmartcarVehicleCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, SmartcarVehicleCoordinator] = entry_data.get(
        "coordinators", {}
    )
    entities = []
    token_scopes = entry.data.get("token", {}).get("scope", "").split()
    if "read_location" not in token_scopes:
        _LOGGER.warning("Missing 'read_location' scope.")
        return
    for vin, coordinator in coordinators.items():
        if (
            coordinator.last_update_success
            and coordinator.data
            and coordinator.data.get("location") is not None
        ):
            entities.append(SmartcarLocationTracker(coordinator))
    _LOGGER.info("Adding %d Smartcar device tracker entities", len(entities))
    async_add_entities(entities)


class SmartcarLocationTracker(
    CoordinatorEntity[SmartcarVehicleCoordinator], TrackerEntity
):
    # ... (__init__, latitude, longitude, source_type, available as before) ...
    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:car"

    def __init__(self, coord):
        super().__init__(coord)
        self.vin = coord.vin
        self._attr_unique_id = f"{self.vin}_location"
        self._attr_device_info = {"identifiers": {(DOMAIN, self.vin)}}

    @property
    def latitude(self):
        data = self.coordinator.data
        loc = data.get("location") if data else None
        return loc.get("latitude") if loc else None

    @property
    def longitude(self):
        data = self.coordinator.data
        loc = data.get("location") if data else None
        return loc.get("longitude") if loc else None

    @property
    def source_type(self):
        return SourceType.GPS

    @property
    def available(self):
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.get("location") is not None
        )
