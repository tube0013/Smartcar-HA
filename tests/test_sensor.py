"""Test sensors."""

from collections.abc import Callable
from dataclasses import dataclass
import datetime as dt
import json
from operator import itemgetter
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.const import CONF_WEBHOOK_ID, CONTENT_TYPE_JSON
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_component import async_update_entity
from homeassistant.helpers.restore_state import STORAGE_KEY as RESTORE_STATE_KEY
from homeassistant.util.dt import utcnow
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_restore_state_shutdown_restart,
    mock_restore_cache_with_extra_data,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion

from custom_components.smartcar.const import (
    CONF_APPLICATION_MANAGEMENT_TOKEN,
    DEFAULT_ENABLED_ENTITY_DESCRIPTION_KEYS,
    DOMAIN,
    OAUTH2_TOKEN,
    REQUIRED_SCOPES,
    EntityDescriptionKey,
)
from custom_components.smartcar.coordinator import (
    TIRE_BACK_ROW,
    TIRE_FRONT_ROW,
    TIRE_LEFT_COLUMN,
    TIRE_RIGHT_COLUMN,
)
from custom_components.smartcar.entity import SmartcarEntity
from custom_components.smartcar.sensor import SmartcarSensorDescription

from . import setup_added_integration, setup_integration


@pytest.mark.usefixtures("enable_all_entities")
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
    expected_calls = 0

    await setup_integration(hass, mock_config_entry)
    assert entity_registry.async_get(entity_id) == snapshot(
        name="sensor.vw_id_4_odometer-registry"
    )
    assert hass.states.get(entity_id) == snapshot(name=entity_id)

    # check the first refresh based update (a full batch)
    batch_request_mock_call = aioclient_mock.mock_calls[-1]
    assert aioclient_mock.call_count == (expected_calls := expected_calls + 1)
    assert batch_request_mock_call == snapshot(
        name=f"{entity_id}-api-full-batch-request"
    )

    # trigger a polling based update (another full batch update)
    async_fire_time_changed(hass, utcnow() + dt.timedelta(hours=6))
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == (expected_calls := expected_calls + 1)
    assert aioclient_mock.mock_calls[-1] == batch_request_mock_call

    # trigger an update for a single entity (the batch update should only
    # include a request for the odometer)
    await async_update_entity(hass, entity_id)
    assert aioclient_mock.call_count == (expected_calls := expected_calls + 1)
    assert aioclient_mock.mock_calls[-1] == snapshot(
        name=f"{entity_id}-api-odometer-request"
    )

    # disable the entity & update it -- this should not result in any api calls
    entity_registry.async_update_entity(
        entity_id, disabled_by=er.RegistryEntryDisabler.USER
    )
    await async_update_entity(hass, entity_id)
    assert aioclient_mock.call_count == expected_calls  # no update should have occurred

    # trigger a polling based update (which should not include the disabled
    # odometer in the request)
    async_fire_time_changed(hass, utcnow() + dt.timedelta(hours=12))
    await hass.async_block_till_done()
    batch_request_without_odometer_mock_call = aioclient_mock.mock_calls[-1]
    assert aioclient_mock.call_count == (expected_calls := expected_calls + 1)
    assert batch_request_without_odometer_mock_call == snapshot(
        name=f"{entity_id}-api-batch-without-odometer-request"
    )


@pytest.mark.usefixtures("enable_all_entities")
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
    expected_calls = 0

    await setup_added_integration(hass, mock_config_entry)

    assert entity_registry.async_get(entity_id) == snapshot(
        name="sensor.vw_id_4_odometer-registry"
    )
    assert hass.states.get(entity_id) == snapshot(name=entity_id)

    # no requests should have been made during setup when polling is disabled.
    # this is different from the default behavior, but intended to help reduce
    # excessive api usage.
    assert aioclient_mock.call_count == expected_calls

    await async_update_entity(hass, entity_id)

    assert aioclient_mock.call_count == (expected_calls := expected_calls + 1)
    assert aioclient_mock.mock_calls[-1] == snapshot(
        name=f"{entity_id}-api-odometer-request"
    )

    entity_registry.async_update_entity(
        entity_id, disabled_by=er.RegistryEntryDisabler.USER
    )

    # after another update, no more api calls should have occurred
    await async_update_entity(hass, entity_id)
    assert aioclient_mock.call_count == expected_calls


