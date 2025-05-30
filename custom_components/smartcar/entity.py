from collections.abc import Callable
from functools import reduce
from http import HTTPStatus
import logging
from typing import Any

from aiohttp import ClientResponseError
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.restore_state import (
    ExtraStoredData,
    RestoredExtraData,
    RestoreEntity,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmartcarVehicleCoordinator

_LOGGER = logging.getLogger(__name__)

ERROR_STATUS_VEHICLE_STATE = 409
ERROR_STATUS_RATE_LIMIT = 429
ERROR_STATUS_BILLING = 430
ERROR_STATUS_COMPATIBILITY = 501
ERROR_STATUS_UPSTREAM = 502


class SmartcarEntity(CoordinatorEntity[SmartcarVehicleCoordinator], RestoreEntity):
    def __init__(
        self, coordinator: SmartcarVehicleCoordinator, description: EntityDescription
    ):
        super().__init__(coordinator)
        self.vin = coordinator.vin
        self.entity_description = description
        self._attr_unique_id = f"{self.vin}_{description.key}"
        self._attr_device_info = {"identifiers": {(DOMAIN, self.vin)}}

    @property
    def available(self):
        return super().available and self._extract_value() is not None

    async def async_update(self) -> None:
        if not self.enabled:
            return

        self.coordinator.batch_sensor(self)

        await super().async_update()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        if (
            (last_state := await self.async_get_last_state()) is not None
            and last_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
            and (extra_data := await self.async_get_last_extra_data()) is not None
            and (extra_data_dict := extra_data.as_dict())
            and (extra_data_raw_value := extra_data_dict.get("raw_value")) is not None
            and not self.available
        ):
            extra_data_dict.pop("raw_value")

            self._inject_raw_value(extra_data_raw_value, extra_data_dict)

    @property
    def extra_restore_state_data(self) -> ExtraStoredData | None:
        data = {"raw_value": self._extract_raw_value()}

        if unit_system := self._extract_unit_system():
            data["unit_system"] = unit_system

        return RestoredExtraData(data)

    def _extract_unit_system(self) -> Any:
        data = self.coordinator.data or {}
        description = self.entity_description
        key_path = description.value_key_path.split(".")
        return data.get(f"{key_path[0]}:unit_system")

    def _extract_raw_value(self) -> Any:
        data = self.coordinator.data or {}
        description = self.entity_description
        key_path = description.value_key_path.split(".")
        value = reduce(lambda v, key: v.get(key) if v else None, key_path, data)

        return value

    def _extract_value(self) -> Any:
        description = self.entity_description
        unit_system = self._extract_unit_system()
        value = self._extract_raw_value()
        value = description.value_cast(value)

        if (
            value is not None
            and unit_system == "imperial"
            and (imperial_conversion := self.entity_description.imperial_conversion)
        ):
            value = imperial_conversion(value)

        return value

    def _inject_raw_value(self, value, extra_data: dict = {}) -> None:
        coordinator = self.coordinator
        if coordinator.data is None:
            coordinator.data = {}
        data = coordinator.data
        description = self.entity_description
        key_path = description.value_key_path.split(".")
        obj_path = key_path[:-1]
        key = key_path[-1]
        obj = reduce(
            lambda v, key: v.setdefault(key, {}) if v is not None else None,
            obj_path,
            data,
        )
        obj[key] = value

        if unit_system := extra_data.get("unit_system"):
            data[f"{key_path[0]}:unit_system"] = unit_system

    async def _async_send_command(
        self, subpath, payload, *, method="post", version="2.0", **kwargs
    ):
        _LOGGER.info(f"Sending {subpath} request for {self.vin}")
        success = False

        try:
            resp = await self.coordinator.auth.request(
                method,
                f"vehicles/{self.coordinator.vehicle_id}{subpath}",
                version=version,
                json=payload,
            )
            resp.raise_for_status()
            success = True
        except ClientResponseError as err:
            if err.status in (HTTPStatus.UNAUTHORIZED,):
                _LOGGER.warning(
                    f"Auth error {err.status} sending {subpath} request for {self.vin}"
                )
                self.coordinator.config_entry.async_start_reauth(self.hass)
            elif err.status in (
                ERROR_STATUS_VEHICLE_STATE,
                ERROR_STATUS_RATE_LIMIT,
                ERROR_STATUS_BILLING,
                ERROR_STATUS_COMPATIBILITY,
                ERROR_STATUS_UPSTREAM,
            ):
                pass
            else:
                raise err

        return success


class SmartcarEntityDescription(EntityDescription):
    """Class describing Smartcar sensor entities."""

    value_key_path: str
    value_cast: Callable[[Any], Any] = lambda x: x
    imperial_conversion: Callable[[float], float] | None = None
