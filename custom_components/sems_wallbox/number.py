"""Support for number entity controlling GoodWe SEMS Wallbox charge power."""

from __future__ import annotations

import logging
import time

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONN_TYPE_MODBUS
from .coordinator import SemsUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

NUMBER_VERSION = "0.3.2"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add numbers for passed config_entry in HA."""
    runtime = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = runtime["coordinator"]
    conn_type = runtime.get("connection_type", "cloud")

    if conn_type == CONN_TYPE_MODBUS:
        client = runtime["modbus_client"]
        entities = []
        for sn in coordinator.data:
            entities.append(ModbusMaxChargePowerNumber(coordinator, sn, client))
            entities.append(ModbusMaxChargeCapacityNumber(coordinator, sn, client))
            entities.append(ModbusMinChargeCapacityNumber(coordinator, sn, client))
            entities.append(ModbusBatteryDischargeSocNumber(coordinator, sn, client))
        async_add_entities(entities)
        return

    api = runtime["api"]

    _LOGGER.debug(
        "Setting up SemsNumber entities (version %s) for entry %s",
        NUMBER_VERSION,
        config_entry.entry_id,
    )

    entities: list[SemsNumber] = []
    for sn, data in coordinator.data.items():
        set_charge_power = data.get("set_charge_power")
        entities.append(SemsNumber(coordinator, sn, api, set_charge_power))

    async_add_entities(entities)


class SemsNumber(CoordinatorEntity, NumberEntity):
    """Number entity for setting wallbox charge power."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "charge_power"

    def __init__(self, coordinator: SemsUpdateCoordinator, sn: str, api, value: float):
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.api = api
        self.sn = sn
        self._attr_native_value = float(value) if value is not None else None
        # Grace period tracking: ignore stale coordinator updates after a set
        self._pending_value: float | None = None
        self._pending_until: float = 0.0
        _LOGGER.debug(
            "Creating SemsNumber (v%s) for Wallbox %s, initial value=%s",
            NUMBER_VERSION,
            self.sn,
            self._attr_native_value,
        )

    @property
    def device_class(self):
        """Return the device class."""
        return NumberDeviceClass.POWER

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return UnitOfPower.KILO_WATT

    @property
    def native_step(self):
        """Return the step value."""
        return 0.1

    def _model_limits(self) -> tuple[float, float]:
        """Return (min_kW, max_kW) as fallback based on product model string.

        Per-model defaults when API doesn't return min/max:
          GW7  → 1.4 -  7.0 kW
          GW11 → 4.2 - 11.0 kW
          GW22 → 4.2 - 22.0 kW
        Defaults to GW7 range when model is unknown (smallest / safest).
        """
        model = ((self.coordinator.data.get(self.sn, {}) or {}).get("model") or "").upper()
        if "GW22" in model:
            return 4.2, 22.0
        if "GW11" in model:
            return 4.2, 11.0
        if "GW7" in model:
            return 1.4, 7.0
        return 1.4, 7.0  # safe default (smallest model)

    @property
    def native_min_value(self) -> float:
        """Return the minimum value, read from API data when available."""
        data = self.coordinator.data.get(self.sn, {}) or {}
        v = data.get("min_charge_power")
        try:
            return float(v) if v is not None else self._model_limits()[0]
        except (TypeError, ValueError):
            return self._model_limits()[0]

    @property
    def native_max_value(self) -> float:
        """Return the maximum value, read from API data when available."""
        data = self.coordinator.data.get(self.sn, {}) or {}
        v = data.get("max_charge_power")
        try:
            return float(v) if v is not None else self._model_limits()[1]
        except (TypeError, ValueError):
            return self._model_limits()[1]

    @property
    def unique_id(self) -> str:
        """Return unique id."""
        return f"{self.coordinator.data[self.sn]['sn']}_number_set_charge_power"

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self.sn)},
            "name": (self.coordinator.data.get(self.sn, {}) or {}).get("name") or f"GoodWe Wallbox {self.sn}",
            "manufacturer": "GoodWe",
        }

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
        _LOGGER.debug("SemsNumber added to hass for wallbox %s", self.sn)

    @property
    def available(self) -> bool:
        """Always available -- entity is editable only in Fast mode (chargeMode=0)."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict:
        """Expose whether the slider is currently editable."""
        data = self.coordinator.data.get(self.sn, {}) or {}
        return {"editable": data.get("chargeMode", 0) == 0}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data = self.coordinator.data.get(self.sn, {}) or {}
        set_charge_power = data.get("set_charge_power")

        # Grace period: after a set, ignore stale API values until device catches up
        now = time.monotonic()
        if self._pending_value is not None and now < self._pending_until:
            if set_charge_power is not None:
                try:
                    if abs(float(set_charge_power) - self._pending_value) < 0.05:
                        self._pending_value = None
                        self._attr_native_value = float(set_charge_power)
                    # else: still stale -- keep _attr_native_value at pending value
                except (TypeError, ValueError):
                    pass
        else:
            # Grace expired or no pending set -- always accept the API value
            if self._pending_value is not None:
                self._pending_value = None
            if set_charge_power is not None:
                try:
                    self._attr_native_value = float(set_charge_power)
                except (TypeError, ValueError):
                    _LOGGER.warning(
                        "SemsNumber %s: invalid set_charge_power value %r from API",
                        self.sn,
                        set_charge_power,
                    )

        _LOGGER.debug(
            "SemsNumber coordinator update SN=%s -> native_value=%s, available=%s",
            self.sn,
            self._attr_native_value,
            self.available,
        )
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Manual update from HA."""
        await self.coordinator.async_request_refresh()

    async def async_set_native_value(self, value: float) -> None:
        """Handle change from UI slider -- switches to Fast mode (0) with the given power."""
        _LOGGER.debug(
            "Setting set_charge_power for SN=%s to %s",
            self.sn,
            value,
        )

        # 1) Optimistic UI update -- also write the new power directly into
        # coordinator.data (without going through async_set_updated_data) so
        # that an in-flight select.py mode-switch call can detect it after its
        # own API call finishes and re-send with the correct power.
        # We deliberately avoid async_set_updated_data here: calling it would
        # trigger _handle_coordinator_update on the select entity, which could
        # see the optimistically-written chargeMode and prematurely clear
        # _pending_mode -- causing the very revert we are trying to prevent.
        old_value = self._attr_native_value  # save before optimistic write for failure revert
        self._attr_native_value = float(value)
        # Start grace period immediately so coordinator updates during the API
        # call (which can take several seconds) don't revert the optimistic value.
        self._pending_value = float(value)
        self._pending_until = time.monotonic() + 120.0
        device = self.coordinator.data.get(self.sn)
        if device is not None:
            device["set_charge_power"] = float(value)
        self.async_write_ha_state()

        # 2) Call SEMS API -- always Fast mode (0)
        ok = await self.hass.async_add_executor_job(
            self.api.set_charge_mode_gen2,
            self.sn,
            0,
            value,
            None,  # ensure_minimum_charging_power
        )

        if not ok:
            # API call failed -- revert optimistic value and coordinator.data
            # so the slider goes back to whatever the device actually has.
            # But only revert if still in Fast mode (entity available): if the mode
            # has already switched to PV while this call was in flight, we must NOT
            # overwrite the preserved PV power value -- the user set 11 kW and we
            # should remember it for the next switch back to Fast.
            _LOGGER.warning(
                "set_charge_mode failed for %s (power=%s), reverting optimistic value",
                self.sn,
                value,
            )
            if old_value is not None and self.coordinator.data.get(self.sn, {}).get("chargeMode", 0) == 0:
                self._attr_native_value = old_value
                self._pending_value = None  # revert cancels grace
                self._pending_until = 0.0
                device = self.coordinator.data.get(self.sn)
                if device is not None:
                    device["set_charge_power"] = old_value
                self.async_write_ha_state()
            self.hass.async_create_task(self.coordinator.async_request_refresh())
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_charge_power_failed",
                translation_placeholders={"value": str(value)},
            )

        # 3) Schedule a delayed refresh to confirm state from the API.
        # set-mode can take up to 90s to return, then device needs more time to apply.
        # Poll 60s after set-mode returns (total from user action up to ~150s).
        self.coordinator.schedule_delayed_refresh(60)


