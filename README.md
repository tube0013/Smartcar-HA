# Smartcar Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
Connect your compatible vehicle to Home Assistant using the [Smartcar API](https://smartcar.com/).

This integration provides various sensors and controls for vehicles linked through the Smartcar platform, allowing you to monitor and interact with your car directly within Home Assistant.

**Note:** This integration relies on the Smartcar service. Availability of specific features depends on your vehicle's make, model, year, your Smartcar account plan (especially API rate limits), and the permissions granted during authentication.

## Features

Provides the following entities for each connected vehicle (subject to vehicle compatibility and granted permissions):

* **Device Tracker:**
    * Location (GPS)
* **Sensors:**
    * Odometer
    * Battery Level (%)
    * Estimated Range
    * Battery Capacity (kWh)
    * Charging Status (Charging, Not Charging, Fully Charged)
    * Engine Oil Life (%) (*If supported*)
    * Tire Pressures (*If supported*)
    * Fuel Level / Range (*If supported*)
* **Binary Sensors:**
    * Charging Cable Plugged In
* **Switches:**
    * Start/Stop Charging
* * **Number:**
    * Set Charge Limit (%)
* **Locks:**
    * Door Lock/Unlock (*Note: Known compatibility issues with some models, e.g., VW ID.4 2023+ seems unsupported via API*)

## Prerequisites

1.  **Compatible Vehicle:** Your car must be compatible with Smartcar. Check compatibility [here](https://smartcar.com/product/compatible-vehicles).
2.  **Smartcar Developer Account:** You need a free developer account from Smartcar.
    * Go to [developer.smartcar.com](https://developer.smartcar.com/) and sign up.
    * Log in to your Developer Dashboard.
3.  **Create a Smartcar Application:**
    * In the dashboard, go to "Applications" and click "Register a new application".
    * Give your application a name (e.g., "Home Assistant Connect").
    * **Crucially, set the "Redirect URIs".** You need to add **exactly** the URI your Home Assistant instance uses for OAuth callbacks.
        *  **My Home Assistant will work by default**, the URI is: `https://my.home-assistant.io/redirect/oauth`
        * Add **only** the correct URI for your setup.
    * Select the **Permissions (Scopes)** you want Home Assistant to be able to access. To enable all entities in this integration, select all relevant scopes like:
        * `read_vehicle_info`, `read_vin`
        * `read_odometer`, `read_location`
        * `read_battery`, `read_charge`
        * `control_charge`
        * `read_security`, `control_security`
        * `read_tires`, `read_engine_oil`, `read_fuel` (these may not work depending on car support)
        * *Select any other scopes corresponding to features you want.*
    * Choose the **Mode** (usually "Live" for real vehicles, "Test" or "Simulated" might work for testing if you don't have a compatible car linked yet).
    * Save the application.
4.  **Get Credentials:**
    * Once the application is created, go to its settings page on the Smartcar dashboard.
    * Find your **Client ID** and **Client Secret**. You will need these for the Home Assistant configuration.
    * **Keep your Client Secret secure!**
5.  **Link Your Vehicle (If needed for testing):** If using Live mode, ensure your actual vehicle's connected services account (e.g., your VW, Ford, Tesla account) is linked or ready to be linked via the Smartcar flow. For Test/Simulated mode, follow Smartcar's instructions.

## Installation

**Recommended: HACS**

1.  Ensure [HACS (Home Assistant Community Store)](https://hacs.xyz/) is installed.
2.  Go to HACS -> Integrations -> Click the three dots (⋮) in the top right -> Custom Repositories.
3.  Enter the URL of this GitHub repository (`https://github.com/tube0013/Smartcar-HA`) in the "Repository" field.
4.  Select "Integration" as the category.
5.  Click "Add".
6.  The "Smartcar" integration should now appear in the HACS list. Click on it and then click "Download".
7.  Confirm the download.
8.  **Restart Home Assistant** (Settings -> System -> Restart).

**Manual Installation**

1.  Download the latest release source code archive (`.zip` or `.tar.gz`).
2.  Unpack the archive.
3.  Copy the `custom_components/smartcar/` directory into your Home Assistant `<config>/custom_components/` directory. Create `custom_components` if it doesn't exist.
4.  **Restart Home Assistant** (Settings -> System -> Restart).

## Configuration

Configuration is done via the Home Assistant UI after installation.

1.  **Add Application Credentials:**
    * Go to **Settings > Devices & Services > Application Credentials** (If you don't see this, ensure "Advanced Mode" is enabled in your Home Assistant User Profile).
    * Click **+ Add Application Credential**.
    * Select **Smartcar** from the list.
    * Enter your **Client ID** and **Client Secret** obtained from the Smartcar Developer Dashboard.
    * Click **Save**.

2.  **Add Smartcar Integration:**
    * Go to **Settings > Devices & Services**.
    * Click **+ Add Integration**.
    * Search for **Smartcar** and select it.
    * A configuration window will appear. It should automatically detect your saved Application Credentials. Click **Submit**.

3.  **Smartcar Authorization:**
    * You will be redirected to the Smartcar website (or a new tab will open).
    * Log in using the credentials for your **vehicle's connected services account** (e.g., your Volkswagen ID, FordPass account, Tesla account), **NOT** your Smartcar developer account credentials.
    * Review the permissions requested by Home Assistant (these should match the scopes you selected when creating the Smartcar application).
    * **Grant access** to allow Home Assistant to connect to your vehicle(s) via Smartcar.
    * You should be redirected back to Home Assistant.

4.  **Success:** If successful, the integration will be added, and Home Assistant will create devices and entities for your connected vehicle(s).

## Rate Limits & Polling

* Smartcar's free developer tier typically has a limit of **500 API calls per vehicle per month**. Exceeding this may incur costs or stop the integration from working.
* This integration uses a **batch endpoint** to retrieve multiple data points in a single API call to minimize usage.
* It also uses **dynamic polling intervals:**
    * When the vehicle is detected as **CHARGING**: Updates every **30 minutes** (configurable in `coordinator.py`).
    * When the vehicle is **IDLE/NOT CHARGING**: Updates every **6 hours** (configurable in `coordinator.py`).
* This helps significantly reduce API calls while providing more frequent updates during important events (charging).

## Known Issues / Limitations

* **Vehicle Compatibility:** Not all features are supported by all vehicle makes/models/years via the Smartcar API. Entities for unsupported features (e.g., Lock control for VW ID.4 2023+) will not be created. Check the Smartcar compatibility details for your specific vehicle.
* **API Latency:** There can be significant delays (seconds to minutes) between sending a command (e.g., start charging) and the vehicle executing/reporting the change back through the API. The state in Home Assistant will update after the next successful data poll.
* **Rate Limits:** Be mindful of the 500 calls/vehicle/month limit on the free tier.

## Support / Issues

Please report any issues you find with this integration by opening an issue on the [GitHub Issues page](https://github.com/tube0013/Smartcar-HA/issues).