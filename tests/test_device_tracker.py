"""Test device trackers."""

import json
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.const import CONF_WEBHOOK_ID, CONTENT_TYPE_JSON
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.restore_state import STORAGE_KEY as RESTORE_STATE_KEY
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
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
    EntityDescriptionKey,
)

from . import setup_added_integration, setup_integration


@pytest.mark.usefixtures("enable_all_entities")
@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
@pytest.mark.parametrize(
    ("webhook_body", "webhook_headers", "expected"),
    [
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
                                "code": "location-preciselocation",
                                "name": "PreciseLocation",
                                "group": "Location",
                                "body": {
                                    "latitude": 52.238523055555554,
                                    "longitude": 0.15465555555555555,
                                    "heading": 42,
                                },
                                "meta": {
                                    "oemUpdatedAt": 1765227252000,
                                    "retrievedAt": 1765229655488,
                                },
                                "status": {"value": "SUCCESS"},
                            },
                        ],
                    },
                    "triggers": [
                        {
                            "type": "SIGNAL_UPDATED",
                            "signal": "Location.PreciseLocation",
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
    ],
    ids=[
        "vehicle_state",
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


RESTORE_STATE_PARAMETRIZE_ARGS = [
    (
        "entity_id",
        "stored_data",
        "device_tracker_state",
        "coordinator_data",
    ),
    [
        (
            "device_tracker.vw_id_4_location",
            {"raw_value": {"latitude": 37.4292, "longitude": 122.1381}},
            "not_home",
            {"location-preciselocation": {"latitude": 37.4292, "longitude": 122.1381}},
        ),
    ],
]
RESTORE_STATE_PARAMETRIZE_IDS = [
    "location",
]


@pytest.mark.parametrize(
    *RESTORE_STATE_PARAMETRIZE_ARGS,
    ids=RESTORE_STATE_PARAMETRIZE_IDS,
)
@pytest.mark.usefixtures("enable_specified_entities")
@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
@pytest.mark.parametrize(
    "enabled_entities",
    [DEFAULT_ENABLED_ENTITY_DESCRIPTION_KEYS | {EntityDescriptionKey.LOCATION}],
)
async def test_restore_device_tracker_save_state(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
    vehicle_attributes: dict,
    entity_id: str,
    stored_data: dict,
    device_tracker_state: Any,
    coordinator_data: dict,
) -> None:
    """Test saving device tracker/coordinator state."""

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


@pytest.mark.parametrize(
    *RESTORE_STATE_PARAMETRIZE_ARGS,
    ids=RESTORE_STATE_PARAMETRIZE_IDS,
)
@pytest.mark.usefixtures("enable_specified_entities")
@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
@pytest.mark.parametrize(
    "enabled_entities",
    [DEFAULT_ENABLED_ENTITY_DESCRIPTION_KEYS | {EntityDescriptionKey.LOCATION}],
)
async def test_restore_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    vehicle_attributes: dict,
    entity_id: str,
    stored_data: dict,
    device_tracker_state: Any,
    coordinator_data: dict,
) -> None:
    """Test device tracker restore state."""

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
    assert state.state == device_tracker_state
    assert coordinator.data == coordinator_data
