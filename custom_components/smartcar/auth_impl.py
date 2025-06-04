from typing import cast

from aiohttp import ClientSession
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session

from .auth import AbstractAuth


class AsyncConfigEntryAuth(AbstractAuth):
    """Provide Smartcar authentication tied to an OAuth2 based config entry."""

    def __init__(
        self,
        websession: ClientSession,
        oauth_session: OAuth2Session,
        host: str,
    ) -> None:
        """Initialize Smartcar auth."""
        super().__init__(websession, host)
        self._oauth_session = oauth_session

    async def async_get_access_token(self) -> str:
        """Return a valid access token for Smartcar API."""
        await self._oauth_session.async_ensure_token_valid()
        return cast("str", self._oauth_session.token["access_token"])


class AccessTokenAuthImpl(AbstractAuth):
    """Authentication implementation used during config flow, without refresh.

    This exists to allow the config flow to use the API before it has fully
    created a config entry required by OAuth2Session. This does not support
    refreshing tokens, which is fine since it should have been just created.
    """

    def __init__(
        self,
        websession: ClientSession,
        access_token: str,
        host: str,
    ) -> None:
        """Init the Nest client library auth implementation."""
        super().__init__(websession, host)
        self._access_token = access_token

    async def async_get_access_token(self) -> str:
        """Return the access token."""
        return self._access_token
