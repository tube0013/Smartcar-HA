# custom_components/smartcar/config_flow.py
# ... (imports, ALL_SCOPES, DEFAULT_SCOPES definitions) ...
from custom_components.smartcar.const import DEFAULT_NAME  # Ensure DEFAULT_NAME is defined in const.py
from custom_components.smartcar.const import SMARTCAR_MODE  # Ensure SMARTCAR_MODE is defined in const.py
import logging
from urllib.parse import urlencode, quote
import voluptuous as vol
from homeassistant.helpers.config_entry_oauth2_flow import AbortFlow, config_entry_oauth2_flow, FlowResult

_LOGGER = logging.getLogger(__name__)

class SmartcarOAuth2FlowHandler(...):
    # ... (VERSION, _selected_scopes, logger, async_step_user) ...

    # Add instance variable for webhook secret
    _webhook_secret: str | None = None

    async def async_step_scopes(self, user_input=None):
        # ... (Show scope form if user_input is None) ...
        # --- Existing logic when form is submitted ---
        errors = {}
        if user_input is not None:
            # ... (process selected scopes, store in self._selected_scopes) ...
            if not errors: # If scopes are valid
                 # ---> Instead of proceeding to OAuth redirect, go to webhook secret step
                 return await self.async_step_webhook_secret()
        # --- End existing logic ---
        # Show scope form if needed (initial view or errors)
        # ... (Show scope form logic) ...

    async def async_step_webhook_secret(self, user_input=None):
        """Get the Webhook Secret from the user."""
        errors = {}
        if user_input is not None:
            secret = user_input.get("webhook_secret")
            if secret:
                self._webhook_secret = secret
                _LOGGER.debug("Webhook secret received, proceeding to check implementation")
                # Now proceed with the OAuth implementation check and redirect
                try:
                    implementations = await config_entry_oauth2_flow.async_get_implementations(self.hass, self.DOMAIN)
                    if len(implementations) != 1: return self.async_abort(reason="oauth_impl_error")
                    self.flow_impl = list(implementations.values())[0]

                    # Generate URL manually (as before) including selected scopes
                    authorize_url = await self.flow_impl.async_generate_authorize_url(self.flow_id)
                    extra_params = { "scope": self._selected_scopes, "mode": SMARTCAR_MODE }
                    params_to_add = {k: v for k, v in extra_params.items() if v}
                    separator = "&" if "?" in authorize_url else "?"
                    encoded_extra_params = urlencode(params_to_add, quote_via=quote)
                    final_authorize_url = f"{authorize_url}{separator}{encoded_extra_params}"

                    _LOGGER.info("Handler %s: Redirecting user for OAuth", self.flow_id)
                    return self.async_external_step(step_id="auth", url=final_authorize_url)

                except AbortFlow as err: return self.async_abort(reason=err.reason)
                except Exception as err: _LOGGER.exception(...); return self.async_abort(reason="unknown")
            else:
                errors["base"] = "secret_required" # Define in strings.json

        # Show form to get secret
        return self.async_show_form(
            step_id="webhook_secret",
            data_schema=vol.Schema({
                vol.Required("webhook_secret"): str,
            }),
            description_placeholders={
                "webhook_secret_info": "Enter the Webhook Secret found in your Smartcar Application settings under the 'Webhooks' section."
            },
            errors=errors,
            last_step=False
        )


    # Modify async_oauth_create_entry to also store the webhook secret
    async def async_oauth_create_entry(self, data: dict) -> FlowResult:
        # ... (Existing scope injection logic) ...

        # Add the webhook secret collected during the flow
        if self._webhook_secret:
             data["webhook_secret"] = self._webhook_secret
        else:
             # This shouldn't happen if the flow is correct, but handle defensively
             _LOGGER.error("Webhook secret missing during entry creation!")
             # Maybe abort? For now, let it create but log error.
             # return self.async_abort(reason="internal_error_secret_missing")

        title = DEFAULT_NAME
        _LOGGER.debug("Creating config entry with final data (including webhook secret)")
        return self.async_create_entry(title=title, data=data)

    # ... (extra_authorize_data (REMOVED if using manual URL), async_step_reauth) ...
    # Note: extra_authorize_data is technically no longer needed if we build the URL manually above