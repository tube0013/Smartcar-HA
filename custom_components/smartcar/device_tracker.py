from dataclasses import dataclass
import logging

from homeassistant.components.device_tracker.config_entry import (
    TrackerEntity,
    TrackerEntityDescription,
)
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import EntityDescriptionKey
from .coordinator import SmartcarVehicleCoordinator
from .entity import SmartcarEntity, SmartcarEntityDescription

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SmartcarTrackerDescription(TrackerEntityDescription, SmartcarEntityDescription):
    """Class describing Smartcar tracker entities."""


ENTITY_DESCRIPTIONS: tuple[TrackerEntityDescription, ...] = (
    SmartcarTrackerDescription(
        key=EntityDescriptionKey.LOCATION,
        name="Location",
        value_key_path="location",
        value_cast=lambda location: location or {},
        icon="mdi:car",
    ),
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
    _LOGGER.info(f"Adding {len(entities)} Smartcar device tracker entities")
    async_add_entities(entities)


class SmartcarLocationTracker(SmartcarEntity, TrackerEntity):
    _attr_has_entity_name = True

    @property
    def latitude(self):
        return self._extract_value().get("latitude")

    @property
    def longitude(self):
        return self._extract_value().get("longitude")

    @property
    def source_type(self):
        return SourceType.GPS
