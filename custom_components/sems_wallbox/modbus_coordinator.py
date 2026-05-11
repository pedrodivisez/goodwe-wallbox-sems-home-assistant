"""DataUpdateCoordinator for the GoodWe Wallbox Gen2 via local Modbus TCP."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_STATION_ID,
    DEFAULT_SCAN_INTERVAL_IDLE,
    DEFAULT_SCAN_INTERVAL_CHARGING,
    CONF_SCAN_INTERVAL_CHARGING,
)
from .wallbox_modbus import WallboxModbusClient

_LOGGER = logging.getLogger(__name__)


class ModbusUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate fetching data from the wallbox directly via Modbus TCP."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: WallboxModbusClient,
    ) -> None:
        self._client = client
        self._station_id: str = entry.data[CONF_STATION_ID]

        self._interval_idle = int(entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_IDLE),
        ))
        self._interval_charging = int(entry.options.get(
            CONF_SCAN_INTERVAL_CHARGING,
            DEFAULT_SCAN_INTERVAL_CHARGING,
        ))

        self._pending_refresh_cancel = None

        super().__init__(
            hass,
            _LOGGER,
            name="Modbus wallbox",
            update_interval=timedelta(seconds=self._interval_idle),
        )

    def schedule_delayed_refresh(self, delay: float = 3.0) -> None:
        """Schedule a one-shot coordinator refresh after `delay` seconds."""
        if self._pending_refresh_cancel is not None:
            self._pending_refresh_cancel()
            self._pending_refresh_cancel = None

        @callback
        def _do_refresh(_now):
            self._pending_refresh_cancel = None
            self.hass.async_create_task(self.async_request_refresh())

        self._pending_refresh_cancel = async_call_later(self.hass, delay, _do_refresh)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the wallbox via Modbus TCP."""
        try:
            result = await self.hass.async_add_executor_job(self._client.read_all)
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Modbus read error: {err}") from err

        if result is None:
            raise UpdateFailed("No data received from Modbus -- check wallbox connectivity")

        sn = result.get("sn") or self._station_id
        if not sn:
            raise UpdateFailed("Could not determine SN from Modbus data")

        data: dict[str, Any] = {sn: result}
        _LOGGER.debug(
            "Modbus %s: status=%s power=%.1f on_off=%s car=%s cp=%s start=%s",
            sn,
            result.get("modbus_status_name"),
            result.get("modbus_power") or 0.0,
            result.get("modbus_charging_on_off"),
            result.get("modbus_car_connected"),
            result.get("modbus_cp_state_name"),
            result.get("modbus_start_mode"),
        )

        # Dynamic polling: faster while actively charging
        is_charging = result.get("modbus_status_raw") == 3
        new_interval = timedelta(
            seconds=self._interval_charging if is_charging else self._interval_idle
        )
        if new_interval != self.update_interval:
            self.update_interval = new_interval
            _LOGGER.debug("Modbus coordinator polling interval -> %ss (charging=%s)",
                          int(new_interval.total_seconds()), is_charging)

        return data
