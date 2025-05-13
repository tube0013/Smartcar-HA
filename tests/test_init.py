"""Test component setup."""

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from syrupy.assertion import SnapshotAssertion

from custom_components.smartcar.const import DOMAIN, REQUIRED_SCOPES

from . import MOCK_API_ENDPOINT, setup_integration


async def test_async_setup(hass: HomeAssistant):
    """Test the component gets setup."""
    assert await async_setup_component(hass, DOMAIN, {}) is True


async def test_standard_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
    vehicle: AsyncMock,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test all devices and entities in a standard setup."""
    await setup_integration(hass, mock_config_entry)

    device_id = vehicle["vin"]
    device = device_registry.async_get_device({(DOMAIN, device_id)})

    assert device is not None
    assert device == snapshot(name="device")

    entities = entity_registry.entities.get_entries_for_device_id(device.id)
    assert entities == snapshot(name="entities")

    for entity in entities:
        assert hass.states.get(entity.entity_id) == snapshot(name=entity.entity_id)


@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
async def test_duplicate_vins_disallowed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    vehicle: AsyncMock,
) -> None:
    """Test setup fails if config entities share vehicles with the same VIN."""

    # setup the duplicate first with two vehicles
    duplicate_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="mock-vehicle-id-1 mock-vehicle-id-2",
        version=2,
        minor_version=0,
        data={
            "auth_implementation": DOMAIN,
            "token": {},
            "vehicles": {
                "mock-vehicle-id-1": {"vin": vehicle["vin"]},
                "mock-vehicle-id-2": {"vin": "mock-another-vin"},
            },
        },
    )

    # register it while skipping all of the entity config and whatnot
    with patch("custom_components.smartcar.async_setup_entry", return_value=True):
        await setup_integration(hass, duplicate_entry)
    assert duplicate_entry.state is ConfigEntryState.LOADED

    # setup of this config entry should fail
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR


@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
@pytest.mark.parametrize("enabled_scopes", [REQUIRED_SCOPES + ["read_battery"]])
async def test_limited_scopes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
    vehicle: AsyncMock,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test setup when only limited scopes are enabled."""
    await setup_integration(hass, mock_config_entry)

    device_id = vehicle["vin"]
    device = device_registry.async_get_device({(DOMAIN, device_id)})

    assert device is not None
    assert device == snapshot(name="device")

    # few entities should be created (only if they derive their value from the
    # /battery endpoint)
    entities = entity_registry.entities.get_entries_for_device_id(device.id)
    assert entities == snapshot(name="entities")

    for entity in entities:
        assert hass.states.get(entity.entity_id) == snapshot(name=entity.entity_id)


