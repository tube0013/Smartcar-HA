from dataclasses import dataclass
import logging

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SmartcarVehicleCoordinator
from .entity import SmartcarEntity, SmartcarEntityDescription

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SmartcarSwitchDescription(SwitchEntityDescription, SmartcarEntityDescription):
    """Class describing Smartcar switch entities."""


ENTITY_DESCRIPTIONS: tuple[SwitchEntityDescription, ...] = (
    SmartcarSwitchDescription(
        key="charging",
        name="Charging",
        value_key_path="charge.state",
        value_cast=lambda value: value == "CHARGING",
        icon="mdi:ev-plug-type2",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up switches from coordinator."""
    coordinators: dict[str, SmartcarVehicleCoordinator] = (
        entry.runtime_data.coordinators
    )
    entities = []
    for vin, coordinator in coordinators.items():
        for description in ENTITY_DESCRIPTIONS:
            if coordinator.is_scope_enabled(description.key, verbose=True):
                entities.append(SmartcarChargingSwitch(coordinator, description))
    _LOGGER.info(f"Adding {len(entities)} Smartcar switch entities")
    async_add_entities(entities)


class SmartcarChargingSwitch(SmartcarEntity, SwitchEntity):
    _attr_has_entity_name = True

    @property
    def is_on(self):
        return self._extract_value()

    async def async_turn_on(self, **kwargs):
        if await self._async_send_command("/charge", {"action": "START"}):
            self._inject_raw_value("CHARGING")
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        if await self._async_send_command("/charge", {"action": "STOP"}):
            self._inject_raw_value("NOT_CHARGING")
            self.async_write_ha_state()
