from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPressure,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util.unit_conversion import DistanceConverter, PressureConverter

from .const import EntityDescriptionKey
from .coordinator import (
    TIRE_BACK_ROW,
    TIRE_FRONT_ROW,
    TIRE_LEFT_COLUMN,
    TIRE_RIGHT_COLUMN,
    SmartcarVehicleCoordinator,
)
from .entity import SmartcarEntity, SmartcarEntityDescription

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SmartcarSensorDescription(SensorEntityDescription, SmartcarEntityDescription):
    """Class describing Smartcar sensor entities."""


SENSOR_TYPES: tuple[SmartcarSensorDescription, ...] = (
    SmartcarSensorDescription(
        key=EntityDescriptionKey.BATTERY_CAPACITY,
        name="Battery Capacity",
        value_key_path="tractionbattery-nominalcapacity.capacity",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    SmartcarSensorDescription(
        key=EntityDescriptionKey.BATTERY_LEVEL,
        name="Battery",
        value_key_path="tractionbattery-stateofcharge.value",
        value_cast=lambda pct: pct and round(pct * 100),
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SmartcarSensorDescription(
        key=EntityDescriptionKey.CHARGING_STATE,
        name="Charging Status",
        value_key_path="charge-detailedchargingstatus.value",
        icon="mdi:ev-station",
    ),
    SmartcarSensorDescription(
        key=EntityDescriptionKey.ENGINE_OIL,
        name="Engine Oil Life",
        value_key_path="internalcombustionengine-oillife.value",
        icon="mdi:oil-level",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SmartcarSensorDescription(
        key=EntityDescriptionKey.FUEL,
        name="Fuel",
        value_key_path="internalcombustionengine-amountremaining.value",
        icon="mdi:gas-station",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        imperial_conversion=lambda v: DistanceConverter.convert(
            v, UnitOfVolume.GALLONS, UnitOfVolume.LITERS
        ),
    ),
    SmartcarSensorDescription(
        key=EntityDescriptionKey.FUEL_PERCENT,
        name="Fuel Percent",
        value_key_path="internalcombustionengine-fuellevel.value",
        value_cast=lambda pct: pct and round(pct * 100),
        icon="mdi:gas-station",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SmartcarSensorDescription(
        key=EntityDescriptionKey.FUEL_RANGE,
        name="Fuel Range",
        value_key_path="internalcombustionengine-range.value",
        icon="mdi:map-marker-distance",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        imperial_conversion=lambda v: DistanceConverter.convert(
            v, UnitOfLength.MILES, UnitOfLength.KILOMETERS
        ),
    ),
    SmartcarSensorDescription(
        key=EntityDescriptionKey.ODOMETER,
        name="Odometer",
        value_key_path="odometer-traveleddistance.value",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        imperial_conversion=lambda v: DistanceConverter.convert(
            v, UnitOfLength.MILES, UnitOfLength.KILOMETERS
        ),
    ),
    SmartcarSensorDescription(
        key=EntityDescriptionKey.RANGE,
        name="Range",
        value_key_path="tractionbattery-range.value",
        icon="mdi:map-marker-distance",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        imperial_conversion=lambda v: DistanceConverter.convert(
            v, UnitOfLength.MILES, UnitOfLength.KILOMETERS
        ),
    ),
    SmartcarSensorDescription(
        key=EntityDescriptionKey.TIRE_PRESSURE_BACK_LEFT,
        name="Tire Pressure Back Left",
        value_key_path="wheel-tires.values",
        value_cast=lambda values: next(
            (
                value["tirePressure"]
                for value in values or []
                if value["row"] == TIRE_BACK_ROW and value["column"] == TIRE_LEFT_COLUMN
            ),
            None,
        ),
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        native_unit_of_measurement=UnitOfPressure.KPA,
        imperial_conversion=lambda v: PressureConverter.convert(
            v, UnitOfPressure.PSI, UnitOfPressure.KPA
        ),
    ),
    SmartcarSensorDescription(
        key=EntityDescriptionKey.TIRE_PRESSURE_BACK_RIGHT,
        name="Tire Pressure Back Right",
        value_key_path="wheel-tires.values",
        value_cast=lambda values: next(
            (
                value["tirePressure"]
                for value in values or []
                if value["row"] == TIRE_BACK_ROW
                and value["column"] == TIRE_RIGHT_COLUMN
            ),
            None,
        ),
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        native_unit_of_measurement=UnitOfPressure.KPA,
        imperial_conversion=lambda v: PressureConverter.convert(
            v, UnitOfPressure.PSI, UnitOfPressure.KPA
        ),
    ),
    SmartcarSensorDescription(
        key=EntityDescriptionKey.TIRE_PRESSURE_FRONT_LEFT,
        name="Tire Pressure Front Left",
        value_key_path="wheel-tires.values",
        value_cast=lambda values: next(
            (
                value["tirePressure"]
                for value in values or []
                if value["row"] == TIRE_FRONT_ROW
                and value["column"] == TIRE_LEFT_COLUMN
            ),
            None,
        ),
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        native_unit_of_measurement=UnitOfPressure.KPA,
        imperial_conversion=lambda v: PressureConverter.convert(
            v, UnitOfPressure.PSI, UnitOfPressure.KPA
        ),
    ),
    SmartcarSensorDescription(
        key=EntityDescriptionKey.TIRE_PRESSURE_FRONT_RIGHT,
        name="Tire Pressure Front Right",
        value_key_path="wheel-tires.values",
        value_cast=lambda values: next(
            (
                value["tirePressure"]
                for value in values or []
                if value["row"] == TIRE_FRONT_ROW
                and value["column"] == TIRE_RIGHT_COLUMN
            ),
            None,
        ),
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        native_unit_of_measurement=UnitOfPressure.KPA,
        imperial_conversion=lambda v: PressureConverter.convert(
            v, UnitOfPressure.PSI, UnitOfPressure.KPA
        ),
    ),
)


async def async_setup_entry(  # noqa: RUF029
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from coordinator."""
    coordinators: dict[str, SmartcarVehicleCoordinator] = (
        entry.runtime_data.coordinators
    )
    _LOGGER.debug("Setting up sensors for VINs: %s", list(coordinators.keys()))
    entities = [
        SmartcarSensor(coordinator, description)
        for coordinator in coordinators.values()
        for description in SENSOR_TYPES
        if coordinator.is_scope_enabled(description.key, verbose=True)
    ]
    _LOGGER.info("Adding %s Smartcar sensor entities", len(entities))
    async_add_entities(entities)


class SmartcarSensor[ValueT, RawValueT](
    SmartcarEntity[ValueT, RawValueT], SensorEntity
):
    """Sensor entity."""

    _attr_has_entity_name = True

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        return self._extract_value()
