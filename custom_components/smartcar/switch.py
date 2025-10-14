from dataclasses import dataclass
import logging

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import EntityDescriptionKey
from .coordinator import SmartcarVehicleCoordinator
from .entity import SmartcarEntity, SmartcarEntityDescription

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SmartcarSwitchDescription(SwitchEntityDescription, SmartcarEntityDescription):
    """Class describing Smartcar switch entities."""


ENTITY_DESCRIPTIONS: tuple[SwitchEntityDescription, ...] = (
    SmartcarSwitchDescription(
        key=EntityDescriptionKey.CHARGING,
        name="Charging",
        value_key_path="charge-ischarging.value",
        icon="mdi:ev-plug-type2",
    ),
)


async def async_setup_entry(  # noqa: RUF029
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches from coordinator."""
    coordinators: dict[str, SmartcarVehicleCoordinator] = (
        entry.runtime_data.coordinators
    )
    entities = [
        SmartcarChargingSwitch(coordinator, description)
        for coordinator in coordinators.values()
        for description in ENTITY_DESCRIPTIONS
        if coordinator.is_scope_enabled(description.key, verbose=True)
    ]
    _LOGGER.info("Adding %s Smartcar switch entities", len(entities))
    async_add_entities(entities)


class SmartcarChargingSwitch(SmartcarEntity[bool, bool], SwitchEntity):
    """Switch entity."""

    _attr_has_entity_name = True

    @property
    def is_on(self) -> bool:
        return self._extract_value()

    async def async_turn_on(
        self,
        **kwargs,  # noqa: ARG002, ANN003
    ) -> None:
        if await self._async_send_command("/charge", {"action": "START"}):
            self._inject_raw_value(value=True)
            self.async_write_ha_state()

    async def async_turn_off(
        self,
        **kwargs,  # noqa: ARG002, ANN003
    ) -> None:
        if await self._async_send_command("/charge", {"action": "STOP"}):
            self._inject_raw_value(value=False)
            self.async_write_ha_state()
