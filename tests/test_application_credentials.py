"""Test application_credentials."""

from homeassistant.core import HomeAssistant
import pytest

from custom_components.smartcar.application_credentials import (
    async_get_description_placeholders,
)


@pytest.mark.parametrize(
    ("additional_components", "external_url", "expected_redirect_uri"),
    [
        ([], "https://example.com", "https://example.com/auth/external/callback"),
        ([], None, "https://YOUR_DOMAIN:PORT/auth/external/callback"),
        (["my"], "https://example.com", "https://my.home-assistant.io/redirect/oauth"),
    ],
)
async def test_description_placeholders(
    hass: HomeAssistant,
    additional_components: list[str],
    external_url: str | None,
    expected_redirect_uri: str,
) -> None:
    """Test description placeholders."""
    hass.config.components.update(additional_components)
    hass.config.external_url = external_url
    placeholders = await async_get_description_placeholders(hass)
    assert placeholders == {
        "more_info_url": "https://github.com/wbyoung/smartcar?tab=readme-ov-file#configuration",
        "oauth_creds_url": "https://dashboard.smartcar.com/team/applications",
        "redirect_url": expected_redirect_uri,
    }
