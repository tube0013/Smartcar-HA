"""Smartcar dataclasses and typing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .auth import AbstractAuth

if TYPE_CHECKING:
    from .coordinator import SmartcarVehicleCoordinator


@dataclass(frozen=True, kw_only=True)
class SmartcarData:
    """The Smartcar coordinator runtime data."""

    auth: AbstractAuth
    coordinators: dict[str, SmartcarVehicleCoordinator]
    meta_coordinator: DataUpdateCoordinator


@dataclass
class SmartcarAPIError(Exception):
    """Error representing an issue via the Smartcar API."""

    code: int
    reason: str