@pytest.mark.usefixtures("enable_all_entities")
@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
@pytest.mark.parametrize(
    ("webhook_body", "webhook_headers", "expected"),
    [
        (
            json.dumps({"eventType": "VERIFY", "data": {"challenge": "any-abcd"}}),
            {},
            {
                "response": {
                    "challenge": "1234",  # from mock_hmac_sha256_hexdigest
                }
            },
        ),
        (
            json.dumps(
                {
                    "eventId": "1821c036-71cb-408f-8dee-2989b9764307",
                    "eventType": "VEHICLE_STATE",
                    "data": {
                        "user": {"id": "2fbd0033-83e7-43b8-a367-776d6dff1134"},
                        "vehicle": {
                            "id": "a1d50709-3502-4faa-ba43-a5c7565e6a09",
                            "make": "VOLKSWAGEN",
                            "model": "ID.4",
                            "year": 2021,
                        },
                        "signals": [
                            {
                                "code": "connectivitystatus-isonline",
                                "name": "IsOnline",
                                "group": "ConnectivityStatus",
                                "status": {
                                    "value": "ERROR",
                                    "error": {
                                        "type": "COMPATIBILITY",
                                        "code": "VEHICLE_NOT_CAPABLE",
                                    },
                                },
                            },
                            {
                                "code": "odometer-traveleddistance",
                                "name": "TraveledDistance",
                                "group": "Odometer",
                                "body": {"value": 62041, "unit": "km"},
                                "meta": {
                                    "oemUpdatedAt": 1758238176603,
                                    "retrievedAt": 1758238782829,
                                },
                            },
                            {
                                "code": "closure-islocked",
                                "name": "IsLocked",
                                "group": "Closure",
                                "status": {
                                    "value": "ERROR",
                                    "error": {"type": "PERMISSION", "code": None},
                                },
                            },
                            {
                                "code": "internalcombustionengine-fuellevel",
                                "name": "FuelLevel",
                                "group": "InternalCombustionEngine",
                                "status": {
                                    "value": "ERROR",
                                    "error": {
                                        "type": "COMPATIBILITY",
                                        "code": "VEHICLE_NOT_CAPABLE",
                                    },
                                },
                            },
                            {
                                "code": "tractionbattery-stateofcharge",
                                "name": "StateOfCharge",
                                "group": "TractionBattery",
                                "body": {"value": 42, "unit": "percent"},
                                "meta": {
                                    "oemUpdatedAt": 1758238233000,
                                    "retrievedAt": 1758238783086,
                                },
                            },
                            {
                                "code": "tractionbattery-range",
                                "name": "Range",
                                "group": "TractionBattery",
                                "status": {
                                    "value": "ERROR",
                                    "error": {
                                        "type": "COMPATIBILITY",
                                        "code": "VEHICLE_NOT_CAPABLE",
                                    },
                                },
                            },
                            {
                                "code": "charge-chargelimits",
                                "name": "ChargeLimits",
                                "group": "Charge",
                                "body": {
                                    "values": [
                                        {
                                            "type": "GLOBAL",
                                            "limit": 80,
                                            "condition": None,
                                        }
                                    ],
                                    "activeLimit": 80,
                                    "unit": "percent",
                                },
                                "meta": {
                                    "oemUpdatedAt": 1758238232000,
                                    "retrievedAt": 1758238783086,
                                },
                            },
                            {
                                "code": "charge-ischarging",
                                "name": "IsCharging",
                                "group": "Charge",
                                "body": {"value": False},
                                "meta": {
                                    # empty meta just to cover all
                                    # possibilities, but this will likely never
                                    # be empty.
                                },
                            },
                        ],
                    },
                    "triggers": [
                        {
                            "type": "SIGNAL_UPDATED",
                            "signal": "Odometer.TraveledDistance",
                        },
                        {
                            "type": "SIGNAL_UPDATED",
                            "signal": "TractionBattery.StateOfCharge",
                        },
                    ],
                    "meta": {
                        "deliveryId": "682541b6-a461-4d69-9e6e-fead3832f5eb",
                        "deliveredAt": 1758238783185,
                        "deliveryTime": 1758238783185,
                    },
                }
            ),
            {
                "sc-signature": "1234",
            },
            {
                "log_messages": [
                    "error for signal FuelLevel: COMPATIBILITY:VEHICLE_NOT_CAPABLE"
                ],
            },
        ),
        (
            json.dumps(
                {
                    "eventId": "1821c036-71cb-408f-8dee-2989b9764307",
                    "eventType": "VEHICLE_STATE",
                    "data": {
                        "user": {"id": "2fbd0033-83e7-43b8-a367-776d6dff1134"},
                        "vehicle": {
                            "id": "a1d50709-3502-4faa-ba43-a5c7565e6a09",
                            "make": "BMW",
                            "model": "118i",
                            "year": 2025,
                        },
                        "signals": [
                            {
                                "code": "internalcombustionengine-fuellevel",
                                "name": "FuelLevel",
                                "group": "InternalCombustionEngine",
                                "body": {"value": 0.77},
                                "meta": {
                                    "oemUpdatedAt": 1758238233000,
                                    "retrievedAt": 1758238783086,
                                },
                            },
                            {
                                "code": "internalcombustionengine-range",
                                "name": "FuelLevel",
                                "group": "InternalCombustionEngine",
                                "body": {"value": 239},
                                "meta": {
                                    "oemUpdatedAt": 1758238233000,
                                    "retrievedAt": 1758238783086,
                                },
                            },
                        ],
                    },
                    "triggers": [
                        {
                            "type": "SIGNAL_UPDATED",
                            "signal": "InternalCombustionEngine.FuelLevel",
                        },
                    ],
                    "meta": {
                        "deliveryId": "682541b6-a461-4d69-9e6e-fead3832f5eb",
                        "deliveredAt": 1758238783185,
                        "deliveryTime": 1758238783185,
                    },
                }
            ),
            {
                "sc-signature": "1234",
            },
            {},
        ),
        (
            json.dumps(
                {
                    "eventId": "1821c036-71cb-408f-8dee-2989b9764307",
                    "eventType": "VEHICLE_STATE",
                    "data": {
                        "user": {"id": "2fbd0033-83e7-43b8-a367-776d6dff1134"},
                        "vehicle": {
                            "id": "70076e4a-d774-464c-8241-60de654ccb24",
                            "make": "Hyundai",
                            "model": "IONIQ 5",
                            "year": 2023,
                        },
                        "signals": [],
                    },
                }
            ),
            {
                "sc-signature": "1234",
            },
            {
                "response_status": 404,
                "response": "",
                "log_messages": [
                    "unknown vehicle with id: 70076e4a-d774-464c-8241-60de654ccb24, vin: unknown"
                ],
            },
        ),
        (
            json.dumps(
                {
                    "eventId": "1821c036-71cb-408f-8dee-2989b9764307",
                    "eventType": "VEHICLE_ERROR",
                    "data": {
                        "user": {"id": "2fbd0033-83e7-43b8-a367-776d6dff1134"},
                        "vehicle": {
                            "id": "a1d50709-3502-4faa-ba43-a5c7565e6a09",
                            "make": "VOLKSWAGEN",
                            "model": "ID.4",
                            "year": 2021,
                        },
                        "errors": [
                            {
                                "type": "COMPATIBILITY",
                                "code": "VEHICLE_NOT_CAPABLE",
                                "description": "The vehicle is incapable of performing your request.",
                                "docURL": "https://smartcar.com/docs/errors/api-errors/compatibility-errors#vehicle-not-capable",
                                "resolution": {"type": None},
                                "suggestedUserMessage": "Your car is unable to perform this request.",
                                "state": "ERROR",
                                "signals": [
                                    "VehicleIdentification.Nickname",
                                    "VehicleUserAccount.Role",
                                    "VehicleUserAccount.Permissions",
                                    "ConnectivitySoftware.CurrentFirmwareVersion",
                                    "ConnectivityStatus.IsOnline",
                                    "ConnectivityStatus.IsAsleep",
                                    "ConnectivityStatus.IsDigitalKeyPaired",
                                    "InternalCombustionEngine.FuelLevel",
                                ],
                            },
                            {
                                "type": "PERMISSION",
                                "code": None,
                                "description": "Your application has insufficient permissions to access the requested resource. Please prompt the user to re-authenticate using Smartcar Connect.",
                                "docURL": "https://smartcar.com/docs/errors/api-errors/permission-errors#null",
                                "resolution": {"type": "REAUTHENTICATE"},
                                "state": "ERROR",
                                "signals": ["Closure.IsLocked"],
                            },
                        ],
                    },
                    "meta": {
                        "deliveryId": "49c3f6bb-63cf-47ce-b320-6e0aaa9a2ca7",
                        "deliveredAt": 1758224204078,
                        "deliveryTime": 1758224204078,
                    },
                }
            ),
            {
                "sc-signature": "1234",
            },
            {
                "reauth_calls": 1,
                "log_messages": ["ignoring error", "requesting reauth"],
            },
        ),
        (
            "invalid-json",
            {
                "sc-signature": "1234",
            },
            {"log_messages": ["invalid JSON"]},
        ),
        (
            json.dumps({}),
            {"sc-signature": "invalid-4321"},
            {
                "response_status": 404,
                "response": "",
                "log_messages": ["invalid signature"],
            },
        ),
    ],
    ids=[
        "verify",
        "vehicle_state",
        "vehicle_state_fuel",
        "vehicle_mismatch",
        "vehicle_error",
        "invalid_json",
        "invalid_signature",
    ],
)
async def test_webhook_update(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_hmac_sha256_hexdigest: Mock,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    snapshot: SnapshotAssertion,
    vehicle: AsyncMock,
    vehicle_fixture: str,
    vehicle_attributes: dict,
    webhook_body: str,
    webhook_headers: dict[str, Any],
    expected: dict[str, Any],
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={
            **mock_config_entry.data,
            CONF_WEBHOOK_ID: "smartcar_test",
            CONF_APPLICATION_MANAGEMENT_TOKEN: "test_amt",
        },
    )

    expected_calls = 0
    expected_response = expected.get("response", {})
    expected_response_status = expected.get("response_status", 200)
    expected_reauth_calls = expected.get("reauth_calls", 0)
    expected_log_messages = expected.get("log_messages", [])

    await setup_added_integration(hass, mock_config_entry)

    # no requests should have been made during setup when webhooks are enabled
    # because this automatically disables polling.
    assert aioclient_mock.call_count == expected_calls

    with patch(
        "homeassistant.config_entries.ConfigEntry.async_start_reauth"
    ) as mock_start_reauth:
        client = await hass_client()
        resp = await client.post(
            "/api/webhook/smartcar_test",
            data=webhook_body,
            headers={
                "content-type": CONTENT_TYPE_JSON,
                **webhook_headers,
            },
        )
        assert resp.status == expected_response_status
        assert (
            await (resp.json() if expected_response_status < 300 else resp.text())
            == expected_response
        )
        await hass.async_block_till_done()

    # still no calls since webhooks will update from the data it received
    assert aioclient_mock.call_count == expected_calls
    assert mock_start_reauth.call_count == expected_reauth_calls

    device_id = vehicle["vin"]
    device = device_registry.async_get_device({(DOMAIN, device_id)})
    entities = entity_registry.entities.get_entries_for_device_id(device.id)

    for entity in entities:
        assert hass.states.get(entity.entity_id) == snapshot(name=entity.entity_id)

    for expected_log_message in expected_log_messages:
        assert expected_log_message in caplog.text


