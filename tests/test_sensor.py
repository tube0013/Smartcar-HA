"""Test sensors."""

from dataclasses import dataclass
import datetime as dt
from typing import Any, cast
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_component import async_update_entity
from homeassistant.util.dt import utcnow
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from syrupy.assertion import SnapshotAssertion

from custom_components.smartcar.const import REQUIRED_SCOPES
from custom_components.smartcar.entity import SmartcarEntity

from . import (
    aioclient_mock_append_vehicle_request,
    setup_added_integration,
    setup_integration,
)


@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
async def test_polling_updates(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    snapshot: SnapshotAssertion,
    vehicle: AsyncMock,
    vehicle_fixture: str,
    vehicle_attributes: dict,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test sensors when polling is enabled."""

    entity_id = "sensor.vw_id_4_odometer"
    exepcted_calls = 0

    await setup_integration(hass, mock_config_entry)
    assert entity_registry.async_get(entity_id) == snapshot(
        name="sensor.vw_id_4_odometer-registry"
    )
    assert hass.states.get(entity_id) == snapshot(name=entity_id)

    # check the first refresh based update (a full batch)
    batch_request_mock_call = aioclient_mock.mock_calls[-1]
    assert aioclient_mock.call_count == (exepcted_calls := exepcted_calls + 1)
    assert batch_request_mock_call == snapshot(
        name=f"{entity_id}-api-full-batch-request"
    )

    # tick the clock enough that a polling update would occur if the state was
    # charging (it's not, so there should be no udpdates).
    async_fire_time_changed(hass, utcnow() + dt.timedelta(hours=1))
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == exepcted_calls  # no update should have occurred

    # trigger a polling based update (another full batch update)
    async_fire_time_changed(hass, utcnow() + dt.timedelta(hours=6))
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == (exepcted_calls := exepcted_calls + 1)
    assert aioclient_mock.mock_calls[-1] == batch_request_mock_call

    # trigger an update for a single entity (the batch update should only
    # include a request for the odometer)
    await async_update_entity(hass, entity_id)
    assert aioclient_mock.call_count == (exepcted_calls := exepcted_calls + 1)
    assert aioclient_mock.mock_calls[-1] == snapshot(
        name=f"{entity_id}-api-odometer-request"
    )

    # disable the entity & update it -- this should not result in any api calls
    entity_registry.async_update_entity(
        entity_id, disabled_by=er.RegistryEntryDisabler.USER
    )
    await async_update_entity(hass, entity_id)
    assert aioclient_mock.call_count == exepcted_calls  # no update should have occurred

    # setup response to make the next update result in the vehicle switching to
    # charging state
    exepcted_calls = 0
    aioclient_mock.clear_requests()
    aioclient_mock_append_vehicle_request(
        aioclient_mock,
        "charging",
        vehicle_fixture,
        vehicle_attributes,
    )

    # trigger a polling based update (which should not include the disabled
    # odometer in the request)
    async_fire_time_changed(hass, utcnow() + dt.timedelta(hours=12))
    await hass.async_block_till_done()
    batch_request_without_odometer_mock_call = aioclient_mock.mock_calls[-1]
    assert aioclient_mock.call_count == (exepcted_calls := exepcted_calls + 1)
    assert batch_request_without_odometer_mock_call == snapshot(
        name=f"{entity_id}-api-batch-without-odometer-request"
    )

    # tick the clock enough that a polling update will occur since the state is
    # charging & check the result.
    async_fire_time_changed(hass, utcnow() + dt.timedelta(hours=1))
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == (exepcted_calls := exepcted_calls + 1)
    assert aioclient_mock.mock_calls[-1] == snapshot(
        name=f"{entity_id}-api-batch-without-odometer-request-while-charging"
    )


@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
async def test_update_with_polling_disabled(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    snapshot: SnapshotAssertion,
    vehicle: AsyncMock,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test sensors when polling is disabled."""

    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        pref_disable_polling=True,
    )

    entity_id = "sensor.vw_id_4_odometer"
    exepcted_calls = 0

    await setup_added_integration(hass, mock_config_entry)

    assert entity_registry.async_get(entity_id) == snapshot(
        name="sensor.vw_id_4_odometer-registry"
    )
    assert hass.states.get(entity_id) == snapshot(name=entity_id)

    # no requests should have been made during setup when polling is disabled.
    # this is different from the default behavior, but intended to help reduce
    # excessive api usage.
    assert aioclient_mock.call_count == exepcted_calls

    await async_update_entity(hass, entity_id)

    assert aioclient_mock.call_count == (exepcted_calls := exepcted_calls + 1)
    assert aioclient_mock.mock_calls[-1] == snapshot(
        name=f"{entity_id}-api-odometer-request"
    )

    entity_registry.async_update_entity(
        entity_id, disabled_by=er.RegistryEntryDisabler.USER
    )

    # after another update, no more api calls should have occurred
    await async_update_entity(hass, entity_id)
    assert aioclient_mock.call_count == exepcted_calls


