"""Fixtures for testing."""

from collections.abc import Generator
import time
from unittest.mock import AsyncMock, PropertyMock, patch

from homeassistant.components.application_credentials import (
    ClientCredential,
    async_import_client_credential,
)
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    load_json_object_fixture,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    mock_aiohttp_client,
)

from custom_components.smartcar.auth import AbstractAuth
from custom_components.smartcar.const import DOMAIN, EntityDescriptionKey, Scope

from . import aioclient_mock_append_vehicle_request, setup_integration


class AdvancedPropertyMock(PropertyMock):
    def __get__(self, obj, obj_type=None):
        return self(obj)

    def __set__(self, obj, val):
        self(obj, val)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    return


@pytest.fixture
def aioclient_mock() -> Generator[AiohttpClientMocker]:
    """Fixture to mock aioclient calls."""
    with mock_aiohttp_client() as mock_session:
        yield mock_session


@pytest.fixture
def mock_smartcar_auth(
    aioclient_mock: AiohttpClientMocker,
) -> Generator[AsyncMock]:
    """Mock a Smartcar auth."""

    class MockAuth(AbstractAuth):
        async def async_get_access_token(self) -> str:  # noqa: PLR6301
            return "mock-token"

    with (
        patch(
            "custom_components.smartcar.auth.AbstractAuth", autospec=True
        ) as mock_auth,
        patch(
            "custom_components.smartcar.AsyncConfigEntryAuth",
            new=lambda session, _, _host: MockAuth(session, "http://test.local"),
        ),
        patch(
            "custom_components.smartcar.AccessTokenAuthImpl",
            new=lambda session, _, _host: MockAuth(session, "http://test.local"),
        ),
        patch(
            "custom_components.smartcar.config_flow.AccessTokenAuthImpl",
            new=lambda session, _, _host: MockAuth(session, "http://test.local"),
        ),
    ):
        yield mock_auth.return_value


@pytest.fixture(autouse=True)
async def setup_credentials(
    request: pytest.FixtureRequest, hass: HomeAssistant
) -> None:
    """Fixture to setup credentials."""
    assert await async_setup_component(hass, "application_credentials", {})

    if "no_credentials" in request.keywords:
        pass
    else:
        await async_import_client_credential(
            hass,
            DOMAIN,
            ClientCredential("mock-id", "mock-secret"),
            DOMAIN,
        )


@pytest.fixture(name="api_respone_type")
def mock_api_respone_type() -> str:
    """Fixture to define the API response fixture to use."""
    return "ok"


@pytest.fixture(name="enabled_scopes")
def mock_enabled_scopes() -> list[Scope]:
    """Fixture to define the scopes to use."""
    return list(Scope)


@pytest.fixture(params=["vw_id_4", "unknown_make"])
def vehicle_fixture(request: pytest.FixtureRequest) -> str:
    """Return every vehicle."""
    return str(request.param)


@pytest.fixture
def vehicle_attributes(vehicle_fixture: str) -> dict:
    """Return a specific vehicle's attributes."""
    return dict(load_json_object_fixture(f"vehicles/{vehicle_fixture}.json", DOMAIN))


@pytest.fixture
def vehicle(
    mock_smartcar_auth: AsyncMock,
    aioclient_mock: AiohttpClientMocker,
    api_respone_type: str,
    vehicle_fixture: str,
    vehicle_attributes: dict,
) -> dict:
    """Return a specific vehicle."""

    http_calls = aioclient_mock_append_vehicle_request(
        aioclient_mock,
        api_respone_type,
        vehicle_fixture,
        vehicle_attributes,
    )

    return dict(vehicle_attributes, _api=http_calls)


@pytest.fixture(name="expires_at")
def mock_expires_at() -> int:
    """Fixture to set the oauth token expiration time."""
    return int(time.time()) + 3600


@pytest.fixture
def mock_config_entry(
    expires_at: int,
    vehicle_attributes: dict,
    enabled_scopes: list[Scope],
    enabled_entities: set[EntityDescriptionKey],
) -> MockConfigEntry:
    """Return the default mocked config entry for a single vehicle."""
    vehicle = dict(vehicle_attributes)
    vehicle_id = vehicle.pop("id")
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=vehicle_id,
        version=2,
        minor_version=0,
        data={
            "auth_implementation": DOMAIN,
            "token": {
                "access_token": "mock-access-token",
                "refresh_token": "mock-refresh-token",
                "expires_at": expires_at,
                "scopes": " ".join(enabled_scopes),
                "access_tier": 0,
                "installed_app_id": "2d474f47-bab5-4438-9d37-478148b9d073",
            },
            "vehicles": {
                vehicle_id: vehicle,
            },
        },
    )


@pytest.fixture(name="enabled_entities")
def mock_enabled_entities() -> set[EntityDescriptionKey]:
    """Fixture to pre-enable entities.

    To use, pair with the `mock_entity_registry_enabled_default` fixture and
    extend the list prior to setting up the config entry.
    """
    return set()


@pytest.fixture(name="enable_all_entities")
def mock_enable_all_entities(
    enabled_entities: set[EntityDescriptionKey],
    mock_entity_registry_enabled_default: AsyncMock,
) -> None:
    """Fixture to pre-enable all entity entities."""

    enabled_entities.update(set(EntityDescriptionKey))


@pytest.fixture(name="enable_specified_entities")
def mock_enable_specified_entities(
    enabled_entities: set[EntityDescriptionKey],
    mock_entity_registry_enabled_default: AsyncMock,
) -> None:
    """Fixture to pre-enable entities specified in `enabled_entities` fixture."""


@pytest.fixture
def mock_entity_registry_enabled_default(
    enabled_entities: list[str],
) -> Generator[AsyncMock]:
    with patch(
        "custom_components.smartcar.entity.SmartcarEntityDescription.entity_registry_enabled_default",
        new_callable=AdvancedPropertyMock,
    ) as mock:
        mock.side_effect = lambda entity_description, _=None: (
            entity_description.key in enabled_entities if entity_description else ...
        )
        yield mock


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_smartcar_auth: AsyncMock,
) -> MockConfigEntry:
    """Set up the Smartcar integration for testing."""
    await setup_integration(hass, mock_config_entry)

    return mock_config_entry
