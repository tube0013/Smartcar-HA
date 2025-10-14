import asyncio
from functools import partial
from http import HTTPStatus
import logging

from aiohttp import ClientResponseError
from homeassistant.components import cloud, webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_TOKEN, CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import (
    OAuth2Session,
    async_get_config_entry_implementation,
)

from . import util
from .auth import AbstractAuth
from .auth_impl import AccessTokenAuthImpl, AsyncConfigEntryAuth
from .const import API_HOST, CONF_CLOUDHOOK, DOMAIN, PLATFORMS, Scope
from .coordinator import SmartcarVehicleCoordinator
from .errors import EmptyVehicleListError, InvalidAuthError, MissingVINError
from .types import SmartcarData
from .webhooks import handle_webhook, webhook_url_from_id

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smartcar from a config entry.

    Returns:
        If the setup was successful.

    Raises:
        ConfigEntryError: For overlapping VIN in config entries.
    """
    implementation = await async_get_config_entry_implementation(hass, entry)
    websession = async_get_clientsession(hass)
    oauth_session = OAuth2Session(hass, entry, implementation)
    auth = AsyncConfigEntryAuth(websession, oauth_session, API_HOST)
    coordinators: dict[str, SmartcarVehicleCoordinator] = {}
    entry.runtime_data = SmartcarData(auth=auth, coordinators=coordinators)
    device_registry = dr.async_get(hass)
    other_vins = vehicle_vins_in_use(hass, entry)

    for vehicle_id, details in entry.data.get("vehicles", {}).items():
        vin = details["vin"]
        make = details.get("make")
        model = details.get("model")
        year = details.get("year")

        if vin in other_vins:
            msg = f"Cannot setup multiple config entries with VIN {vin}"
            raise ConfigEntryError(msg)

        # register device
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, vin)},
            manufacturer=make,
            model=f"{model} ({year})" if model and year else model,
            name=f"{make} {model}" if make and model else f"Smartcar {vin[-4:]}",
        )
        _LOGGER.info("Registered device for VIN: %s", vin)

        # create and store coordinator
        coordinator = SmartcarVehicleCoordinator(hass, auth, vehicle_id, vin, entry)
        coordinators[vin] = coordinator
        _LOGGER.debug("Coordinator created and initial data fetched for VIN: %s", vin)

    # setup platforms before doing first refresh. this gets the entity registry
    # populated with the desired entities & allows the coordinator to determine
    # what to fetch on the first refresh. (some entities, for instance, are
    # disabled by default.)
    _LOGGER.debug("Forwarding setup to platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if CONF_WEBHOOK_ID in entry.data:
        _LOGGER.info(
            "Registering webhook at url: %s",
            (await webhook_url_from_id(hass, entry.data[CONF_WEBHOOK_ID]))[0],
        )
        webhook.async_register(
            hass,
            DOMAIN,
            entry.title,
            entry.data[CONF_WEBHOOK_ID],
            partial(handle_webhook, config_entry=entry),
        )
    else:
        _LOGGER.debug("Webhooks are not enabled")

    await asyncio.gather(
        *[async_do_first_refresh(coordinator) for coordinator in coordinators.values()]
    )

    # log stored scopes once on successful setup
    _LOGGER.info(
        "Using token with scopes: %s", entry.data.get("token", {}).get("scopes")
    )

    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    return True


async def async_do_first_refresh(coordinator: SmartcarVehicleCoordinator) -> None:
    await coordinator.async_config_entry_first_refresh()
    _LOGGER.debug(
        "Coordinator created and initial data fetched for VIN: %s", coordinator.vin
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Returns:
        If the unload was successful.
    """
    _LOGGER.info("Unloading Smartcar entry %s", entry.entry_id)
    if CONF_WEBHOOK_ID in entry.data:
        webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    return bool(await hass.config_entries.async_unload_platforms(entry, PLATFORMS))


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Cleanup when entry is removed."""
    if CONF_WEBHOOK_ID in entry.data and (
        cloud.async_active_subscription(hass) or entry.data.get(CONF_CLOUDHOOK, False)
    ):
        try:
            _LOGGER.debug(
                "Removing Smartcar cloudhook (%s)", entry.data[CONF_WEBHOOK_ID]
            )
            await cloud.async_delete_cloudhook(hass, entry.data[CONF_WEBHOOK_ID])
        except cloud.CloudNotAvailable:
            pass


async def async_update_listener(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    _LOGGER.debug(
        "Migrating configuration from version %s.%s",
        config_entry.version,
        config_entry.minor_version,
    )

    # prevent rollbacks
    if config_entry.version > 2:
        return False

    if config_entry.version == 1:
        old_data = config_entry.data
        session = async_get_clientsession(hass)
        token = old_data[CONF_TOKEN]
        access_token = token[CONF_ACCESS_TOKEN]
        scopes = token["scope"].split(" ")
        auth = AccessTokenAuthImpl(session, access_token, API_HOST)

        # copy old data & remove old keys
        new_data = {**old_data}
        new_data[CONF_TOKEN] = {**old_data[CONF_TOKEN]}
        new_data[CONF_TOKEN].pop("scope", None)

        await populate_entry_data(new_data, auth, scopes)

        old_vehicle_ids = set(old_data.get("vehicles", {}).keys())
        new_vehicle_ids = set(new_data["vehicles"].keys())

        # limit the vehicles in the config entry to whatever was in the previous
        # entry even if the API is returning new items.
        if old_vehicle_ids:
            for vehicle_id in new_vehicle_ids:
                if vehicle_id not in old_vehicle_ids:
                    new_data["vehicles"].pop(vehicle_id, None)

        # ensure all previously accessible vehicles are still accessible.
        inaccessible_vehicle_ids = [
            vehicle_id
            for vehicle_id in old_vehicle_ids
            if vehicle_id not in new_vehicle_ids
        ]

        if inaccessible_vehicle_ids:
            _LOGGER.error(
                "Vehicle(s) are no longer accessible via the API: %s",
                inaccessible_vehicle_ids,
            )
            return False

        hass.config_entries.async_update_entry(
            config_entry,
            unique_id=util.unique_id_from_entry_data(new_data),
            data=new_data,
            version=2,
            minor_version=0,
        )

    _LOGGER.debug(
        "Migration to configuration version %s.%s successful",
        config_entry.version,
        config_entry.minor_version,
    )

    return True


def vehicle_vins_in_use(
    hass: HomeAssistant, config_entry: ConfigEntry = None
) -> set[str]:
    return {
        vehicle["vin"]
        for other_entry in hass.config_entries.async_entries(DOMAIN)
        for vehicle in other_entry.data.get("vehicles", {}).values()
        if not config_entry or other_entry.unique_id != config_entry.unique_id
    }


async def populate_entry_data(
    data: dict,
    auth: AbstractAuth,
    scopes: list[Scope],
) -> None:
    """Populate config entry data during initial creation or migration."""
    _inject_requested_scopes_into_entry_data(data, scopes)

    await _store_all_vehicles(data, auth)


def _inject_requested_scopes_into_entry_data(data: dict, scopes: list[Scope]) -> None:
    """Inject selected scopes into stored token data."""
    data.setdefault("token", {})["scopes"] = scopes


async def _store_all_vehicles(
    data: dict,
    auth: AbstractAuth,
) -> None:
    """Fetch and store data for all vehicles in config entry data.

    Raises:
        EmptyVehicleListError: If no vehicles are found.
        InvalidAuthError: If the request cannot be authorized.
        ClientResponseError: If there is a request error.
    """

    _LOGGER.info("Fetching Smartcar vehicle IDs...")

    data["vehicles"] = {}

    try:
        vehicle_list_resp = await auth.request(
            "get",
            "vehicles",
        )
        vehicle_list_resp.raise_for_status()
        vehicle_list_data = await vehicle_list_resp.json()
        vehicle_ids = vehicle_list_data.get("vehicles", [])
    except ClientResponseError as err:
        if err.status == HTTPStatus.UNAUTHORIZED:
            msg = f"Auth error fetching vehicle list: {err.status}"
            raise InvalidAuthError(msg) from err
        raise

    _LOGGER.info("Found %s vehicle IDs", len(vehicle_ids))

    if not vehicle_ids:
        raise EmptyVehicleListError

    await asyncio.gather(
        *[_store_vehicle_details(data, auth, vid) for vid in vehicle_ids]
    )


async def _store_vehicle_details(
    data: dict,
    auth: AbstractAuth,
    vehicle_id: str,
) -> None:
    """Fetch and store data for a single vehicle.

    Raises:
        MissingVINError: If the VIN is not available.
        InvalidAuthError: If the request cannot be authorized.
        ClientResponseError: If there is a request error.
    """

    try:
        _LOGGER.debug("Fetching VIN for vehicle ID: %s", vehicle_id)
        vin_resp = await auth.request(
            "get",
            f"vehicles/{vehicle_id}/vin",
        )
        vin_resp.raise_for_status()
        vin_data = await vin_resp.json()
        vin = vin_data.get("vin")

        if not vin:
            msg = f"No VIN for vehicle {vehicle_id}"
            raise MissingVINError(msg)

        data["vehicles"][vehicle_id] = {
            "vin": vin,
        }

        _LOGGER.debug("Fetching attributes for vehicle ID: %s", vehicle_id)
        attr_resp = await auth.request(
            "get",
            f"vehicles/{vehicle_id}",
        )
        attr_resp.raise_for_status()
        vehicle_info = await attr_resp.json()
        make = vehicle_info.get("make")
        model = vehicle_info.get("model")
        year = vehicle_info.get("year")

        data["vehicles"][vehicle_id].update(
            {
                "make": make,
                "model": model,
                "year": year,
            }
        )
    except ClientResponseError as err:
        if err.status == HTTPStatus.UNAUTHORIZED:
            msg = f"Auth error [{err.status}] during vehicle setup"
            raise InvalidAuthError(msg) from err
        raise
