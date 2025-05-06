from __future__ import annotations

import logging
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.components.device_tracker.config_entry import (
    TrackerEntity,
    TrackerEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
from .coordinator import SmartcarVehicleCoordinator, SmartcarCoordinatorEntity

_LOGGER = logging.getLogger(__name__)
ENTITY_DESCRIPTIONS: tuple[TrackerEntityDescription, ...] = (
    TrackerEntityDescription(key="location", name="Location", icon="mdi:car"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators: dict[str, SmartcarVehicleCoordinator] = (
        entry.runtime_data.coordinators
    )
    entities = []
    for vin, coordinator in coordinators.items():
        for description in ENTITY_DESCRIPTIONS:
            if coordinator.is_scope_enabled(description.key, verbose=True):
                entities.append(SmartcarLocationTracker(coordinator, description))
    _LOGGER.info("Adding %d Smartcar device tracker entities", len(entities))
    async_add_entities(entities)


class SmartcarLocationTracker(SmartcarCoordinatorEntity, TrackerEntity):
    _attr_has_entity_name = True

    def __init__(self, coord, desc):
        super().__init__(coord, desc)
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
