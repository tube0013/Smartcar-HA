"""Test switch entities."""

from unittest.mock import AsyncMock

from aiohttp import ClientResponseError
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from syrupy.assertion import SnapshotAssertion

from . import MOCK_API_ENDPOINT, setup_integration

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
