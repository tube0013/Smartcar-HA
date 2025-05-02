# custom_components/smartcar/number.py

import logging; from typing import Any # Shorten imports
from aiohttp import ClientResponseError
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.components.number import (NumberEntity, NumberEntityDescription, NumberMode)
from homeassistant.config_entries import ConfigEntry; from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session
from .const import DOMAIN, API_BASE_URL_V2
from .coordinator import SmartcarVehicleCoordinator

_LOGGER = logging.getLogger(__name__)
ENTITY_DESCRIPTIONS: tuple[NumberEntityDescription,...] = (NumberEntityDescription(key="charge_limit", name="Charge Limit", icon="mdi:battery-charging-80", mode=NumberMode.BOX, native_min_value=50.0, native_max_value=100.0, native_step=1.0, native_unit_of_measurement=PERCENTAGE),)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, SmartcarVehicleCoordinator] = entry_data.get("coordinators", {})
    session = entry_data["session"]
    entities = []
    token_scopes = entry.data.get("token", {}).get("scope", "").split()
    if "control_charge" not in token_scopes: _LOGGER.warning("Missing 'control_charge' scope."); return
    for vin, coordinator in coordinators.items():
        if coordinator.last_update_success and coordinator.data:
            for description in ENTITY_DESCRIPTIONS:
                if description.key == "charge_limit":
                    limit_data = coordinator.data.get("charge_limit")
                    if limit_data is not None and "limit" in limit_data:
                        entities.append(SmartcarChargeLimitNumber(coordinator, session, entry, description))
    _LOGGER.info("Adding %d Smartcar number entities", len(entities))
    async_add_entities(entities)

class SmartcarChargeLimitNumber(CoordinatorEntity[SmartcarVehicleCoordinator], NumberEntity):
    # ... (__init__, native_value, async_set_native_value, available as before) ...
    _attr_has_entity_name = True
    def __init__(self, coord, session, entry, desc): super().__init__(coord); self.vin=coord.vin; self.vehicle_id=coord.vehicle_id; self.session=session; self.entry=entry; self.entity_description=desc; self._attr_unique_id=f"{self.vin}_{desc.key}"; self._attr_device_info={"identifiers":{(DOMAIN,self.vin)}}
    @property
    def native_value(self): data=self.coordinator.data; limit_data=data.get("charge_limit") if data else None; limit_frac=limit_data.get("limit") if limit_data else None; return round(limit_frac*100.0) if limit_frac is not None else None
    async def async_set_native_value(self, value): # Error handling kept
        limit_frac=max(0.5,min(1.0,value/100.0)); _LOGGER.info("Attempting to set charge limit to %.2f%% for %s",value,self.vin); url=f"{API_BASE_URL_V2}/vehicles/{self.vehicle_id}/charge/limit"; payload={"limit":limit_frac}
        try: resp=await self.session.async_request("post",url,json=payload); resp.raise_for_status(); _LOGGER.info("Set charge limit cmd OK for %s",self.vin) # Removed early refresh
        except ClientResponseError as e:
            if e.status in(401,403): _LOGGER.warning("Auth err [%s] setting limit for %s",e.status,self.vin); self.entry.async_start_reauth(self.hass)
            elif e.status==409: _LOGGER.warning("Conflict (409) setting limit for %s.",self.vin); raise HomeAssistantError("Conflict setting limit (plugged in?)") from e
            else: _LOGGER.error("HTTP err setting limit for %s: %s",self.vin,e); raise HomeAssistantError(f"API err {e.status}") from e
        except ConfigEntryAuthFailed as e: _LOGGER.warning("AuthFail setting limit for %s",self.vin); self.entry.async_start_reauth(self.hass)
        except Exception as e: _LOGGER.exception("Unexpected err setting limit for %s",self.vin); raise HomeAssistantError("Unexpected limit err") from e
    @property
    def available(self): return super().available and self.coordinator.data is not None and self.coordinator.data.get("charge_limit") is not None and "limit" in self.coordinator.data["charge_limit"]