@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
@pytest.mark.parametrize("enabled_scopes", [[*REQUIRED_SCOPES, "read_battery"]])
@pytest.mark.parametrize(
    "enabled_entities",
    [DEFAULT_ENABLED_ENTITY_DESCRIPTION_KEYS | {EntityDescriptionKey.BATTERY_CAPACITY}],
)
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
    expected_calls = 0

    await setup_integration(hass, mock_config_entry)
    assert entity_registry.async_get(entity_id) == snapshot(
        name=f"{entity_id}-registry"
    )
    assert hass.states.get(entity_id) == snapshot(name=entity_id)
    assert aioclient_mock.call_count == (expected_calls := expected_calls + 1)
    assert aioclient_mock.mock_calls[-1] == snapshot(
        name=f"{entity_id}-api-battery-request"
    )


@pytest.mark.usefixtures("enable_all_entities")
@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
@pytest.mark.parametrize("api_response_type", ["imperial"])
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
    expected_calls = 0

    await setup_integration(hass, mock_config_entry)
    assert entity_registry.async_get(entity_id) == snapshot(
        name=f"{entity_id}-registry"
    )
    assert hass.states.get(entity_id) == snapshot(name=entity_id)

    assert aioclient_mock.call_count == (expected_calls := expected_calls + 1)
    assert aioclient_mock.mock_calls[-1] == snapshot(
        name=f"{entity_id}-api-full-batch-request"
    )

    await async_update_entity(hass, entity_id)

    assert aioclient_mock.call_count == (expected_calls := expected_calls + 1)
    assert aioclient_mock.mock_calls[-1] == snapshot(
        name=f"{entity_id}-api-odometer-request"
    )


