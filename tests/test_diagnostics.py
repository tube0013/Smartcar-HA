"""Test Smartcar diagnostics."""

from unittest.mock import AsyncMock

from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion
from syrupy.filters import props

from custom_components.smartcar.const import CONF_APPLICATION_MANAGEMENT_TOKEN

from . import setup_added_integration, setup_integration


@pytest.mark.usefixtures("enable_all_entities")
async def test_entry_diagnostics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    hass_client: ClientSessionGenerator,
    snapshot: SnapshotAssertion,
    vehicle: AsyncMock,
) -> None:
    """Test config entry diagnostics."""
    await setup_integration(hass, mock_config_entry)
    assert await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    ) == snapshot(
        exclude=props(
            "entry_id", "webhook_id", "created_at", "modified_at", "expires_at"
        )
    )


@pytest.mark.usefixtures("enable_all_entities")
@pytest.mark.parametrize(
    ("vehicle_fixture", "webhook_body", "webhook_status"),
    [
        ("jaguar_ipace", "all", 204),
        ("jaguar_ipace", "all", 401),
        ("vw_id_4", b"invalid_json", 204),
    ],
    indirect=["webhook_body"],
    ids=[
        "location_redaction",
        "signature_validation_failure",  # keeps raw response
        "invalid_json",
    ],
)
async def test_entry_diagnostics_metadata(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    hass_client: ClientSessionGenerator,
    snapshot: SnapshotAssertion,
    vehicle_fixture: str,
    webhook_body: str | bytes,
    webhook_status: int,
) -> None:
    """Test config entry diagnostics."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={
            **mock_config_entry.data,
            CONF_WEBHOOK_ID: "smartcar_test",
            CONF_APPLICATION_MANAGEMENT_TOKEN: "test_amt",
        },
    )

    await setup_added_integration(hass, mock_config_entry)

    if isinstance(webhook_body, bytes):
        webhook_body = webhook_body.decode("utf-8")

    meta_coordinator = mock_config_entry.runtime_data.meta_coordinator
    meta_coordinator.async_set_updated_data(
        {
            "last_webhook_response": {
                "status": webhook_status,
            },
            "last_webhook_request": webhook_body,
        }
    )

    assert await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    ) == snapshot(
        exclude=props(
            "entry_id", "webhook_id", "created_at", "modified_at", "expires_at"
        )
    )
