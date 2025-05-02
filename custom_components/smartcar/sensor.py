# custom_components/smartcar/sensor.py

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from homeassistant.helpers.typing import StateType

from homeassistant.components.sensor import (
    SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE, UnitOfEnergy, UnitOfLength, UnitOfPressure, UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmartcarVehicleCoordinator

_LOGGER = logging.getLogger(__name__)

# Sensor Descriptions
SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(key="odometer", name="Odometer", device_class=SensorDeviceClass.DISTANCE, state_class=SensorStateClass.TOTAL_INCREASING),
    SensorEntityDescription(key="battery_level", name="Battery", device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT, native_unit_of_measurement=PERCENTAGE),
    SensorEntityDescription(key="range", name="Range", icon="mdi:map-marker-distance", device_class=SensorDeviceClass.DISTANCE, state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key="charging_state", name="Charging Status", icon="mdi:ev-station"),
    SensorEntityDescription(key="engine_oil", name="Engine Oil Life", icon="mdi:oil-level", state_class=SensorStateClass.MEASUREMENT, native_unit_of_measurement=PERCENTAGE),
    SensorEntityDescription(key="battery_capacity", name="Battery Capacity", device_class=SensorDeviceClass.ENERGY_STORAGE, state_class=SensorStateClass.MEASUREMENT, native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, entity_registry_enabled_default=False),
    SensorEntityDescription(key="tire_pressure_front_left", name="Tire Pressure Front Left", device_class=SensorDeviceClass.PRESSURE, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1),
    SensorEntityDescription(key="tire_pressure_front_right", name="Tire Pressure Front Right", device_class=SensorDeviceClass.PRESSURE, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1),
    SensorEntityDescription(key="tire_pressure_back_left", name="Tire Pressure Back Left", device_class=SensorDeviceClass.PRESSURE, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1),
    SensorEntityDescription(key="tire_pressure_back_right", name="Tire Pressure Back Right", device_class=SensorDeviceClass.PRESSURE, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1),
)

def _get_value_from_coordinator(coordinator_data: dict | None, entity_key: str) -> Any | None:
    """Extract the specific value for an entity key from coordinator data."""
    # ... (Keep implementation from previous version) ...
    if not coordinator_data: return None
    try:
        if entity_key == "odometer": data = coordinator_data.get("odometer"); return data.get("distance") if data else None
        if entity_key == "battery_level": data = coordinator_data.get("battery"); percent = data.get("percentRemaining") if data else None; return round(percent * 100) if percent is not None else None
        if entity_key == "range": data = coordinator_data.get("battery"); return data.get("range") if data else None
        if entity_key == "charging_state": data = coordinator_data.get("charge"); return data.get("state") if data else None # Use 'charge' key
        if entity_key == "engine_oil": data = coordinator_data.get("engine_oil"); return data.get("lifeRemaining") if data else None
        if entity_key == "battery_capacity": data = coordinator_data.get("battery_capacity"); return data.get("capacity") if data else None
        if entity_key.startswith("tire_pressure"):
            data = coordinator_data.get("tires");
            if not data: return None
            tire_map = {"tire_pressure_front_left": "frontLeft", "tire_pressure_front_right": "frontRight", "tire_pressure_back_left": "backLeft", "tire_pressure_back_right": "backRight"}
            api_key = tire_map.get(entity_key); return data.get(api_key) if api_key else None
    except Exception as e: _LOGGER.warning("Error extracting value for key %s: %s", entity_key, e) # Warning level now
    return None

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up sensors from coordinator."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, SmartcarVehicleCoordinator] = entry_data.get("coordinators", {})
    _LOGGER.debug("Setting up sensors for VINs: %s", list(coordinators.keys()))
    entities = []
    for vin, coordinator in coordinators.items():
        if not coordinator.last_update_success or not coordinator.data: continue
        for description in SENSOR_TYPES:
            value = _get_value_from_coordinator(coordinator.data, description.key)
            if value is not None: entities.append(SmartcarSensor(coordinator, description))
    _LOGGER.info("Adding %d Smartcar sensor entities", len(entities))
    async_add_entities(entities)


class SmartcarSensor(CoordinatorEntity[SmartcarVehicleCoordinator], SensorEntity):
    """Implementation of a Smartcar sensor."""
    _attr_has_entity_name = True

    def __init__(self, coordinator: SmartcarVehicleCoordinator, description: SensorEntityDescription):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.vin = coordinator.vin
        self.entity_description = description
        self._attr_native_unit_of_measurement = getattr(description, 'native_unit_of_measurement', None)
        self._attr_unique_id = f"{self.vin}_{description.key}"
        self._attr_device_info = {"identifiers": {(DOMAIN, self.vin)}}
        self._update_unit_from_coordinator() # Set initial unit

    def _get_coordinator_units(self) -> str | None:
        # ... (same as before) ...
        if self.coordinator and self.coordinator.data: return self.coordinator.data.get("units")
        return None

    def _update_unit_from_coordinator(self): # Removed log_details flag
        """Update unit based on coordinator data, only if needed."""
        # ... (same logic as before to determine new_unit) ...
        key = self.entity_description.key; log_id = self.entity_id or self._attr_unique_id
        coordinator_units = self._get_coordinator_units() or "metric"
        new_unit = getattr(self.entity_description, 'native_unit_of_measurement', None)
        if key == "odometer" or key == "range":
            if coordinator_units: new_unit = UnitOfLength.KILOMETERS if coordinator_units == "metric" else UnitOfLength.MILES
            else: new_unit = None
        elif key.startswith("tire_pressure"):
            if coordinator_units: new_unit = UnitOfPressure.KPA if coordinator_units == "metric" else UnitOfPressure.PSI
            else: new_unit = None
        current_unit = getattr(self, "_attr_native_unit_of_measurement", "NOT_SET")
        if new_unit != current_unit:
             _LOGGER.debug("Sensor %s: Updating unit from %s to %s", log_id, current_unit, new_unit) # Keep this debug maybe
             self._attr_native_unit_of_measurement = new_unit

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        """Return the state of the sensor."""
        self._update_unit_from_coordinator()
        value = _get_value_from_coordinator(self.coordinator.data, self.entity_description.key)
        # Removed verbose logging from here
        return value

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        value = _get_value_from_coordinator(self.coordinator.data, self.entity_description.key)
        is_available = super().available and value is not None
        # Removed verbose logging from here
        return is_available