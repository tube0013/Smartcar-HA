from __future__ import annotations

import logging
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
from .coordinator import SmartcarVehicleCoordinator, SmartcarCoordinatorEntity

_LOGGER = logging.getLogger(__name__)
SENSOR_TYPES: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="plug_status",
        name="Charging Cable Plugged In",
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
    _LOGGER.info("Adding %d Smartcar binary sensor entities", len(entities))
    async_add_entities(entities)


class SmartcarBinarySensor(SmartcarCoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coord, desc):
        super().__init__(coord, desc)
        self.vin = coord.vin
        self.entity_description = desc
        self._attr_unique_id = f"{self.vin}_{desc.key}"
        self._attr_device_info = {"identifiers": {(DOMAIN, self.vin)}}

    @property
    def is_on(self):
        data = self.coordinator.data
        charge = data.get("charge") if data else None
        return charge.get("isPluggedIn") if charge else None

    @property
    def available(self):
        data = self.coordinator.data
        charge = None
        if super().available and data is not None:
            charge = data.get("charge")
        return charge is not None and "isPluggedIn" in charge