@pytest.mark.usefixtures("enable_all_entities")
@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
@pytest.mark.parametrize("expires_at", [1756764425])
@pytest.mark.parametrize("api_response_type", ["unauthorized"])
async def test_expired_token_update_with_polling_disabled(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    snapshot: SnapshotAssertion,
    vehicle: AsyncMock,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test update for expired token when polling is disabled."""

    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        pref_disable_polling=True,
    )

    aioclient_mock.post(
        OAUTH2_TOKEN,
        status=400,
        json={
            "error": "invalid_grant",
            "error_description": "Invalid or expired refresh token.",
        },
    )

    await setup_added_integration(hass, mock_config_entry)

    assert len(hass.config_entries.flow.async_progress()) == 0
    await async_update_entity(hass, "sensor.vw_id_4_battery")
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["step_id"] == "reauth_confirm"
    assert flows[0]["context"]["source"] == "reauth"


@pytest.mark.usefixtures("enable_all_entities")
@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
@pytest.mark.parametrize("expires_at", [1756764425])
@pytest.mark.parametrize("api_response_type", ["unauthorized"])
async def test_expired_token_invalid_update_with_polling_disabled(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    snapshot: SnapshotAssertion,
    vehicle: AsyncMock,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test update for expired token when polling is disabled."""

    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        pref_disable_polling=True,
    )

    aioclient_mock.post(
        OAUTH2_TOKEN,
        status=500,
        json={
            "error": "server_error",
            "error_description": "A server error occurred.",
        },
    )

    await setup_added_integration(hass, mock_config_entry)

    assert len(hass.config_entries.flow.async_progress()) == 0
    await async_update_entity(hass, "sensor.vw_id_4_battery")
    await hass.async_block_till_done()
    assert len(hass.config_entries.flow.async_progress()) == 0


