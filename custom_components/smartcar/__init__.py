# custom_components/smartcar/__init__.py
# ... (imports) ...
import logging  # Import logging module

PLATFORMS = ["sensor", "binary_sensor"]  # Define supported platforms
from aiohttp import ClientResponseError  # Import ClientResponseError for exception handling
import asyncio  # Import asyncio for asynchronous operations

API_BASE_URL_V2 = "https://api.smartcar.com/v2.0"  # Define the base URL for Smartcar API
from .coordinator import SmartcarVehicleCoordinator  # Import SmartcarVehicleCoordinator

_LOGGER = logging.getLogger(__name__)  # Initialize logger

DOMAIN = "smartcar"  # Define the domain for the integration
from homeassistant.core import HomeAssistant  # Import HomeAssistant
from homeassistant.helpers import network, webhook, device_registry  # Import helpers including device_registry
from homeassistant.config_entries import ConfigEntry  # Import ConfigEntry
from .webhook import async_handle_webhook # Import handler function

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # ... (get session, initialize hass.data) ...
    entry_data = hass.data[DOMAIN][entry.entry_id]
    session = entry_data["session"]
    webhook_secret = entry.data.get("webhook_secret") # Get secret from entry data

    if not webhook_secret:
        _LOGGER.error("Webhook secret not found in config entry data. Cannot set up webhooks.")
        # Decide how to handle - maybe continue with polling only? Or fail setup?
        # For now, let's log and maybe skip webhook setup part
        pass # Continue without webhook functionality?

    # --- Webhook Setup ---
    webhook_id = entry.entry_id # Use unique entry ID for webhook ID
    entry_data["webhook_id"] = webhook_id # Store for unload
    try:
        webhook.async_register(
            hass, DOMAIN, "Smartcar", webhook_id, async_handle_webhook
        )
        _LOGGER.info("Registered webhook handler with ID: %s", webhook_id)
    except ValueError: # Already registered
        _LOGGER.info("Webhook handler already registered for ID: %s", webhook_id)

    try:
        webhook_url = webhook.async_generate_url(hass, webhook_id)
        _LOGGER.info("Generated Home Assistant webhook URL.") # Don't log the full URL+ID
    except webhook.WebhookNotAvailable:
        _LOGGER.error("Webhook support not available. Ensure base_url/external_url is configured.")
        # Cannot subscribe to Smartcar without a public URL
        webhook_url = None
    # --- End Webhook Setup ---

    # ... (Fetch vehicle IDs and details as before) ...

    setup_tasks = []
    vehicle_ids = [...] # Get list of vehicle_ids from API call
    for vehicle_id in vehicle_ids:
        # Pass webhook details down if needed, or just handle subscription here
        setup_tasks.append(async_setup_single_vehicle(
            hass, entry, session, vehicle_id, device_registry, webhook_url, webhook_secret
        ))
    # ... (gather tasks, handle results) ...

    # ... (forward to platforms) ...


async def async_setup_single_vehicle(
    hass: HomeAssistant, entry: ConfigEntry, session, vehicle_id, device_registry,
    webhook_url: str | None, webhook_secret: str | None # Added webhook args
) -> None:
    """Set up a single vehicle, including webhook subscription."""
    # ... (get VIN, attributes, register device as before) ...
    vin = ... # Get VIN

    # Create Coordinator (might change polling interval later)
    coordinator = SmartcarVehicleCoordinator(hass, session, vehicle_id, vin, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id]["coordinators"][vin] = coordinator

    # --- Subscribe to Smartcar Webhook ---
    if webhook_url and webhook_secret: # Only if webhook setup was successful
        sub_url = f"{API_BASE_URL_V2}/vehicles/{vehicle_id}/webhooks"
        payload = {"webhookUrl": webhook_url}
        try:
            _LOGGER.info("Subscribing vehicle %s (VIN %s) to webhook", vehicle_id, vin)
            sub_resp = await session.async_request("post", sub_url, json=payload)
            # Check Smartcar API docs for expected success code (likely 200 or 201)
            if sub_resp.status not in (200, 201):
                _LOGGER.error(
                    "Failed to subscribe vehicle %s to webhook. Status: %d, Response: %s",
                    vehicle_id, sub_resp.status, await sub_resp.text()
                )
            else:
                _LOGGER.info("Successfully subscribed vehicle %s to webhook", vehicle_id)
        except ClientResponseError as err:
            # Handle auth errors during subscription
            if err.status in (401, 403):
                 _LOGGER.warning("Auth error subscribing vehicle %s: %s. Missing scope?", vehicle_id, err)
                 # Might need specific scope like read_charge_events?
                 # Don't raise ConfigEntryAuthFailed here? Let coordinator handle polling?
            else:
                 _LOGGER.error("HTTP error subscribing vehicle %s: %s", vehicle_id, err)
        except Exception as err:
            _LOGGER.exception("Unexpected error subscribing vehicle %s: %s", vehicle_id, err)
    else:
         _LOGGER.warning("Webhook URL or Secret not available, skipping webhook subscription for VIN %s", vin)
    # --- End Webhook Subscription ---

    # ... (exception handling for overall setup) ...

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Smartcar entry %s", entry.entry_id)
    entry_data = hass.data[DOMAIN].get(entry.entry_id)

    # --- Unsubscribe and Unregister Webhook ---
    if entry_data:
        webhook_id = entry_data.get("webhook_id")
        if webhook_id:
            _LOGGER.info("Unregistering webhook handler: %s", webhook_id)
            try:
                 webhook.async_unregister(hass, webhook_id)
            except ValueError:
                 _LOGGER.warning("Webhook handler %s not found during unregister.", webhook_id)

            session = entry_data.get("session")
            coordinators = entry_data.get("coordinators", {})
            if session:
                 unsubscribe_tasks = []
                 for coord in coordinators.values():
                      # Need vehicle ID from coordinator
                      vehicle_id = coord.vehicle_id
                      unsub_url = f"{API_BASE_URL_V2}/vehicles/{vehicle_id}/webhooks"
                      _LOGGER.info("Unsubscribing vehicle %s from webhook", vehicle_id)
                      unsubscribe_tasks.append(session.async_request("delete", unsub_url))

                 if unsubscribe_tasks:
                      results = await asyncio.gather(*unsubscribe_tasks, return_exceptions=True)
                      for i, result in enumerate(results):
                           if isinstance(result, Exception):
                                _LOGGER.warning("Error unsubscribing vehicle %s: %s", list(coordinators.values())[i].vehicle_id, result)
    # --- End Unsubscribe ---

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _LOGGER.info("Unloaded Smartcar data for entry %s", entry.entry_id)
    return unload_ok