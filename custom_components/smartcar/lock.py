from __future__ import annotations

import logging
from aiohttp import ClientResponseError
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN, API_BASE_URL_V1  # Uses V1 for POST
from .coordinator import SmartcarVehicleCoordinator, SmartcarCoordinatorEntity

_LOGGER = logging.getLogger(__name__)
ENTITY_DESCRIPTIONS: tuple[LockEntityDescription, ...] = (
    LockEntityDescription(key="door_lock", name="Door Lock"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators: dict[str, SmartcarVehicleCoordinator] = (
        entry.runtime_data.coordinators
    )
    session = entry.runtime_data.session
    entities = []
    for vin, coordinator in coordinators.items():
        for description in ENTITY_DESCRIPTIONS:
            if coordinator.is_scope_enabled(description.key, verbose=True):
                entities.append(
                    SmartcarDoorLock(coordinator, session, entry, description)
                )
    _LOGGER.info("Adding %d Smartcar lock entities", len(entities))
    async_add_entities(entities)


class SmartcarDoorLock(SmartcarCoordinatorEntity, LockEntity):
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
    def is_locked(self):
        data = self.coordinator.data
        lock_data = data.get("lock_status") if data else None
        return lock_data.get("isLocked") if lock_data else None

    async def _async_send_lock_command(self, action):  # Error handling kept
        _LOGGER.info("Attempting to %s doors for %s", action, self.vin)
        url = f"{API_BASE_URL_V1}/vehicles/{self.vehicle_id}/security"
        payload = {"action": action}
        try:
            resp = await self.session.async_request("post", url, json=payload)
            resp.raise_for_status()
            _LOGGER.info(
                "%s cmd OK for %s", action.capitalize(), self.vin
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
            raise HomeAssistantError("Unexpected lock err") from e

    async def async_lock(self, **kwargs):
        await self._async_send_lock_command("LOCK")

    async def async_unlock(self, **kwargs):
        await self._async_send_lock_command("UNLOCK")

    @property
    def available(self):
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.get("lock_status") is not None
            and "isLocked" in self.coordinator.data["lock_status"]
        )