RESTORE_STATE_PARAMETRIZE_ARGS = [
    (
        "entity_id",
        "stored_data",
        "sensor_state",
        "coordinator_data",
    ),
    [
        (
            "sensor.vw_id_4_battery",
            {"raw_value": 0.34},
            "34",
            {"tractionbattery-stateofcharge": {"value": 0.34}},
        ),
        (
            "sensor.vw_id_4_range",
            {"raw_value": 45.2, "unit_system": "imperial"},
            "72.7423488",
            {
                "tractionbattery-range": {"value": 45.2},
                "tractionbattery-range:unit_system": "imperial",
            },
        ),
        (
            "sensor.vw_id_4_range",
            {
                "raw_value": 45.2,
                "data_age": "2025-05-29T19:47:32+00:00",
                "fetched_at": "2025-05-29T20:09:57+00:00",
            },
            "45.2",
            {
                "tractionbattery-range": {"value": 45.2},
                "tractionbattery-range:data_age": dt.datetime(
                    2025, 5, 29, 19, 47, 32, tzinfo=dt.UTC
                ),
                "tractionbattery-range:fetched_at": dt.datetime(
                    2025, 5, 29, 20, 9, 57, tzinfo=dt.UTC
                ),
            },
        ),
        (
            "sensor.vw_id_4_tire_pressure_front_right",
            {
                "raw_value": [
                    {
                        "column": TIRE_RIGHT_COLUMN,
                        "row": TIRE_FRONT_ROW,
                        "tirePressure": 234,
                    },
                ],
            },
            "234",
            {
                "wheel-tires": {
                    "values": [
                        {
                            "column": TIRE_RIGHT_COLUMN,
                            "row": TIRE_FRONT_ROW,
                            "tirePressure": 234,
                        },
                    ],
                },
            },
        ),
    ],
]
RESTORE_STATE_PARAMETRIZE_IDS = [
    "value_only",
    "value_and_unit_system",
    "value_and_timestamps",
    "value_complex",
]


