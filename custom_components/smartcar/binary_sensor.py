from dataclasses import dataclass
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SmartcarVehicleCoordinator
from .entity import SmartcarEntity, SmartcarEntityDescription

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SmartcarBinarySensorDescription(
    BinarySensorEntityDescription, SmartcarEntityDescription
):
    """Class describing Smartcar binary sensor entities."""


SENSOR_TYPES: tuple[BinarySensorEntityDescription, ...] = (
    SmartcarBinarySensorDescription(
        key="plug_status",
        name="Charging Cable Plugged In",
        value_key_path="charge.isPluggedIn",
        device_class=BinarySensorDeviceClass.PLUG,
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
        for description in SENSOR_TYPES:
            if coordinator.is_scope_enabled(description.key, verbose=True):
                entities.append(SmartcarBinarySensor(coordinator, description))
    _LOGGER.info(f"Adding {len(entities)} Smartcar binary sensor entities")
    async_add_entities(entities)


class SmartcarBinarySensor(SmartcarEntity, BinarySensorEntity):
    _attr_has_entity_name = True

    @property
    def is_on(self):
        return self._extract_value()
