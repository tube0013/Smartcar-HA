# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Smartcar-HA is a Home Assistant custom integration that connects vehicles to Home Assistant using the Smartcar API. It provides sensors, binary sensors, device trackers, locks, switches, and number entities for monitoring and controlling connected vehicles.

## Commands

### Testing
```bash
# Run all tests
pytest -p no:sugar

# Run with coverage
pytest --cov=custom_components/smartcar --cov-report=html

# Run a single test file
pytest tests/test_sensor.py

# Run a specific test
pytest tests/test_sensor.py::test_battery_level_sensor -v
```

### Linting and Formatting
```bash
# Run all pre-commit hooks
pre-commit run --all-files

# Ruff linting
ruff check custom_components/smartcar tests

# Ruff formatting
ruff format custom_components/smartcar tests

# Type checking
mypy custom_components/smartcar

# Spell checking
codespell custom_components/smartcar tests
```

### Install Dependencies
```bash
pip install -r requirements.test.txt
pre-commit install
```

## Architecture

### Core Components

- **`coordinator.py`** - `SmartcarVehicleCoordinator` manages data fetching from Smartcar v2 and v3 APIs. Uses `DatapointConfig` to define each data point's polling behavior. `DATAPOINT_ENTITY_KEY_MAP` maps ~30 entity types to API endpoints.

- **`entity.py`** - Base `SmartcarEntity` class that all platform entities inherit. Implements state restoration, error handling, and data age tracking.

- **`config_flow.py`** - OAuth2 configuration flow using Home Assistant's application credentials framework.

- **`webhooks.py`** - Real-time webhook support for v3 API. Handles webhook registration, verification, and event processing.

### Entity Platforms

Six platforms in `custom_components/smartcar/`:
- `sensor.py` - Battery, charging, fuel, tire pressure, odometer, range
- `binary_sensor.py` - Door/window/trunk states, charging status, online status
- `device_tracker.py` - GPS location
- `lock.py` - Door lock control
- `switch.py` - Charging control
- `number.py` - Charge limit adjustment

### Data Flow

1. OAuth2 authentication via Smartcar Connect
2. `SmartcarVehicleCoordinator` polls v2/v3 APIs (default: 6-hour interval)
3. Webhooks provide real-time updates when configured
4. Entities subscribe to coordinator updates
5. Batch API calls group requests to reduce quota usage

### Key Patterns

- **Coordinator pattern** - All entities use `DataUpdateCoordinator` for efficient polling
- **RestoreEntity** - State persists across Home Assistant restarts
- **Permissions-based entity creation** - Entities created based on granted OAuth scopes

## Testing

Tests use `pytest-homeassistant-custom-component` for Home Assistant test fixtures. Snapshot testing via `syrupy` for entity state verification.

Test fixtures in `tests/fixtures/` contain sample API responses.

## Configuration

- `pyproject.toml` - Python/mypy/ruff configuration
- `.pre-commit-config.yaml` - Pre-commit hooks
- `custom_components/smartcar/manifest.json` - Home Assistant integration manifest
