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

from .const import EntityDescriptionKey
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
        key=EntityDescriptionKey.PLUG_STATUS,
        name="Charging Cable Plugged In",
        value_key_path="charge.isPluggedIn",
        device_class=BinarySensorDeviceClass.PLUG,
    ),
)


async def async_setup_entry(  # noqa: RUF029
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinators: dict[str, SmartcarVehicleCoordinator] = (
        entry.runtime_data.coordinators
    )
    entities = [
        SmartcarBinarySensor(coordinator, description)
        for coordinator in coordinators.values()
        for description in SENSOR_TYPES
        if coordinator.is_scope_enabled(description.key, verbose=True)
    ]
    _LOGGER.info("Adding %s Smartcar binary sensor entities", len(entities))
    async_add_entities(entities)


class SmartcarBinarySensor(SmartcarEntity[bool, bool], BinarySensorEntity):
    """Binary sensor entity for plugged in status."""

    _attr_has_entity_name = True

    @property
    def is_on(self) -> bool:
        return self._extract_value()
