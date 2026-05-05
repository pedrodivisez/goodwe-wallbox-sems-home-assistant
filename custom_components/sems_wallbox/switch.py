"""Support for switch controlling an output of a GoodWe SEMS wallbox."""

from __future__ import annotations

import logging
import time

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONN_TYPE_MODBUS
from .coordinator import SemsUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SWITCH_VERSION = "0.3.4"

# How long after an ON command to ignore "Waiting/power=0" and keep optimistic ON (seconds)
GRACE_ON_SECONDS = 130

# How long after an OFF command to tolerate API still briefly showing power>0
GRACE_OFF_SECONDS = 130


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add switches for passed config_entry in HA."""
    runtime = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = runtime["coordinator"]
    conn_type = runtime.get("connection_type", "cloud")

    if conn_type == CONN_TYPE_MODBUS:
        client = runtime["modbus_client"]
        entities = []
        for sn in coordinator.data:
            entities.append(ModbusStartStopSwitch(coordinator, sn, client))
            entities.append(ModbusMaintainMinPowerSwitch(coordinator, sn, client))
            entities.append(ModbusPlugChargeSwitch(coordinator, sn, client))
            entities.append(ModbusDynamicLoadMgmtSwitch(coordinator, sn, client))
            entities.append(ModbusEmsDispatchSwitch(coordinator, sn, client))
        async_add_entities(entities)
        return

    api = runtime["api"]

    _LOGGER.debug(
        "Setting up SemsSwitch entities (version %s) for entry %s",
        SWITCH_VERSION,
        config_entry.entry_id,
    )

    entities: list[SemsSwitch] = []
    for sn, data in coordinator.data.items():
        start_status = data.get("startStatus")
        current_is_on = bool(start_status) if start_status is not None else False
        entities.append(SemsSwitch(coordinator, sn, api, current_is_on))
        entities.append(SemsMinimumPowerSwitch(coordinator, sn, api))

    async_add_entities(entities)


class SemsSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to start/stop charging."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "start_charging"

    def __init__(
        self,
        coordinator: SemsUpdateCoordinator,
        sn: str,
        api,
        current_is_on: bool,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.api = api
        self.sn = sn
        self._attr_is_on = current_is_on

        # Grace period tracking
        self._last_command_ts: float | None = None
        self._last_command_target: bool | None = None

        _LOGGER.debug(
            "Creating SemsSwitch (v%s) for Wallbox %s, initial is_on=%s",
            SWITCH_VERSION,
            self.sn,
            self._attr_is_on,
        )

    @property
    def device_class(self):
        """Return the device class."""
        return SwitchDeviceClass.SWITCH

    @property
    def unique_id(self) -> str:
        """Return unique id."""
        return f"{self.coordinator.data[self.sn]['sn']}-switch-start-charging"

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self.sn)},
            "name": (self.coordinator.data.get(self.sn, {}) or {}).get("name") or f"GoodWe Wallbox {self.sn}",
            "manufacturer": "GoodWe",
        }

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success

    def _compute_is_on_from_data(self, data: dict) -> bool:
        """Compute is_on from API data, respecting the grace period after commands."""
        # Primary signal: workStu=6 from getLastCharge (merged into coordinator data).
        # startStatus in /detail is unreliable -- always False in PV mode even when charging.
        work_status = data.get("last_charge_work_status")
        if work_status is not None:
            api_is_on = work_status == 6
        else:
            # Fallback: startStatus for Gen1 or when getLastCharge failed
            start_status = data.get("startStatus")
            if start_status is not None:
                api_is_on = bool(start_status)
            else:
                status = data.get("status")
                api_is_on = status == "EVDetail_Status_Title_Charging"
        status = data.get("status")

        now = self.hass.loop.time()
        target = self._last_command_target
        ts = self._last_command_ts

        # Within ON grace: keep optimistic ON even if API still shows not charging
        if (
            target is True
            and ts is not None
            and now - ts < GRACE_ON_SECONDS
            and not api_is_on
        ):
            _LOGGER.debug(
                "SemsSwitch %s: within ON grace (%.1fs < %.1fs), "
                "API status=%s, startStatus=%s -> holding is_on=True",
                self.sn,
                now - ts,
                GRACE_ON_SECONDS,
                status,
                data.get("startStatus"),
            )
            return True

        # Within OFF grace: keep optimistic OFF even if API briefly shows charging
        if (
            target is False
            and ts is not None
            and now - ts < GRACE_OFF_SECONDS
            and api_is_on
        ):
            _LOGGER.debug(
                "SemsSwitch %s: within OFF grace (%.1fs < %.1fs), "
                "API status=%s, startStatus=%s -> holding is_on=False",
                self.sn,
                now - ts,
                GRACE_OFF_SECONDS,
                status,
                data.get("startStatus"),
            )
            return False

        # Outside grace period or state already matches command
        if target is not None and api_is_on == target:
            self._last_command_target = None
            self._last_command_ts = None

        _LOGGER.debug(
            "SemsSwitch %s: API status=%s, startStatus=%s -> is_on=%s (no grace override)",
            self.sn,
            status,
            data.get("startStatus"),
            api_is_on,
        )
        return api_is_on

    async def async_turn_off(self, **kwargs):
        """Turn off charging."""
        _LOGGER.debug("Wallbox %s set to Off (optimistic UI + OFF grace)", self.sn)

        self._last_command_target = False
        self._last_command_ts = self.hass.loop.time()

        # Optimistic state update
        self._attr_is_on = False
        self.async_write_ha_state()

        # Optimistic immediate refresh, then a confirmed one 5 s after the command
        self.hass.async_create_task(self.coordinator.async_request_refresh())

        # Send command to SEMS API
        await self.hass.async_add_executor_job(self.api.change_status_gen2, self.sn, "stop")
        self.coordinator.schedule_delayed_refresh(5)

    async def async_turn_on(self, **kwargs):
        """Turn on charging."""
        _LOGGER.debug("Wallbox %s set to On (optimistic UI + ON grace)", self.sn)

        self._last_command_target = True
        self._last_command_ts = self.hass.loop.time()

        # Optimistic state update
        self._attr_is_on = True
        self.async_write_ha_state()

        # Optimistic immediate refresh, then a confirmed one 5 s after the command
        self.hass.async_create_task(self.coordinator.async_request_refresh())

        # Send command to SEMS API
        await self.hass.async_add_executor_job(self.api.change_status_gen2, self.sn, "start")
        self.coordinator.schedule_delayed_refresh(5)

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.debug("SemsSwitch added to hass for wallbox %s", self.sn)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data = self.coordinator.data.get(self.sn, {}) or {}
        self._attr_is_on = self._compute_is_on_from_data(data)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Manual update from HA."""
        await self.coordinator.async_request_refresh()
        data = self.coordinator.data.get(self.sn, {}) or {}
        self._attr_is_on = self._compute_is_on_from_data(data)
        self.async_write_ha_state()


class SemsMinimumPowerSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable 'ensure minimum charging power' in PV priority mode.

    When enabled, the wallbox guarantees a minimum charge current from the grid
    even when PV production is insufficient. Only relevant in PV priority mode (mode=1);
    the entity is unavailable in other modes.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "ensure_minimum_charging_power"
    _attr_entity_category = EntityCategory.CONFIG

    # How long to hold the pending (optimistic) state while waiting for API to apply.
    # set-mode can take up to 90 s; use 120 s to be safe.
    _PENDING_TIMEOUT = 120.0

    def __init__(self, coordinator: SemsUpdateCoordinator, sn: str, api) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.api = api
        self.sn = sn
        # Pending state: set while we wait for the API to confirm the command.
        # Prevents coordinator polls from reverting the optimistic UI state.
        self._pending_state: bool | None = None
        self._pending_set_at: float = 0.0
        _LOGGER.debug("Creating SemsMinimumPowerSwitch for wallbox %s", self.sn)

    @property
    def unique_id(self) -> str:
        return f"{self.sn}-switch-ensure-minimum-power"

    @property
    def device_info(self):
        data = self.coordinator.data.get(self.sn, {}) or {}
        return {
            "identifiers": {(DOMAIN, self.sn)},
            "name": data.get("name") or f"GoodWe Wallbox {self.sn}",
            "manufacturer": "GoodWe",
        }

    @property
    def available(self) -> bool:
        """Available in PV priority (mode 1) and PV & battery (mode 2)."""
        if not self.coordinator.last_update_success:
            return False
        data = self.coordinator.data.get(self.sn, {}) or {}
        return data.get("chargeMode") in (1, 2)

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data.get(self.sn, {}) or {}
        api_val = bool(data.get("ensure_minimum_charging_power", False))
        if self._pending_state is not None:
            if time.monotonic() - self._pending_set_at >= self._PENDING_TIMEOUT:
                # Timeout expired -- stop holding
                self._pending_state = None
            elif api_val == self._pending_state:
                # API confirmed our command
                self._pending_state = None
            else:
                # Still waiting -- show pending state to prevent flicker
                return self._pending_state
        return api_val

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        """Enable minimum charging power guarantee."""
        _LOGGER.debug("SemsMinimumPowerSwitch %s: turning ON", self.sn)
        self._pending_state = True
        self._pending_set_at = time.monotonic()
        self.async_write_ha_state()
        ok = await self.hass.async_add_executor_job(
            self.api.set_charge_mode_gen2,
            self.sn,
            1,  # PV priority
            None,
            True,  # ensure_minimum_charging_power
        )
        if not ok:
            _LOGGER.warning("SemsMinimumPowerSwitch %s: turn ON failed", self.sn)
            self._pending_state = None
            self.async_write_ha_state()
        self.coordinator.schedule_delayed_refresh(5.0)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable minimum charging power guarantee."""
        _LOGGER.debug("SemsMinimumPowerSwitch %s: turning OFF", self.sn)
        self._pending_state = False
        self._pending_set_at = time.monotonic()
        self.async_write_ha_state()
        ok = await self.hass.async_add_executor_job(
            self.api.set_charge_mode_gen2,
            self.sn,
            1,  # PV priority
            None,
            False,  # ensure_minimum_charging_power
        )
        if not ok:
            _LOGGER.warning("SemsMinimumPowerSwitch %s: turn OFF failed", self.sn)
            self._pending_state = None
            self.async_write_ha_state()
        self.coordinator.schedule_delayed_refresh(5.0)


# ---------------------------------------------------------------------------
# Modbus-specific switch entities (local Modbus TCP mode only)
# ---------------------------------------------------------------------------

_MODBUS_PENDING_TIMEOUT = 30.0


class _ModbusSwitch(CoordinatorEntity, SwitchEntity):
    """Base class for Modbus-backed boolean controls.

    Subclasses provide unique_id, translation_key, _api_state(), _do_write().
    """

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator, sn: str, client) -> None:
        super().__init__(coordinator)
        self.sn = sn
        self._client = client
        self._pending_state: bool | None = None
        self._pending_set_at: float = 0.0

    @property
    def device_info(self):
        data = self.coordinator.data.get(self.sn, {}) or {}
        return {
            "identifiers": {(DOMAIN, self.sn)},
            "name": data.get("name") or f"GoodWe Wallbox {self.sn}",
            "manufacturer": "GoodWe",
        }

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    def _api_state(self) -> bool:
        raise NotImplementedError

    def _do_write(self, state: bool) -> bool:
        raise NotImplementedError

    @property
    def is_on(self) -> bool:
        api_val = self._api_state()
        if self._pending_state is not None:
            if time.monotonic() - self._pending_set_at >= _MODBUS_PENDING_TIMEOUT:
                self._pending_state = None
            elif api_val == self._pending_state:
                self._pending_state = None
            else:
                return self._pending_state
        return api_val

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def _async_set(self, state: bool) -> None:
        self._pending_state = state
        self._pending_set_at = time.monotonic()
        self.async_write_ha_state()
        ok = await self.hass.async_add_executor_job(self._do_write, state)
        if not ok:
            _LOGGER.warning("%s: write failed, reverting optimistic state", self.unique_id)
            self._pending_state = None
            self.async_write_ha_state()
        else:
            self.coordinator.schedule_delayed_refresh(3.0)

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set(False)


class ModbusStartStopSwitch(_ModbusSwitch):
    """Start / stop charging via Modbus (reg 10060: 2=on, 1=off)."""

    _attr_translation_key = "modbus_start_charging"

    @property
    def unique_id(self) -> str:
        return f"{self.sn}_modbus_start_stop"

    def _api_state(self) -> bool:
        data = self.coordinator.data.get(self.sn, {}) or {}
        v = data.get("modbus_charging_enabled")
        # Fallback: status==3 (charging) implies on
        if v is None:
            return (data.get("modbus_status_raw") == 3)
        return bool(v)

    def _do_write(self, state: bool) -> bool:
        return self._client.write_start_stop(state)


class ModbusMaintainMinPowerSwitch(_ModbusSwitch):
    """Enable / disable maintain minimum charging power (reg 10024)."""

    _attr_translation_key = "modbus_maintain_min_power"
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def unique_id(self) -> str:
        return f"{self.sn}_modbus_maintain_min_power"

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success:
            return False
        data = self.coordinator.data.get(self.sn, {}) or {}
        return data.get("chargeMode") in (1, 2)

    def _api_state(self) -> bool:
        data = self.coordinator.data.get(self.sn, {}) or {}
        return bool(data.get("ensure_minimum_charging_power", False))

    def _do_write(self, state: bool) -> bool:
        return self._client.write_maintain_min_power(state)


class ModbusPlugChargeSwitch(_ModbusSwitch):
    """Enable / disable Plug & Charge function (reg 10019)."""

    _attr_translation_key = "modbus_plug_charge"
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def unique_id(self) -> str:
        return f"{self.sn}_modbus_plug_charge"

    def _api_state(self) -> bool:
        data = self.coordinator.data.get(self.sn, {}) or {}
        return bool(data.get("modbus_plug_charge_enabled", False))

    def _do_write(self, state: bool) -> bool:
        return self._client.write_plug_charge(state)


class ModbusDynamicLoadMgmtSwitch(_ModbusSwitch):
    """Enable / disable dynamic load management (reg 10025)."""

    _attr_translation_key = "modbus_dynamic_load"
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def unique_id(self) -> str:
        return f"{self.sn}_modbus_dynamic_load"

    def _api_state(self) -> bool:
        data = self.coordinator.data.get(self.sn, {}) or {}
        return bool(data.get("modbus_dynamic_load", False))

    def _do_write(self, state: bool) -> bool:
        return self._client.write_dynamic_load_mgmt(state)


class ModbusEmsDispatchSwitch(_ModbusSwitch):
    """EMS minimum power dispatch mode (reg 10000: 0=normal, 1=min-power)."""

    _attr_translation_key = "modbus_ems_dispatch"
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def unique_id(self) -> str:
        return f"{self.sn}_modbus_ems_dispatch"

    def _api_state(self) -> bool:
        data = self.coordinator.data.get(self.sn, {}) or {}
        return data.get("modbus_ems_dispatch", 0) == 1

    def _do_write(self, state: bool) -> bool:
        return self._client.write_ems_dispatch(state)
