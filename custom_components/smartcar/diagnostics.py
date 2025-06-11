"""Diagnostics support for Smartcar."""

from typing import Any, cast

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
)
from homeassistant.core import HomeAssistant

from .coordinator import SmartcarVehicleCoordinator

CONF_REFRESH_TOKEN = "refresh_token"  # noqa: S105
CONF_VIN = "vin"

TO_REDACT = {
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_VIN,
}


async def async_get_config_entry_diagnostics(  # noqa: RUF029
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinators: dict[str, SmartcarVehicleCoordinator] = (
        entry.runtime_data.coordinators
    )

    return cast(
        "dict[str, Any]",
        async_redact_data(
            {
                "entry": entry.as_dict(),
                "data": {
                    coordinator_name: coordinator.data
                    for coordinator_name, coordinator in coordinators.items()
                },
            },
            TO_REDACT,
        ),
    )
