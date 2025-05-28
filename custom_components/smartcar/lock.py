from dataclasses import dataclass
import logging

from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import EntityDescriptionKey
from .coordinator import SmartcarVehicleCoordinator
from .entity import SmartcarEntity, SmartcarEntityDescription

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SmartcarLockDescription(LockEntityDescription, SmartcarEntityDescription):
    """Class describing Smartcar lock entities."""


ENTITY_DESCRIPTIONS: tuple[LockEntityDescription, ...] = (
    SmartcarLockDescription(
        key=EntityDescriptionKey.DOOR_LOCK,
        name="Door Lock",
        value_key_path="security.isLocked",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators: dict[str, SmartcarVehicleCoordinator] = (
        entry.runtime_data.coordinators
    )
    entities = []
    for vin, coordinator in coordinators.items():
        for description in ENTITY_DESCRIPTIONS:
            if coordinator.is_scope_enabled(description.key, verbose=True):
                entities.append(SmartcarDoorLock(coordinator, description))
    _LOGGER.info(f"Adding {len(entities)} Smartcar lock entities")
    async_add_entities(entities)


class SmartcarDoorLock(SmartcarEntity, LockEntity):
    _attr_has_entity_name = True

    @property
    def is_locked(self):
        return self._extract_value()

    async def async_lock(self, **kwargs):
        if await self._async_send_command("/security", {"action": "LOCK"}):
            self._inject_raw_value(True)
            self.async_write_ha_state()

    async def async_unlock(self, **kwargs):
        if await self._async_send_command("/security", {"action": "UNLOCK"}):
            self._inject_raw_value(False)
            self.async_write_ha_state()
