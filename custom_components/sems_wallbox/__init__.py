"""The sems_wallbox integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    CONF_PLANT_ID,
    CONF_PRODUCT_MODEL,
    CONF_STATION_ID,
    CONF_CONNECTION_TYPE,
    CONN_TYPE_MODBUS,
    CONF_MODBUS_HOST,
    CONF_MODBUS_PORT,
    CONF_MODBUS_DEVICE_ID,
    DEFAULT_MODBUS_PORT,
    DEFAULT_MODBUS_DEVICE_ID,
)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
from .sems_api import SemsApi
from .coordinator import SemsUpdateCoordinator
from .modbus_coordinator import ModbusUpdateCoordinator
from .wallbox_modbus import WallboxModbusClient

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the sems component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up sems from a config entry."""
    conn_type = entry.data.get(CONF_CONNECTION_TYPE, "cloud")

    if conn_type == CONN_TYPE_MODBUS:
        return await _async_setup_modbus(hass, entry)
    return await _async_setup_cloud(hass, entry)


async def _async_setup_modbus(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration using local Modbus TCP."""
    host = entry.data[CONF_MODBUS_HOST]
    port = int(entry.data.get(CONF_MODBUS_PORT, DEFAULT_MODBUS_PORT))
    device_id = int(entry.data.get(CONF_MODBUS_DEVICE_ID, DEFAULT_MODBUS_DEVICE_ID))

    client = WallboxModbusClient(host, port, device_id)
    coordinator = ModbusUpdateCoordinator(hass, entry, client)

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "modbus_client": client,
        "connection_type": CONN_TYPE_MODBUS,
    }

    entry.async_on_unload(entry.add_update_listener(update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_setup_cloud(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration using the SEMS cloud API (original path)."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    api = SemsApi(hass, username, password)

    # Configure gen2 (SEMS Plus) plant info from options/data if provided.
    # strip() + or None so empty-string values from the OptionsFlow are treated as unset.
    plant_id = (entry.options.get(CONF_PLANT_ID) or entry.data.get(CONF_PLANT_ID) or "").strip() or None
    product_model = (entry.options.get(CONF_PRODUCT_MODEL) or entry.data.get(CONF_PRODUCT_MODEL) or "").strip() or None
    _LOGGER.debug(
        "SEMS setup: plant_id=%r product_model=%r (from options=%r data=%r)",
        plant_id,
        product_model,
        entry.options,
        {k: v for k, v in entry.data.items() if k not in (CONF_PASSWORD,)},
    )
    api.configure_gen2(plant_id, product_model)

    # If model wasn't known at config time, try to fetch it from the EU gateway.
    if plant_id and not product_model:
        station_id = entry.data.get(CONF_STATION_ID) or entry.options.get(CONF_STATION_ID) or ""
        if station_id:
            info = await hass.async_add_executor_job(api.fetch_device_info, station_id)
            discovered_model = (info.get("productModel") or "").strip() or None
            if discovered_model:
                _LOGGER.debug("SEMS setup: auto-discovered model=%r for sn=%r", discovered_model, station_id)
                api.configure_gen2(plant_id, discovered_model)

    coordinator = SemsUpdateCoordinator(hass, entry, api)

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    # Reload on options change (e.g. scan_interval)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle options update (e.g. scan_interval change)."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
            ]
        )
    )
    if unload_ok:
        runtime = hass.data[DOMAIN].pop(entry.entry_id, {})
        modbus_client = runtime.get("modbus_client")
        if modbus_client is not None:
            await hass.async_add_executor_job(modbus_client.close)

    return unload_ok
