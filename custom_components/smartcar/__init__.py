# custom_components/smartcar/__init__.py

import asyncio
import logging

from aiohttp import ClientResponseError
from homeassistant.exceptions import ConfigEntryAuthFailed

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow, device_registry as dr
from homeassistant.helpers.update_coordinator import UpdateFailed

from .coordinator import SmartcarVehicleCoordinator
from .const import DOMAIN, PLATFORMS, API_BASE_URL_V2

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smartcar from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    hass.data[DOMAIN][entry.entry_id] = {"session": session, "coordinators": {}}
    entry_data = hass.data[DOMAIN][entry.entry_id]

    try:
        _LOGGER.info("Fetching Smartcar vehicle IDs...")
        vehicle_list_resp = await session.async_request(
            "get", f"{API_BASE_URL_V2}/vehicles"
        )
        vehicle_list_resp.raise_for_status()
        vehicle_list_data = await vehicle_list_resp.json()
        vehicle_ids = vehicle_list_data.get("vehicles", [])
        _LOGGER.info("Found %d vehicle IDs", len(vehicle_ids))
    except ClientResponseError as err:
        if err.status in (401, 403):
            raise ConfigEntryAuthFailed(
                f"Auth error fetching vehicle list: {err.status}"
            ) from err
        else:
            _LOGGER.exception("HTTP Error fetching vehicle list")
            return False
    except ConfigEntryAuthFailed:
        raise  # Already logged by helper potentially
    except Exception:
        _LOGGER.exception("Unexpected error fetching vehicle list")
        return False

    if not vehicle_ids:
        _LOGGER.warning("No vehicle IDs found.")
        return True

    device_registry = dr.async_get(hass)
    setup_tasks = [
        async_setup_single_vehicle(hass, entry, session, vid, device_registry)
        for vid in vehicle_ids
    ]
    results = await asyncio.gather(*setup_tasks, return_exceptions=True)

    auth_failed = any(
        isinstance(res, ConfigEntryAuthFailed)
        for res in results
        if isinstance(res, Exception)
    )
    any_failed = any(isinstance(res, Exception) for res in results)

    if auth_failed:
        _LOGGER.error("Authentication failed during setup of at least one vehicle.")
        return False
    if any_failed:
        _LOGGER.warning("One or more vehicles failed non-critical setup steps.")
    if not entry_data["coordinators"]:
        _LOGGER.warning("No vehicles were successfully set up.")
        return True

    # Log stored scopes once on successful setup
    stored_token_info = entry.data.get("token")
    if stored_token_info:
        _LOGGER.info("Using token with scopes: %s", stored_token_info.get("scope"))
    else:
        _LOGGER.warning("No token information found in ConfigEntry data!")

    _LOGGER.debug("Forwarding setup to platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


# --- Corrected Function Signature Below ---
async def async_setup_single_vehicle(
    hass: HomeAssistant,
    entry: ConfigEntry,
    session: config_entry_oauth2_flow.OAuth2Session,
    vehicle_id: str,
    device_registry: dr.DeviceRegistry,
) -> None:
    # --- End Corrected Signature ---
    """Set up a single vehicle, register device, create coordinator. Raises exceptions on failure."""
    vin = None
    entry_data = hass.data[DOMAIN][entry.entry_id]
    try:
        # Get VIN (read_vin scope)
        _LOGGER.debug("Fetching VIN for vehicle ID: %s", vehicle_id)
        vin_resp = await session.async_request(
            "get", f"{API_BASE_URL_V2}/vehicles/{vehicle_id}/vin"
        )
        vin_resp.raise_for_status()
        vin_data = await vin_resp.json()
        vin = vin_data.get("vin")
        if not vin:
            raise ValueError("Missing VIN")

        # Get Attributes (read_vehicle_info scope)
        _LOGGER.debug("Fetching attributes for VIN: %s (ID: %s)", vin, vehicle_id)
        attr_resp = await session.async_request(
            "get", f"{API_BASE_URL_V2}/vehicles/{vehicle_id}"
        )
        attr_resp.raise_for_status()
        vehicle_info = await attr_resp.json()
        make = vehicle_info.get("make")
        model = vehicle_info.get("model")
        year = vehicle_info.get("year")

        # Register device
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, vin)},
            manufacturer=make,
            model=f"{model} ({year})" if model and year else model,
            name=f"{make} {model}" if make and model else f"Smartcar {vin[-4:]}",
        )
        _LOGGER.info("Registered device for VIN: %s", vin)

        # Create and Store Coordinator
        coordinator = SmartcarVehicleCoordinator(hass, session, vehicle_id, vin, entry)
        await coordinator.async_config_entry_first_refresh()
        entry_data["coordinators"][vin] = coordinator
        _LOGGER.debug("Coordinator created and initial data fetched for VIN: %s", vin)

    except ClientResponseError as err:
        if err.status in (401, 403):
            raise ConfigEntryAuthFailed(
                f"Auth error [{err.status}] during vehicle setup"
            ) from err
        else:
            raise UpdateFailed(
                f"API error during setup: {err.status}"
            ) from err  # Raise UpdateFailed for non-auth HTTP errors
    except ConfigEntryAuthFailed:
        raise  # Propagate auth failure
    except Exception as err:
        raise err  # Propagate other errors


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Smartcar entry %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _LOGGER.info("Unloaded Smartcar data for entry %s", entry.entry_id)
    return unload_ok
