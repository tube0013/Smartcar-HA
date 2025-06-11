# Smartcar Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/github/v/release/tube0013/Smartcar-HA)][releases]
![Downloads](https://img.shields.io/github/downloads/tube0013/Smartcar-HA/total)
![Build](https://img.shields.io/github/actions/workflow/status/tube0013/Smartcar-HA/pytest.yml
)


Connect your compatible vehicle to Home Assistant using the [Smartcar API](https://smartcar.com/).

This integration provides various sensors and controls for vehicles linked through the Smartcar platform, allowing you to monitor and interact with your car directly within Home Assistant.

**Note:** This integration relies on the Smartcar service. Availability of specific features depends on your vehicle's make, model, year, your Smartcar account plan (especially API rate limits), and the permissions granted during authentication.

<img src="images/device_page.png" alt="Example Device Page Screenshot" width="600"/>

_Example showing entities for a Volkswagen ID.4_

## Features

Provides the following entities for each connected vehicle (subject to vehicle compatibility and granted permissions):

* **Device Tracker:**
    * Location (GPS)
* **Sensors:**
    * Odometer
    * Battery Level (percentage)
    * Estimated Range
    * Battery Capacity (kWh)
    * Charging Status (Charging, Not Charging, Fully Charged)
    * Engine Oil Life (percentage) *(if supported)*
    * Tire Pressures *(if supported)*
    * Fuel Level / Range *(if supported)*
* **Binary Sensors:**
    * Charging Cable Plugged In
* **Switches:**
    * Start/Stop Charging
* **Number:**
    * Set Charge Limit (percentage)
* **Locks:**
    * Door Lock/Unlock *(note: known compatibility issues with some models, e.g., VW ID.4 2023+ does not have this functionality)*

## Prerequisites

1.  **Compatible Vehicle:** Your car must be [compatible with Smartcar](https://smartcar.com/product/compatible-vehicles) and the API must also be [supported in your country](https://smartcar.com/global).
2.  **Smartcar Developer Account:** You need a free developer account from Smartcar.
    * Go to [developer.smartcar.com](https://developer.smartcar.com/) and sign up.
    * Log in to your Developer Dashboard.
3.  **Ensure a Smartcar Application exists:**
    * In the dashboard, go to "Applications" and ensure an application was automatically created for you.
    * Rename your application if you want to (e.g., "Home Assistant Connect").

## Installation

### HACS

Installation through [HACS][hacs] is the preferred installation method.

1. Go to HACS
1. Click on Integrations
1. Search for "Smartcar" &rarr; select it &rarr; press _DOWNLOAD_.
1. Select the version (it will auto select the latest) &rarr; press _DOWNLOAD_.
1. Restart Home Assistant then continue to [the setup section](#setup).

### Manual Download

1. Go to the [release page][releases] and download the `smartcar.zip` attached
   to the latest release.
1. Unpack the zip file and move `custom_components/smartcar` to the following
   directory of your Home Assistant configuration: `/config/custom_components/`.
1. Restart Home Assistant then continue to [the setup section](#setup).

## Setup

Configuration is done via the Home Assistant UI after installation.

1. Navigate to "Settings" &rarr; "Devices & Services"
1. Click "+ Add Integration"
1. Search for and select &rarr; "Smartcar"

Or you can use the My Home Assistant Button below.

[![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)][config-flow-start]

Follow the instructions to configure the integration.

### Configuration Flow

#### Authorization Data Entry

1. Choose a name for your credentials and enter the **Client ID** and **Client Secret** which can be found in the [Smartcar dashboard](https://dashboard.smartcar.com/team/applications).
1. **Crucially, set the "Redirect URIs"** in the Smartcar settings for your application. You need to add **exactly** the URI your Home Assistant instance uses for OAuth callbacks.
    *  Most users will simply use the **My Home Assistant** URI: `https://my.home-assistant.io/redirect/oauth`
        > Note: This is not a placeholder. It is the URI that must be used unless you’ve disabled or removed the `default_config:` line from your configuration and disabled the [My Home Assistant Integration](https://www.home-assistant.io/integrations/my/).
    * Add **only** the correct URI for your setup.
1. Continue to the next step.
1. Select the **Permissions** you want Home Assistant to be able to access. To enable all entities in this integration, select all relevant permissions:

    * Get total distance traveled
    * Get the vehicle's location
    * Get EV/PHEV battery level, capacity & current range
    * Get details on whether the car is plugged in and charging
    * Get details on whether doors, windows & more are enabled
    * Get engine oil health*
    * Get tire pressure details*
    * Get fuel tank level*
    * Control charging (start/stop & target charge)
    * Lock or unlock vehicle

    \* _These may not work depending on car support_

1. Continue to the [next section](#authorization-via-smartcar-connect) which explains the steps to authorize your vehicle via [Smartcar connect](https://smartcar.com/docs/connect/what-is-connect).

#### Authorization via Smartcar Connect

1. You will be redirected to the Smartcar website (or a new tab will open).
1. Log in using the credentials for your **vehicle's connected services account** (e.g., your Volkswagen ID, FordPass account, Tesla account), **NOT** your Smartcar developer account credentials.
1. Review the permissions requested by Home Assistant (these should match the scopes you selected when creating the Smartcar application).
1. **Grant access** to allow Home Assistant to connect to your vehicle(s) via Smartcar.
1. You should be redirected back to Home Assistant.

#### Setup Complete

If successful, the integration will be added, and Home Assistant will create devices and entities for your connected vehicle(s). From here:

- Enable entities you want access after understanding [the impact on rate limits](#rate-limits--polling).
- Consider creating a [customized polling setup](#customized-polling) via automations.

## Rate Limits & Polling

* Smartcar's free developer tier typically has a limit of **500 API calls per vehicle per month**. Exceeding this may incur costs or stop the integration from working.
* By default, it uses **6 hour polling interval** and only fetches data required for enabled entities.
* Polling can be [customized as well](#customized-polling).

### Customized Polling

To customize polling, you can disable polling on the integration and write your own automation.

* First, configure the integration as described above.
* Go to _Settings_ &rarr; _Integartions_ (under _Devices & services_) &rarr; _Smartcar_
* Click the three dots to the right of the integration.
* Choose _System options_.
* Disable _Enable polling for changes_ and then click _Save_.
* Create an automation using [`homeassistant.update_entity`](https://www.home-assistant.io/integrations/homeassistant/#action-homeassistantupdate_entity) to refresh the desired value(s). Examples are provided:

- [`examples/poll-smartcar-simple.yaml`](examples/poll-smartcar-simple.yaml)
- [`examples/poll-smartcar-custom.yaml`](examples/poll-smartcar-custom.yaml)
- [`examples/poll-smartcar-excessive.yaml`](examples/poll-smartcar-excessive.yaml)

## Known Issues / Limitations

* **Vehicle Compatibility:** Not all features are supported by all vehicle makes/models/years via the Smartcar API. Entities for unsupported features (e.g., Lock control for VW ID.4 2023+) may or may not be created. Check the Smartcar compatibility details for your specific vehicle.
* **API Latency:** There can be significant delays (seconds to minutes) between sending a command (e.g., start charging) and the vehicle executing/reporting the change back through the API. The state in Home Assistant will update after the next successful data poll.
* **Rate Limits:** Be mindful of the 500 calls/vehicle/month limit on the free tier.

## Support / Issues

Please report any issues you find with this integration by opening an issue on the [GitHub Issues page](https://github.com/tube0013/Smartcar-HA/issues).

[releases]: https://github.com/tube0013/Smartcar-HA/releases
[config-flow-start]: https://my.home-assistant.io/redirect/config_flow_start/?domain=smartcar
