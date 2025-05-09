# custom_components/smartcar/const.py

DOMAIN = "smartcar"
DEFAULT_NAME = "Smartcar"

# Platforms to set up
PLATFORMS = [
    "sensor",
    "switch",
    "lock",  # Will add 0 entities for your car, but keep platform for others
    "device_tracker",
    "binary_sensor",
    "number",  # <-- Add this
]

# OAuth2 Details
OAUTH2_AUTHORIZE = "https://connect.smartcar.com/oauth/authorize"
OAUTH2_TOKEN = "https://auth.smartcar.com/oauth/token"
SMARTCAR_MODE = "live"  # Or "test" or "simulated"

# Smartcar API Base URLs
API_BASE_URL_V2 = "https://api.smartcar.com/v2.0"
API_BASE_URL_V1 = "https://api.smartcar.com/v1.0"  # For Lock/Unlock POST