@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
@pytest.mark.parametrize("enabled_scopes", [REQUIRED_SCOPES + ["read_battery"]])
async def test_limited_scopes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    snapshot: SnapshotAssertion,
    vehicle: AsyncMock,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test sensors when only limited scopes are enabled."""

    entity_id = "sensor.vw_id_4_battery"
    exepcted_calls = 0

    await setup_integration(hass, mock_config_entry)
    assert entity_registry.async_get(entity_id) == snapshot(
        name=f"{entity_id}-registry"
    )
    assert hass.states.get(entity_id) == snapshot(name=entity_id)
    assert aioclient_mock.call_count == (exepcted_calls := exepcted_calls + 1)
    assert aioclient_mock.mock_calls[-1] == snapshot(
        name=f"{entity_id}-api-battery-request"
    )


@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
@pytest.mark.parametrize("api_respone_type", ["imperial"])
async def test_unit_conversion(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    snapshot: SnapshotAssertion,
    vehicle: AsyncMock,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test sensors that could return imperial units."""

    entity_id = "sensor.vw_id_4_odometer"
    exepcted_calls = 0

    await setup_integration(hass, mock_config_entry)
    assert entity_registry.async_get(entity_id) == snapshot(
        name=f"{entity_id}-registry"
    )
    assert hass.states.get(entity_id) == snapshot(name=entity_id)

    assert aioclient_mock.call_count == (exepcted_calls := exepcted_calls + 1)
    assert aioclient_mock.mock_calls[-1] == snapshot(
        name=f"{entity_id}-api-full-batch-request"
    )

    await async_update_entity(hass, entity_id)

    assert aioclient_mock.call_count == (exepcted_calls := exepcted_calls + 1)
    assert aioclient_mock.mock_calls[-1] == snapshot(
        name=f"{entity_id}-api-odometer-request"
    )


@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
async def test_restore_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test sensor restore state."""

    entity_id = "sensor.vw_id_4_battery"

    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(
                    entity_id,
                    "34",
                ),
                {
                    "raw_value": 0.34,
                },
            ),
        ),
    )

    # await setup_integration(hass, mock_config_entry)
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        pref_disable_polling=True,
    )

    await setup_added_integration(hass, mock_config_entry)

    state = hass.states.get(entity_id)
    assert state
    assert state.state == "34"


async def test_async_update_internals(
    hass: HomeAssistant,
) -> None:
    """Test that coordinator does not have sensor added during update of a disabled entity."""

    @dataclass(kw_only=True)
    class MockCoordinator:
        vin: str | None = None

    @dataclass(kw_only=True)
    class MockEntityDescription:
        key: str | None = None

    @dataclass(kw_only=True)
    class MockRegistryEntry:
        disabled: bool = False

    coordinator = MockCoordinator()
    description = MockEntityDescription()
    entity = SmartcarEntity(cast(Any, coordinator), description)
    entity.registry_entry = MockRegistryEntry()

    # prove that the failure occurs when enabled
    with pytest.raises(AttributeError) as excinfo:
        await entity.async_update()
    assert excinfo.value.obj == coordinator
    assert excinfo.value.name == "batch_sensor"

    # and then it does not when it's disabled
    entity.registry_entry.disabled = True
    await entity.async_update()