# ---------------------------------------------------------------------------
# Modbus-specific number entities (local Modbus TCP mode only)
# ---------------------------------------------------------------------------

class _ModbusNumber(CoordinatorEntity, NumberEntity):
    """Base class for Modbus-backed numeric controls."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_mode = "box"

    def __init__(self, coordinator, sn: str, client) -> None:
        super().__init__(coordinator)
        self.sn = sn
        self._client = client
        self._pending_value: float | None = None
        self._pending_until: float = 0.0

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

    def _api_value(self) -> float | None:
        raise NotImplementedError

    def _do_write(self, value: float) -> bool:
        raise NotImplementedError

    @property
    def native_value(self) -> float | None:
        api_val = self._api_value()
        now = time.monotonic()
        if self._pending_value is not None:
            if now >= self._pending_until:
                self._pending_value = None
            elif api_val is not None and abs(api_val - self._pending_value) < 0.05:
                self._pending_value = None
            else:
                return self._pending_value
        return api_val

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        self._pending_value = value
        self._pending_until = time.monotonic() + 30.0
        self.async_write_ha_state()
        ok = await self.hass.async_add_executor_job(self._do_write, value)
        if not ok:
            _LOGGER.warning("%s: write failed, reverting optimistic value", self.unique_id)
            self._pending_value = None
            self.async_write_ha_state()
        else:
            self.coordinator.schedule_delayed_refresh(3.0)


class ModbusMaxChargePowerNumber(_ModbusNumber):
    """Max charge power limit in kW (reg 10029, SF=10)."""

    _attr_translation_key = "modbus_charge_power"
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_native_step = 0.1
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def unique_id(self) -> str:
        return f"{self.sn}_modbus_max_charge_power"

    def _power_limits(self) -> tuple[float, float]:
        data = self.coordinator.data.get(self.sn, {}) or {}
        spec = data.get("modbus_power_spec")
        if spec == 2:
            return 4.2, 22.0
        if spec == 1:
            return 4.2, 11.0
        return 1.4, 7.0

    @property
    def native_min_value(self) -> float:
        return self._power_limits()[0]

    @property
    def native_max_value(self) -> float:
        return self._power_limits()[1]

    def _api_value(self) -> float | None:
        data = self.coordinator.data.get(self.sn, {}) or {}
        v = data.get("modbus_max_charging_power")
        return round(float(v), 1) if v is not None else None

    def _do_write(self, value: float) -> bool:
        return self._client.write_max_charge_power(value)

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success:
            return False
        data = self.coordinator.data.get(self.sn, {}) or {}
        return data.get("chargeMode") == 0  # Fast mode only


class ModbusMaxChargeCapacityNumber(_ModbusNumber):
    """Max session energy limit in kWh (reg 10027, SF=10). 0 = unlimited."""

    _attr_translation_key = "modbus_max_capacity"
    _attr_device_class = NumberDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_native_min_value = 0.0
    _attr_native_max_value = 200.0
    _attr_native_step = 0.1
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def unique_id(self) -> str:
        return f"{self.sn}_modbus_max_capacity"

    def _api_value(self) -> float | None:
        data = self.coordinator.data.get(self.sn, {}) or {}
        v = data.get("modbus_max_capacity")
        return round(float(v), 1) if v is not None else None

    def _do_write(self, value: float) -> bool:
        return self._client.write_max_charge_capacity(value)


class ModbusMinChargeCapacityNumber(_ModbusNumber):
    """Min session energy target in kWh (reg 10028, SF=10). 0 = no minimum."""

    _attr_translation_key = "modbus_min_capacity"
    _attr_device_class = NumberDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_native_min_value = 0.0
    _attr_native_max_value = 200.0
    _attr_native_step = 0.1
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def unique_id(self) -> str:
        return f"{self.sn}_modbus_min_capacity"

    def _api_value(self) -> float | None:
        data = self.coordinator.data.get(self.sn, {}) or {}
        v = data.get("modbus_min_capacity")
        return round(float(v), 1) if v is not None else None

    def _do_write(self, value: float) -> bool:
        return self._client.write_min_charge_capacity(value)

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success:
            return False
        data = self.coordinator.data.get(self.sn, {}) or {}
        return data.get("chargeMode") in (1, 2)  # PV and PV+battery modes


class ModbusBatteryDischargeSocNumber(_ModbusNumber):
    """Battery discharge SOC threshold in % (reg 10030). Used in PV+battery mode."""

    _attr_translation_key = "modbus_bat_soc_limit"
    _attr_native_unit_of_measurement = "%"
    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 1.0
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def unique_id(self) -> str:
        return f"{self.sn}_modbus_bat_soc_limit"

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success:
            return False
        data = self.coordinator.data.get(self.sn, {}) or {}
        return data.get("chargeMode") in (0, 2)  # Fast and PV+battery modes

    def _api_value(self) -> float | None:
        data = self.coordinator.data.get(self.sn, {}) or {}
        v = data.get("modbus_bat_soc_limit")
        return float(v) if v is not None else None

    def _do_write(self, value: float) -> bool:
        return self._client.write_battery_discharge_soc(int(value))
