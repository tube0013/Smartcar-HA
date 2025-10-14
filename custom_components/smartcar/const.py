from enum import StrEnum, auto

DOMAIN = "smartcar"
DEFAULT_NAME = "Smartcar"
API_HOST = "https://api.smartcar.com"

PLATFORMS = [
    "sensor",
    "switch",
    "lock",
    "device_tracker",
    "binary_sensor",
    "number",
]

OAUTH2_AUTHORIZE = "https://connect.smartcar.com/oauth/authorize"
OAUTH2_TOKEN = "https://auth.smartcar.com/oauth/token"  # noqa: S105
SMARTCAR_MODE = "live"

CONF_APPLICATION_MANAGEMENT_TOKEN = "application_management_token"  # noqa: S105
CONF_CLOUDHOOK = "cloudhook"


class Scope(StrEnum):
    """Scope enumeration class."""

    READ_VEHICLE_INFO = auto()
    READ_VIN = auto()
    READ_BATTERY = auto()
    READ_CHARGE = auto()
    READ_ENGINE_OIL = auto()
    READ_FUEL = auto()
    READ_LOCATION = auto()
    READ_ODOMETER = auto()
    READ_SECURITY = auto()
    READ_TIRES = auto()
    CONTROL_CHARGE = auto()
    CONTROL_SECURITY = auto()


REQUIRED_SCOPES = [
    Scope.READ_VEHICLE_INFO,
    Scope.READ_VIN,
]

CONFIGURABLE_SCOPES = [scope for scope in Scope if scope not in REQUIRED_SCOPES]

DEFAULT_SCOPES = [
    Scope.READ_BATTERY,
    Scope.READ_CHARGE,
    Scope.READ_LOCATION,
    Scope.READ_ODOMETER,
    Scope.READ_SECURITY,
    Scope.READ_VEHICLE_INFO,
    Scope.READ_VIN,
    Scope.CONTROL_CHARGE,
]


class EntityDescriptionKey(StrEnum):
    """EntityDescriptionKey enumeration class."""

    PLUG_STATUS = auto()
    LOCATION = auto()
    DOOR_LOCK = auto()
    CHARGE_LIMIT = auto()
    CHARGING = auto()
    BATTERY_CAPACITY = auto()
    BATTERY_LEVEL = auto()
    CHARGING_STATE = auto()
    ENGINE_OIL = auto()
    FUEL = auto()
    FUEL_PERCENT = auto()
    FUEL_RANGE = auto()
    ODOMETER = auto()
    RANGE = auto()
    TIRE_PRESSURE_BACK_LEFT = auto()
    TIRE_PRESSURE_BACK_RIGHT = auto()
    TIRE_PRESSURE_FRONT_LEFT = auto()
    TIRE_PRESSURE_FRONT_RIGHT = auto()


DEFAULT_ENABLED_ENTITY_DESCRIPTION_KEYS = {
    EntityDescriptionKey.BATTERY_LEVEL,
    EntityDescriptionKey.CHARGING_STATE,
    EntityDescriptionKey.CHARGING,
    EntityDescriptionKey.DOOR_LOCK,
    EntityDescriptionKey.LOCATION,
    EntityDescriptionKey.PLUG_STATUS,
    EntityDescriptionKey.RANGE,
}
