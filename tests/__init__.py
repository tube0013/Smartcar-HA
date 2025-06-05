import importlib

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    load_json_array_fixture,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.smartcar.const import DOMAIN

MOCK_API_ENDPOINT = "http://test.local"


async def setup_integration(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Helper for setting up the component."""
    config_entry.add_to_hass(hass)
    await setup_added_integration(hass, config_entry)


async def setup_added_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Helper for setting up a previously added component."""

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


def aioclient_mock_append_vehicle_request(
    aioclient_mock: AiohttpClientMocker,
    api_respone_type: str,
    vehicle_fixture: str,
    vehicle_attributes: dict,
):
    vehicle_id = vehicle_attributes["id"]
    fixture_name = f"api/{vehicle_fixture}.{api_respone_type}.json"
    http_calls = load_json_array_fixture(fixture_name, DOMAIN)

    for http_call in http_calls:
        method = http_call.get("method", "get")
        version = http_call.get("version", "2.0")
        params = http_call.get("params", {})
        status = http_call.get("status", 200)
        side_effect = http_call.get("side_effect")
        json = http_call.get("response")
        path = http_call.get("path")
        vehicle_path = http_call.get("vehicle_path")
        assert path or vehicle_path, (
            f"{fixture_name} fixture should provide one of `path` or `vehicle_path`"
        )
        assert json or side_effect or status != 200, (
            f"{fixture_name} fixture should provide `response`"
        )

        if not path:
            path = f"/vehicles/{vehicle_id}{vehicle_path}"

        if side_effect:
            module_path, class_name = side_effect.rsplit(".", 1)
            module = importlib.import_module(module_path)
            side_effect_class = getattr(module, class_name)

            def side_effect(
                *args,  # noqa: ANN002
                side_effect_class=side_effect_class,
            ):
                raise side_effect_class()

        getattr(aioclient_mock, method)(
            f"{MOCK_API_ENDPOINT}/v{version}{path}",
            params=params,
            status=status,
            side_effect=side_effect,
            json=json,
        )

    return http_calls
