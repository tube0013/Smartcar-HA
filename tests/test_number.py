"""Test number entities."""

from collections.abc import Callable
from unittest.mock import AsyncMock

from aiohttp import ClientResponseError
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from syrupy.assertion import SnapshotAssertion

from . import MOCK_API_ENDPOINT, setup_added_integration, setup_integration

NO_ERROR = None.__class__


@pytest.mark.usefixtures("enable_all_entities")
@pytest.mark.parametrize(
    (
        "api_status",
        "api_status_slug",
        "target_state",
        "expected_state",
        "expected_raises",
        "api_calls",
    ),
    [
        (200, "success", 90, 90, NO_ERROR, 1),
        (409, "unreachable", 90, 80, NO_ERROR, 1),
        (401, "unauthroized", 90, 80, NO_ERROR, 1),
        (500, "server", 90, 80, ClientResponseError, 1),
        (None, None, 40, 80, ServiceValidationError, 0),
        (None, None, 110, 80, ServiceValidationError, 0),
    ],
)
@pytest.mark.parametrize("vehicle_fixture", ["unknown_make"])
async def test_charging_limit(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    snapshot: SnapshotAssertion,
    vehicle: AsyncMock,
    api_status: int,
    api_status_slug: str,
    target_state: int,
    expected_state: int,
    expected_raises: Exception,
    api_calls: int,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test updating charging limit."""

    await setup_integration(hass, mock_config_entry)
    assert len(aioclient_mock.mock_calls) == 1

    aioclient_mock.post(
        f"{MOCK_API_ENDPOINT}/v2.0/vehicles/{vehicle['id']}/charge/limit",
        status=api_status,
        json={
            "message": "Some message related to the action unused by our code",
            "status": api_status_slug,
        },
    )

    try:
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            service_data={ATTR_VALUE: target_state},
            target={ATTR_ENTITY_ID: "number.smartcar_784n_charge_limit"},
            blocking=True,
        )
    except Exception as error:  # noqa: BLE001
        raised_error = error
    else:
        raised_error = None  # type: ignore[assignment]

    number_state = hass.states.get("number.smartcar_784n_charge_limit")
    assert number_state.state == str(expected_state)
    assert isinstance(
        raised_error,
        expected_raises,  # type: ignore[arg-type]
    )

    assert len(aioclient_mock.mock_calls) == 1 + api_calls
    assert [tuple(mock_call) for mock_call in aioclient_mock.mock_calls[1:]] == snapshot


RESTORE_STATE_V2_PARAMETRIZE_ARGS = [
    (
        "entities",
        "expected_coordinator_data",
        "values_sort_key",
    ),
    [
        (
            {
                "number.vw_id_4_charge_limit": {
                    "stored_data": {"raw_value": 0.8},
                    "expected_state": "80",
                },
            },
            {
                "charge-chargelimits": {
                    "values": [{"type": "global", "limit": 0.8, "condition": None}],
                },
            },
            None,
        )
    ],
]

RESTORE_STATE_V2_PARAMETRIZE_IDS = ["is_charging"]


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