@pytest.mark.usefixtures("enable_all_entities")
@pytest.mark.parametrize(
    *RESTORE_STATE_PARAMETRIZE_ARGS,
    ids=RESTORE_STATE_PARAMETRIZE_IDS,
)
@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
async def test_restore_sensor_save_state(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
    vehicle_attributes: dict,
    entity_id: str,
    stored_data: dict,
    sensor_state: Any,
    coordinator_data: dict,
) -> None:
    """Test saving sensor/coordinator state."""

    await setup_integration(hass, mock_config_entry)

    coordinator = mock_config_entry.runtime_data.coordinators[vehicle_attributes["vin"]]
    coordinator.data = coordinator_data

    await async_mock_restore_state_shutdown_restart(hass)  # trigger saving state

    stored_entity_data = [
        item["extra_data"]
        for item in hass_storage[RESTORE_STATE_KEY]["data"]
        if item["state"]["entity_id"] == entity_id
    ]

    assert stored_entity_data[0] == stored_data
    assert stored_entity_data == snapshot


@pytest.mark.usefixtures("enable_all_entities")
@pytest.mark.parametrize(
    *RESTORE_STATE_PARAMETRIZE_ARGS,
    ids=RESTORE_STATE_PARAMETRIZE_IDS,
)
@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
async def test_restore_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    vehicle_attributes: dict,
    entity_id: str,
    stored_data: dict,
    sensor_state: Any,
    coordinator_data: dict,
) -> None:
    """Test sensor restore state."""

    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(
                    entity_id,
                    "does-not-matter-for-this-test",
                ),
                stored_data,
            ),
        ),
    )

    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        pref_disable_polling=True,
    )

    await setup_added_integration(hass, mock_config_entry)

    coordinator = mock_config_entry.runtime_data.coordinators[vehicle_attributes["vin"]]
    state = hass.states.get(entity_id)
    assert state
    assert state.state == sensor_state
    assert coordinator.data == coordinator_data


