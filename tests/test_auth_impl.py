"""Test auth concrete subclasses."""

from custom_components.smartcar.auth_impl import (
    AccessTokenAuthImpl,
    AsyncConfigEntryAuth,
)


async def test_config_entry_auth():
    class MockOAuth2Session:
        async def async_ensure_token_valid(self):
            self.token = {"access_token": "mock-token"}

    websession = None
    oauth_session = MockOAuth2Session()
    auth = AsyncConfigEntryAuth(websession, oauth_session, "mock-host")

    assert await auth.async_get_access_token() == "mock-token"


async def test_token_auth():
    websession = None
    auth = AccessTokenAuthImpl(websession, "mock-token", "mock-host")

    assert await auth.async_get_access_token() == "mock-token"
