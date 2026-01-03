"""Test binary sensors."""

from collections.abc import Awaitable, Callable

from homeassistant.const import Platform
import pytest


@pytest.mark.usefixtures("enable_all_entities")
@pytest.mark.parametrize("platform", [Platform.BINARY_SENSOR])
@pytest.mark.parametrize("vehicle_fixture", ["vw_id_4"])
@pytest.mark.parametrize(
    ("webhook_body", "webhook_headers", "expected"),
    [
        (
            "multi_state",  # JSON fixture
            {
                "sc-signature": "1234",
            },
            {},
        ),
        ("all", {"sc-signature": "1234"}, {}),
    ],
    indirect=["webhook_body"],
    ids=[
        "vehicle_state",
        "vehicle_state_all",
    ],
)
async def test_webhook_update(webhook_scenario: Callable[[], Awaitable[None]]) -> None:
    await webhook_scenario()