RESTORE_STATE_V2_PARAMETRIZE_ARGS = [
    (
        "entities",
        "expected_coordinator_data",
        "values_sort_key",
    ),
    [
        (
            {
                "sensor.vw_id_4_tire_pressure_front_left": {
                    "stored_data": {"raw_value": 235},
                    "expected_state": "235",
                },
                "sensor.vw_id_4_tire_pressure_back_left": {
                    "stored_data": {"raw_value": 234},
                    "expected_state": "234",
                },
                "sensor.vw_id_4_tire_pressure_front_right": {
                    "stored_data": {"raw_value": 233},
                    "expected_state": "233",
                },
                "sensor.vw_id_4_tire_pressure_back_right": {
                    "stored_data": {"raw_value": 232},
                    "expected_state": "232",
                },
            },
            {
                "wheel-tires": {
                    "columnCount": 2,
                    "rowCount": 2,
                    "values": [
                        {
                            "column": TIRE_LEFT_COLUMN,
                            "row": TIRE_FRONT_ROW,
                            "tirePressure": 235,
                        },
                        {
                            "column": TIRE_LEFT_COLUMN,
                            "row": TIRE_BACK_ROW,
                            "tirePressure": 234,
                        },
                        {
                            "column": TIRE_RIGHT_COLUMN,
                            "row": TIRE_FRONT_ROW,
                            "tirePressure": 233,
                        },
                        {
                            "column": TIRE_RIGHT_COLUMN,
                            "row": TIRE_BACK_ROW,
                            "tirePressure": 232,
                        },
                    ],
                },
            },
            itemgetter("column", "row"),
        )
    ],
]

RESTORE_STATE_V2_PARAMETRIZE_IDS = ["tire_pressures"]


@pytest.mark.usefixtures("enable_all_entities")
@pytest.mark.parametrize(
    *RESTORE_STATE_V2_PARAMETRIZE_ARGS,
    ids=RESTORE_STATE_V2_PARAMETRIZE_IDS,
)
@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
async def test_restore_state_from_v2(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    vehicle_attributes: dict,
    entities: dict,
    expected_coordinator_data: dict,
    values_sort_key: Callable[[dict], tuple] | None,
) -> None:
    """Test sensor restore state."""

    mock_restore_cache_with_extra_data(
        hass,
        tuple(
            (
                State(
                    entity_id,
                    "does-not-matter-for-this-test",
                ),
                entity_config["stored_data"],
            )
            for entity_id, entity_config in entities.items()
        ),
    )

    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        pref_disable_polling=True,
    )

    await setup_added_integration(hass, mock_config_entry)

    coordinator = mock_config_entry.runtime_data.coordinators[vehicle_attributes["vin"]]

    coordinator_data = {
        key: data
        | (
            {"values": sorted(data["values"], key=values_sort_key)}
            if values_sort_key and "values" in data
            else {}
        )
        for key, data in coordinator.data.items()
    }

    assert coordinator_data == expected_coordinator_data

    for entity_id, entity_config in entities.items():
        state = hass.states.get(entity_id)
        assert state
        assert state.state == entity_config["expected_state"]


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
    entity = SmartcarEntity[float, float](cast("Any", coordinator), description)
    entity.registry_entry = MockRegistryEntry()

    # prove that the failure occurs when enabled
    with pytest.raises(AttributeError) as excinfo:
        await entity.async_update()
    assert excinfo.value.obj == coordinator
    assert excinfo.value.name == "batch_sensor"

    # and then it does not when it's disabled
    entity.registry_entry.disabled = True
    await entity.async_update()


def test_entity_registry_enabled_default_readonly(
    hass: HomeAssistant,
) -> None:
    """Test entity_registry_enabled_default is readonly."""

    with pytest.raises(AttributeError) as excinfo:
        SmartcarSensorDescription(
            key="mock_description",
            value_key_path="mock_path",
            entity_registry_enabled_default=False,
        )

    assert (
        excinfo.value.args[0]
        == "readonly; configure via smartcar.const.DEFAULT_ENABLED_ENTITY_DESCRIPTION_KEYS"
    )
