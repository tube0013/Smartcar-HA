from abc import ABC, abstractmethod
import logging

from aiohttp import ClientResponse, ClientSession

_LOGGER = logging.getLogger(__name__)


# note: this could be the start of allowing a separate client library to be
# designed that would be compatible with HA integrations. this is following the
# recommended design patterns for separating auth concerns from making api
# requests. this integration, however, chooses to make raw http requests
# instead of going through a library.
class AbstractAuth(ABC):
    """Abstract class to make authenticated requests."""

    def __init__(self, websession: ClientSession, host: str):
        """Initialize the auth."""
        self._websession = websession
        self._host = host

    @abstractmethod
    async def async_get_access_token(self) -> str:
        """Return a valid access token."""

    async def request(self, method, path, version="2.0", **kwargs) -> ClientResponse:
        """Make a request."""
        access_token = await self.async_get_access_token()
        headers = dict(kwargs.pop("headers", {}))
        headers["authorization"] = f"Bearer {access_token}"

        _LOGGER.debug(
            f"HTTP {method} request {self._host}/v{version}/{path} {repr(kwargs)} headers={repr(headers)}",
        )

        return await self._websession.request(
            method,
            f"{self._host}/v{version}/{path}",
            **kwargs,
            headers=headers,
        )
