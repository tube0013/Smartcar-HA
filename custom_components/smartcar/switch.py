from __future__ import annotations

import logging
from aiohttp import ClientResponseError
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN, API_BASE_URL_V2
from .coordinator import SmartcarVehicleCoordinator, SmartcarCoordinatorEntity

_LOGGER = logging.getLogger(__name__)
ENTITY_DESCRIPTIONS: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(key="charging", name="Charging", icon="mdi:ev-plug-type2"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up switches from coordinator."""
    coordinators: dict[str, SmartcarVehicleCoordinator] = (
        entry.runtime_data.coordinators
    )
    session = entry.runtime_data.session
    entities = []
    for vin, coordinator in coordinators.items():
        for description in ENTITY_DESCRIPTIONS:
            if coordinator.is_scope_enabled(description.key, verbose=True):
                entities.append(
                    SmartcarChargingSwitch(coordinator, session, entry, description)
                )
    _LOGGER.info("Adding %d Smartcar switch entities", len(entities))
    async_add_entities(entities)


class SmartcarChargingSwitch(SmartcarCoordinatorEntity, SwitchEntity):
    """Smartcar Charging Control Switch."""

    _attr_has_entity_name = True

    def __init__(self, coord, session, entry, desc):
        super().__init__(coord, desc)
        self.vin = coord.vin
        self.vehicle_id = coord.vehicle_id
        self.session = session
        self.entry = entry
        self.entity_description = desc
        self._attr_unique_id = f"{self.vin}_{desc.key}"
        self._attr_device_info = {"identifiers": {(DOMAIN, self.vin)}}

    @property
    def is_on(self):
        data = self.coordinator.data
        charge = data.get("charge") if data else None
        return charge.get("state") == "CHARGING" if charge else None

    async def _async_send_charge_command(self, action):  # Error handling kept
        _LOGGER.info("Attempting to %s charge for %s", action, self.vin)
        url = f"{API_BASE_URL_V2}/vehicles/{self.vehicle_id}/charge"
        payload = {"action": action}
        try:
            resp = await self.session.async_request("post", url, json=payload)
            resp.raise_for_status()
            _LOGGER.info(
                "%s charge cmd OK for %s", action.capitalize(), self.vin
            )  # Removed early refresh
        except ClientResponseError as e:
            if e.status in (400, 401, 403):
                _LOGGER.warning(
                    "Auth err [%s] sending %s cmd for %s", e.status, action, self.vin
                )
                self.entry.async_start_reauth(self.hass)
            else:
                _LOGGER.error("HTTP err sending %s cmd for %s: %s", action, self.vin, e)
                raise HomeAssistantError(f"API err {e.status}") from e
        except ConfigEntryAuthFailed:
            _LOGGER.warning("AuthFail sending %s cmd for %s", action, self.vin)
            self.entry.async_start_reauth(self.hass)
        except Exception as e:
            _LOGGER.exception("Unexpected err sending %s cmd for %s", action, self.vin)
            raise HomeAssistantError("Unexpected charge err") from e

    async def async_turn_on(self, **kwargs):
        await self._async_send_charge_command("START")

    async def async_turn_off(self, **kwargs):
        await self._async_send_charge_command("STOP")

    @property
    def available(self):
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.get("charge") is not None
        )
