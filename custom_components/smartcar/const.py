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
OAUTH2_TOKEN = "https://auth.smartcar.com/oauth/token"
SMARTCAR_MODE = "live"


class Scope(StrEnum):
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
