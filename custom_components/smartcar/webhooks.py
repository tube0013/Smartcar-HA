import copy
import hmac
import json
import logging
from typing import Any, Literal

from aiohttp import web
from homeassistant.components import cloud, webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import util
from .const import CONF_APPLICATION_MANAGEMENT_TOKEN
from .coordinator import DATAPOINT_CODE_MAP, SmartcarVehicleCoordinator
from .types import SmartcarData

_LOGGER = logging.getLogger(__name__)

# values from the smartcar service that denote an imperial measurement and can
# be converted by one of the imperial_conversion functions defined on an entity
# description.
_IMPERIAL_MEASUREMENTS = {"miles", "psi", "gallons"}


async def webhook_url_from_id(hass: HomeAssistant, webhook_id: str) -> tuple[str, bool]:
    if cloud.async_active_subscription(hass):
        webhook_url = await cloud.async_create_cloudhook(hass, webhook_id)
        cloudhook = True
    else:
        webhook_url = webhook.async_generate_url(hass, webhook_id)
        cloudhook = False

    return webhook_url, cloudhook


async def handle_webhook(
    hass: HomeAssistant,  # noqa: ARG001
    webhook_id: str,  # noqa: ARG001
    request: web.Request,
    *,
    config_entry: ConfigEntry,
) -> web.Response:
    """Handle webhook callback.

    Returns:
        The response to send back to Smartcar.
    """
    try:
        body = await request.text()
        message = json.loads(body)
    except ValueError:
        _LOGGER.warning("Received invalid JSON from Smartcar")
        return web.json_response({})

    _LOGGER.debug("Received JSON from Smartcar: %s", body)

    response: dict[str, Any] = {}
    app_token: str = config_entry.data[CONF_APPLICATION_MANAGEMENT_TOKEN]
    signature = request.headers.get("SC-Signature")
    data = message.get("data", {})

    if message.get("eventType") == "VERIFY":
        return web.json_response(
            {"challenge": util.hmac_sha256_hexdigest(app_token, data["challenge"])}
        )

    # the verify message is not signed, so that's done before this check. all
    # other messages must be signed & validated before we process the data from
    # them.
    if not hmac.compare_digest(util.hmac_sha256_hexdigest(app_token, body), signature):
        _LOGGER.error("ignoring message with invalid signature")
        return web.Response(status=404)

    errors = data.get("errors", [])
    signals = data.get("signals", [])
    vehicle = data.get("vehicle", {})
    vehicle_id = vehicle.get("id")
    runtime_data: SmartcarData = config_entry.runtime_data
    coordinators = runtime_data.coordinators
    vehicle_vin: str | None = next(
        (
            vin
            for coordinator in coordinators.values()
            if (
                vin := coordinator.config_entry.data.get("vehicles", {})
                .get(vehicle_id, {})
                .get("vin")
            )
        ),
        None,
    )
    coordinator = coordinators.get(vehicle_vin) if vehicle_vin else None

    if not coordinator:
        _LOGGER.debug(
            "ignoring message for unknown vehicle with id: %s, vin: %s",
            vehicle_id,
            vehicle_vin or "unknown",
        )
        return web.Response(status=404)

    _handle_webhook_errors(coordinator, errors)
    _handle_webhook_signals(coordinator, signals)

    return web.json_response(response)


def _handle_webhook_errors(
    coordinator: SmartcarVehicleCoordinator,
    errors: list[dict],
) -> None:
    hass = coordinator.hass
    config_entry = coordinator.config_entry

    for error in errors:
        if (
            error.get("type") == "PERMISSION"
            and error.get("resolution", {}).get("type") == "REAUTHENTICATE"
        ):
            _LOGGER.info("requesting reauth due to webhook message: %s", error)
            config_entry.async_start_reauth(hass)
        else:
            _LOGGER.debug("ignoring error in webhook: %s", error)


def _handle_webhook_signals(
    coordinator: SmartcarVehicleCoordinator,
    signals: list[dict],
) -> None:
    with coordinator.create_updated_data() as (add_partial_data, updated_data):
        data_changed = False

        for signal in signals:
            name: str | None = signal.get("name")
            status = signal.get("status", {})
            is_error = status.get("value") == "ERROR"
            code: str | None = signal.get("code")
            is_integrated = code in DATAPOINT_CODE_MAP
            body = copy.deepcopy(signal.get("body", {}))
            meta = signal.get("meta", {})

            if is_error:
                _handle_webhook_signal_error(
                    name,
                    status.get("error", {}),
                    level="error" if is_integrated else "debug",
                )

                body = {"value": None}

            if body.get("unit") == "percent":
                body["value"] /= 100
                body.pop("unit")

            if code in DATAPOINT_CODE_MAP:
                data_age = meta.get("oemUpdatedAt") if not is_error else None
                fetched_at = meta.get("retrievedAt") if not is_error else None
                unit = body.pop("unit", None)
                unit_system = (
                    "imperial"
                    if unit in _IMPERIAL_MEASUREMENTS
                    else "metric"
                    if unit
                    else None
                )

                if data_age:
                    data_age = dt_util.utc_from_timestamp(data_age / 1000)
                if fetched_at:
                    fetched_at = dt_util.utc_from_timestamp(fetched_at / 1000)

                add_partial_data(
                    code,
                    body=body,
                    unit_system=unit_system,
                    data_age=data_age,
                    fetched_at=fetched_at,
                    can_clear_meta=not is_error,
                )

                data_changed = True

        if data_changed:
            coordinator.async_set_updated_data(updated_data)


def _handle_webhook_signal_error(
    signal_name: str | None,
    error: dict,
    *,
    level: Literal["error", "debug"] = "error",
) -> None:
    error_type = error.get("type")
    error_code = error.get("code")

    logger_method = getattr(_LOGGER, level)
    logger_method("error for signal %s: %s:%s", signal_name, error_type, error_code)
