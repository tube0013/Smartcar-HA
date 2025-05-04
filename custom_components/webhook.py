# custom_components/smartcar/webhook.py
# ... (imports, including coordinator) ...
from homeassistant.core import HomeAssistant
from aiohttp import web
import json
import logging

# Define DOMAIN for the integration
DOMAIN = "smartcar"

_LOGGER = logging.getLogger(__name__)

async def async_handle_webhook(hass: HomeAssistant, webhook_id: str, request: web.Request):
    # ... (Get entry, webhook_secret) ...
    # ... (Verify Signature) ...
    # ... (Handle Verification Challenge) ...

    # --- Handle Event Payload ---
    try:
        raw_body = await request.read()  # Extract raw body from the request
        body_json = json.loads(raw_body.decode('utf-8')) # Decode after signature check
        event_name = body_json.get("eventName")
        # Use vehicleId from payload if available, fallback maybe needed?
        vehicle_id = body_json.get("vehicleId") # Check actual key name from Smartcar docs
        payload = body_json.get("payload")
    except json.JSONDecodeError as e:
        _LOGGER.error("Failed to decode JSON payload: %s", e)
        return web.Response(status=400)

        if not event_name or not vehicle_id or payload is None:
             _LOGGER.warning("Webhook received incomplete event: %s", body_json)
             return web.Response(status=400)

        _LOGGER.info("Processing webhook event '%s' for vehicle '%s'", event_name, vehicle_id)

        # Find the correct coordinator
        # Assuming single vehicle per entry for now for simplicity
        coordinator = next(iter(hass.data[DOMAIN][webhook_id]["coordinators"].values()), None)
        if not coordinator or coordinator.vehicle_id != vehicle_id:
             _LOGGER.warning("Webhook event for unknown/mismatched vehicle ID %s", vehicle_id)
             return web.Response(status=404) # Or 200 if we don't want retry? Check Smartcar docs.

        # --- Merge webhook data into coordinator ---
        current_data = coordinator.data.copy() if coordinator.data else {}
        data_updated = False

        # Map eventName to coordinator data key and process payload
        # IMPORTANT: Adjust keys and payload structure based on actual Smartcar webhook events!
        if event_name == "charge.status" or event_name.startswith("charge"): # Example event name
            # Assuming payload contains {'state': '...', 'isPluggedIn': ...}
            if isinstance(payload, dict):
                 current_data["charge"] = payload # Update whole charge structure
                 data_updated = True
                 _LOGGER.debug("Coordinator %s: Webhook updated charge data: %s", coordinator.name, payload)
                 # Adjust polling interval immediately based on webhook data
                 INTERVAL_IDLE = 300  # Define an appropriate value for idle interval
                 INTERVAL_CHARGING = 60  # Define an appropriate value for charging interval
                 
                 new_interval = INTERVAL_IDLE
                 if payload.get("state") == "CHARGING":
                     new_interval = INTERVAL_CHARGING
                 if new_interval != coordinator.update_interval:
                     _LOGGER.info("Coordinator %s: Setting polling interval to %s based on webhook", coordinator.name, new_interval)
                     coordinator.async_set_update_interval(new_interval)

        elif event_name == "battery.level" or event_name.startswith("battery"): # Example event name
             # Assuming payload contains {'percentRemaining': ..., 'range': ...}
             if isinstance(payload, dict):
                  # Update battery data, keep existing keys if payload is partial
                  current_data["battery"] = current_data.get("battery", {}) | payload
                  data_updated = True
                  _LOGGER.debug("Coordinator %s: Webhook updated battery data: %s", coordinator.name, payload)

        elif event_name == "location.update" or event_name.startswith("location"): # Example event name
              # Assuming payload contains {'latitude': ..., 'longitude': ...}
             if isinstance(payload, dict):
                  current_data["location"] = payload
                  data_updated = True
                  _LOGGER.debug("Coordinator %s: Webhook updated location data: %s", coordinator.name, payload)

        # --- Add handlers for other webhook eventNames you subscribe to ---
        else:
            _LOGGER.info("Received unhandled webhook event type: %s", event_name)

        # Push updates to HA listeners if data changed
        if data_updated:
            coordinator.async_set_updated_data(current_data)

        return web.Response(status=200) # Acknowledge receipt

    # ... (Exception handling for payload processing) ...