@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
@pytest.mark.parametrize(
    "api_respone_type",
    [
        "server_error",
        "network_error",
        "network_proxy_response",
        "unauthorized",
    ],
)
async def test_update_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
    vehicle: AsyncMock,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test setup with a server error."""
    await setup_integration(hass, mock_config_entry)

    device_id = vehicle["vin"]
    device = device_registry.async_get_device({(DOMAIN, device_id)})

    assert device is not None
    assert device == snapshot(name="device")

    # all entities should still be created
    entities = entity_registry.entities.get_entries_for_device_id(device.id)
    assert entities == snapshot(name="entities")

    for entity in entities:
        assert hass.states.get(entity.entity_id) == snapshot(name=entity.entity_id)


@pytest.mark.parametrize(
    (
        "from_version",
        "from_minor_version",
        "config_data",
        "api_vehicle_ids",
        "expected_unique_id",
        "expected_state",
        "expect_migrated",
    ),
    [
        pytest.param(
            1,
            0,
            {
                "token": {
                    "access_token": "mock-access-token",
                    "scope": "read_vehicle_info read_vin read_battery",
                }
            },
            ["mock_vehicle_id_1"],
            "mock_vehicle_id_1",
            ConfigEntryState.LOADED,
            True,
            id="single_vehicle_not_in_config_entry",
        ),
        pytest.param(
            1,
            1,
            {
                "vehicles": {
                    "mock_vehicle_id_1": {},
                },
                "token": {
                    "access_token": "mock-access-token",
                    "scope": "read_vehicle_info read_vin read_battery",
                },
            },
            ["mock_vehicle_id_1"],
            "mock_vehicle_id_1",
            ConfigEntryState.LOADED,
            True,
            id="single_vehicle_in_config_entry",
        ),
        pytest.param(
            1,
            1,
            {
                "vehicles": {
                    "mock_vehicle_id_1": {},
                    "mock_vehicle_id_2": {},
                },
                "token": {
                    "access_token": "mock-access-token",
                    "scope": "read_vehicle_info read_vin read_battery",
                },
            },
            ["mock_vehicle_id_1", "mock_vehicle_id_2"],
            "mock_vehicle_id_1 mock_vehicle_id_2",
            ConfigEntryState.LOADED,
            True,
            id="multiple_vehicles_in_config_entry",
        ),
        pytest.param(
            1,
            1,
            {
                "vehicles": {
                    "mock_vehicle_id_1": {},
                    "mock_vehicle_id_2": {},
                },
                "token": {
                    "access_token": "mock-access-token",
                    "scope": "read_vehicle_info read_vin read_battery",
                },
            },
            ["mock_vehicle_id_1", "mock_vehicle_id_2", "mock_vehicle_id_3"],
            "mock_vehicle_id_1 mock_vehicle_id_2",
            ConfigEntryState.LOADED,
            True,
            id="multiple_vehicles_in_config_entry_and_api_returns_new_vehicles",
        ),
        pytest.param(
            1,
            1,
            {
                "vehicles": {
                    "mock_vehicle_id_1": {},
                    "mock_vehicle_id_2": {},
                },
                "token": {
                    "access_token": "mock-access-token",
                    "scope": "read_vehicle_info read_vin read_battery",
                },
            },
            ["mock_vehicle_id_1"],
            None,
            ConfigEntryState.MIGRATION_ERROR,
            False,
            id="multiple_vehicles_in_config_entry_and_api_missing_vehicle",
        ),
        pytest.param(
            0,
            1,
            {},
            [],
            None,
            ConfigEntryState.LOADED,
            False,
            id="pre_release_not_migrated",
        ),
        pytest.param(
            3,
            0,
            {},
            [],
            None,
            ConfigEntryState.MIGRATION_ERROR,
            False,
            id="version_rollback",
        ),
    ],
)
async def test_migration(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    mock_smartcar_auth: AsyncMock,
    aioclient_mock: AiohttpClientMocker,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    from_version: int,
    from_minor_version: int,
    config_data: dict,
    api_vehicle_ids: list[str],
    expected_unique_id: str | None,
    expected_state: ConfigEntryState,
    expect_migrated: bool,
) -> None:
    """Test different expected migration paths."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=dict(
            {
                "auth_implementation": DOMAIN,
            },
            **config_data,
        ),
        title=f"MIGRATION_TEST from {from_version}.{from_minor_version}",
        version=from_version,
        minor_version=from_minor_version,
        unique_id=None,
        entry_id="mock_old_entry_id",
    )

    aioclient_mock.get(
        f"{MOCK_API_ENDPOINT}/v2.0/vehicles",
        json=({"paging": {"count": 25, "offset": 0}, "vehicles": api_vehicle_ids}),
    )
    for vehicle_id in api_vehicle_ids:
        aioclient_mock.get(
            f"{MOCK_API_ENDPOINT}/v2.0/vehicles/{vehicle_id}/vin",
            json={"vin": f"mock-vin-for-${vehicle_id}"},
        )
        aioclient_mock.get(
            f"{MOCK_API_ENDPOINT}/v2.0/vehicles/{vehicle_id}",
            json=(
                {
                    "id": vehicle_id,
                    "make": f"Make for {vehicle_id}",
                    "model": f"Model for {vehicle_id}",
                    "year": f"Year for {vehicle_id}",
                }
            ),
        )

    with patch("custom_components.smartcar.async_setup_entry", return_value=True):
        await setup_integration(hass, config_entry)

    assert config_entry.state == expected_state

    # check change in config entry and verify most recent version
    if expect_migrated:
        assert config_entry.version == 2
        assert config_entry.minor_version == 0
        assert config_entry.data == snapshot(name="config_entry_data")

    assert config_entry.unique_id == expected_unique_id
