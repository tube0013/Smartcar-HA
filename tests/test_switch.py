"""Test switch entities."""

from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock

from aiohttp import ClientResponseError
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant, State
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from syrupy.assertion import SnapshotAssertion

from . import MOCK_API_ENDPOINT, setup_added_integration, setup_integration

NO_ERROR = None.__class__


@pytest.mark.parametrize(
    (
        "service_action",
        "api_status",
        "api_status_slug",
        "expected_state",
        "expected_raises",
    ),
    [
        (SERVICE_TURN_ON, 200, "success", STATE_ON, NO_ERROR),
        (SERVICE_TURN_OFF, 200, "success", STATE_OFF, NO_ERROR),
        (SERVICE_TURN_ON, 409, "unreachable", STATE_OFF, NO_ERROR),
        (SERVICE_TURN_OFF, 409, "unreachable", STATE_OFF, NO_ERROR),
        (SERVICE_TURN_ON, 401, "unauthroized", STATE_OFF, NO_ERROR),
        (SERVICE_TURN_OFF, 401, "unauthroized", STATE_OFF, NO_ERROR),
        (SERVICE_TURN_OFF, 500, "server", STATE_OFF, ClientResponseError),
    ],
)
@pytest.mark.parametrize("vehicle_fixture", ["unknown_make"])
async def test_switch(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    snapshot: SnapshotAssertion,
    vehicle: AsyncMock,
    service_action: str,
    api_status: int,
    api_status_slug: str,
    expected_state: str,
    expected_raises: Exception,
) -> None:
    """Test switching charging on/off."""

    await setup_integration(hass, mock_config_entry)
    assert len(aioclient_mock.mock_calls) == 1

    aioclient_mock.post(
        f"{MOCK_API_ENDPOINT}/v2.0/vehicles/{vehicle['id']}/charge",
        status=api_status,
        json={
            "message": "Some message related to the action unused by our code",
            "status": api_status_slug,
        },
    )

    try:
        await hass.services.async_call(
            SWITCH_DOMAIN,
            service_action,
            {ATTR_ENTITY_ID: "switch.smartcar_784n_charging"},
            blocking=True,
        )
    except Exception as error:  # noqa: BLE001
        raised_error = error
    else:
        raised_error = None  # type: ignore[assignment]

    switch_state = hass.states.get("switch.smartcar_784n_charging")
    assert switch_state.state == expected_state
    assert isinstance(
        raised_error,
        expected_raises,  # type: ignore[arg-type]
    )

    assert len(aioclient_mock.mock_calls) == 2
    assert [tuple(mock_call) for mock_call in aioclient_mock.mock_calls[1:]] == snapshot


@pytest.mark.usefixtures("enable_all_entities")
@pytest.mark.parametrize("platform", [Platform.SWITCH])
@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
@pytest.mark.parametrize(
    ("webhook_body", "webhook_headers", "expected"),
    [("all", {"sc-signature": "1234"}, {})],  # JSON fixture
    indirect=["webhook_body"],
    ids=["vehicle_state_all"],
)
async def test_webhook_update(webhook_scenario: Callable[[], Awaitable[None]]) -> None:
    await webhook_scenario()


RESTORE_STATE_V2_PARAMETRIZE_ARGS = [
    (
        "entities",
        "expected_coordinator_data",
        "values_sort_key",
    ),
    [
        (
            {
                "switch.vw_id_4_charging": {
                    "stored_data": {"raw_value": "CHARGING"},
                    "expected_state": "on",
                },
            },
            {
                "charge-ischarging": {
                    "value": True,
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
