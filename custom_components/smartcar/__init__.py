from __future__ import annotations

import asyncio
import logging

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.config_entry_oauth2_flow import (
    async_get_config_entry_implementation,
    OAuth2Session,
)

from .coordinator import SmartcarVehicleCoordinator
from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)


@dataclass
class SmartcarData:
    """The Smartcar data."""

    session: OAuth2Session
    coordinators: dict[str, SmartcarVehicleCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smartcar from a config entry."""
    implementation = await async_get_config_entry_implementation(hass, entry)
    session = OAuth2Session(hass, entry, implementation)
    coordinators = {}
    entry.runtime_data = SmartcarData(session=session, coordinators=coordinators)
    device_registry = dr.async_get(hass)

    for vehicle_id, details in entry.data.get("vehicles", {}).items():
        vin = details["vin"]
        make = details.get("make")
        model = details.get("model")
        year = details.get("year")

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
        coordinators[vin] = coordinator
        _LOGGER.debug("Coordinator created and initial data fetched for VIN: %s", vin)

    if not coordinators:
        _LOGGER.warning("No vehicles were successfully set up.")
        return True

    await asyncio.gather(
        *[async_do_first_refresh(coordinator) for coordinator in coordinators.values()]
    )

    # Log stored scopes once on successful setup
    stored_token_info = entry.data.get("token")
    if stored_token_info:
        _LOGGER.info("Using token with scopes: %s", stored_token_info.get("scope"))
    else:
        _LOGGER.warning("No token information found in ConfigEntry data!")

    _LOGGER.debug("Forwarding setup to platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_do_first_refresh(coordinator):
    await coordinator.async_config_entry_first_refresh()
    _LOGGER.debug(
        "Coordinator created and initial data fetched for VIN: %s", coordinator.vin
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Smartcar entry %s", entry.entry_id)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
