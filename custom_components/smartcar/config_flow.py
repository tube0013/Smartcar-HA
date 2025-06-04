from collections.abc import Mapping
import logging
from typing import Any, cast

from aiohttp import ClientConnectorError, ClientError
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import AbstractOAuth2FlowHandler
import voluptuous as vol

from . import populate_entry_data, vehicle_vins_in_use
from .auth_impl import AccessTokenAuthImpl
from .const import (
    API_HOST,
    CONFIGURABLE_SCOPES,
    DEFAULT_NAME,
    DEFAULT_SCOPES,
    DOMAIN,
    REQUIRED_SCOPES,
    SMARTCAR_MODE,
    Scope,
)
from .errors import EmptyVehicleListError, InvalidAuthError, MissingVINError
from .util import unique_id_from_entry_data, vins_from_entry_data

_LOGGER = logging.getLogger(__name__)


class SmartcarOAuth2FlowHandler(AbstractOAuth2FlowHandler, domain=DOMAIN):  # type: ignore[call-arg]
    """Config flow to handle Smartcar OAuth2 authentication."""

    DOMAIN = DOMAIN
    VERSION = 2
    MINOR_VERSION = 0
    scope_data: dict[str, Any] | None = None

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra data that needs to be appended to the authorize url."""

        return {
            "mode": SMARTCAR_MODE,
            "scope": " ".join(self.requested_scopes),
        }

    @property
    def selected_scopes(self) -> list[Scope]:
        assert self.scope_data

        return sorted(
            [
                cast("Scope", scope)
                for scope, selected in self.scope_data.items()
                if selected
            ]
        )

    @property
    def requested_scopes(self) -> list[Scope]:
        return REQUIRED_SCOPES + self.selected_scopes

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # add in a step for scope selection if that hasn't been done yet
        if self.scope_data is None:
            return await self.async_step_scopes()
        return await super().async_step_auth(user_input)

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],  # noqa: ARG002
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error.

        Returns:
            The config flow result.
        """
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required.

        Returns:
            The config flow result.
        """
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()

    async def async_step_scopes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle scope selection and manually construct redirect URL.

        Returns:
            The config flow result.
        """
        _LOGGER.debug(
            "Handler %s: Starting step_scopes, input: %s",
            self.flow_id,
            user_input,
        )
        errors: dict[str, str] = {}

        if user_input is not None:
            self.scope_data = user_input

            if self.selected_scopes:
                return await self.async_step_auth()
            errors["base"] = "no_scopes"

        def default(scope: str) -> bool:
            if user_input is None:
                return scope in DEFAULT_SCOPES
            return bool(user_input.get(scope, False))

        return self.async_show_form(
            step_id="scopes",
            data_schema=vol.Schema(
                {
                    vol.Optional(str(scope), default=default(scope)): bool
                    for scope in CONFIGURABLE_SCOPES
                }
            ),
            errors=errors,
            last_step=False,
        )

    async def async_oauth_create_entry(self, data: dict) -> ConfigFlowResult:
        session = async_get_clientsession(self.hass)
        token = data[CONF_TOKEN][CONF_ACCESS_TOKEN]
        auth = AccessTokenAuthImpl(session, token, API_HOST)

        try:
            await populate_entry_data(
                data,
                auth,
                self.requested_scopes,
            )
        except EmptyVehicleListError:
            _LOGGER.exception("No vehicles returned")
            return self.async_abort(reason="no_vehicles")
        except MissingVINError:
            _LOGGER.exception("Missing vehicle VIN")
            return self.async_abort(reason="unknown")
        except InvalidAuthError:
            _LOGGER.exception("Failed to authenticate")
            return self.async_abort(reason="invalid_access_token")
        except (ClientConnectorError, ClientError):
            _LOGGER.exception("Failed to fetch vechicles")
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(unique_id_from_entry_data(data))

        other_vins = vehicle_vins_in_use(self.hass)
        duplicate_vins = [
            details["vin"]
            for details in data.get("vehicles", {}).values()
            if details["vin"] in other_vins
        ]

        if duplicate_vins:
            return self.async_abort(
                reason="duplicate_vehicles",
                description_placeholders={"duplicate_vins": duplicate_vins},
            )

        if self.source == SOURCE_REAUTH:
            reauth_entry = self._get_reauth_entry()

            self._abort_if_unique_id_mismatch(
                reason="wrong_vehicles",
                description_placeholders={
                    "vins": vins_from_entry_data(reauth_entry.data)
                },
            )

            return self.async_update_reload_and_abort(reauth_entry, data=data)

        self._abort_if_unique_id_configured()

        return self.async_create_entry(title=DEFAULT_NAME, data=data)
