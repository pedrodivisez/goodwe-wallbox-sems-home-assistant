"""Support for wallbox sensors from GoodWe SEMS API."""

from __future__ import annotations

from decimal import Decimal
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfElectricCurrent, UnitOfElectricPotential, UnitOfEnergy, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONN_TYPE_MODBUS
from .coordinator import SemsUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    runtime: dict[str, Any] = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: SemsUpdateCoordinator = runtime["coordinator"]
    conn_type = runtime.get("connection_type", "cloud")

    sns = list(coordinator.data.keys())

    entities: list[SensorEntity] = []
    for sn in sns:
        entities.append(SemsSensor(coordinator, sn))
        entities.append(SemsWorkStateSensor(coordinator, sn))
        entities.append(SemsStatisticsSensor(coordinator, sn))
        entities.append(SemsPowerSensor(coordinator, sn))
        entities.append(SemsChargePowerLimitSensor(coordinator, sn))
        entities.append(SemsChargeDurationSensor(coordinator, sn))
        # Add Modbus-specific sensors when running in local Modbus mode
        if conn_type == CONN_TYPE_MODBUS:
            entities.extend([
                SemsModbusVoltageSensor(coordinator, sn, "a"),
                SemsModbusVoltageSensor(coordinator, sn, "b"),
                SemsModbusVoltageSensor(coordinator, sn, "c"),
                SemsModbusCurrentSensor(coordinator, sn, "a"),
                SemsModbusCurrentSensor(coordinator, sn, "b"),
                SemsModbusCurrentSensor(coordinator, sn, "c"),
                SemsModbusEnergyTotalSensor(coordinator, sn),
                SemsModbusStatusSensor(coordinator, sn),
                SemsModbusCarConnectionSensor(coordinator, sn),
                SemsModbusFaultSensor(coordinator, sn),
            ])

    async_add_entities(entities)


class SemsSensor(CoordinatorEntity, SensorEntity):
    """Main wallbox status sensor (Charging / Standby / Offline / Unknown)."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["charging", "standby", "offline", "unknown"]
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "status"

    def __init__(self, coordinator: SemsUpdateCoordinator, sn: str) -> None:
        """Initialize the status sensor."""
        super().__init__(coordinator)
        self.sn = sn
        _LOGGER.debug("Creating SemsSensor with id %s", self.sn)

    @property
    def unique_id(self) -> str:
        """Unique ID based on serial number."""
        return self.coordinator.data.get(self.sn, {}).get("sn", self.sn)

    @property
    def state(self) -> str:
        """Return the state of the device as human readable string."""
        data = self.coordinator.data.get(self.sn, {})
        # workStu=6 from getLastCharge is the authoritative charging signal.
        # The detail endpoint's status field is always 'available' in PV mode.
        if data.get("last_charge_work_status") == 6:
            return "charging"
        status = data.get("status")
        # Gen2 EU gateway values
        if status in ("EVDetail_Status_Title_Charging", "charging"):
            return "charging"
        if status in ("EVDetail_Status_Title_Waiting", "available", "standby"):
            return "standby"
        if status in ("EVDetail_Status_Title_Offline", "offline", "unavailable"):
            return "offline"
        return "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return meaningful state attributes."""
        data = self.coordinator.data.get(self.sn, {}) or {}
        attrs: dict[str, Any] = {}
        # Raw status string for display / automations
        if data.get("status"):
            attrs["statusText"] = data["status"]
        # Scheduling
        for key in ("chargeMode", "scheduleMode", "schedule_total_minute"):
            if (v := data.get(key)) is not None:
                attrs[key] = v
        # Power management
        for key in ("set_charge_power", "charge_from_grid", "ensure_minimum_charging_power"):
            if (v := data.get(key)) is not None:
                attrs[key] = v
        # Last charge session (from getLastCharge)
        for key in ("last_charge_work_status", "last_charge_power", "last_charge_duration_minutes"):
            if (v := data.get(key)) is not None:
                attrs[key] = v
        return attrs

    @property
    def icon(self) -> str:
        """Return dynamic icon based on status."""
        state = self.state
        if state == "charging":
            return "mdi:battery-charging-100"
        if state == "standby":
            return "mdi:ev-station"
        if state == "offline":
            return "mdi:power-plug-off"
        return "mdi:help-circle-outline"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> dict[str, Any]:
        data = self.coordinator.data.get(self.sn, {}) or {}
        return {
            "identifiers": {(DOMAIN, self.sn)},
            "name": data.get("name") or f"GoodWe Wallbox {self.sn}",
            "manufacturer": "GoodWe",
            "model": data.get("model", "unknown"),
            "sw_version": data.get("fireware", "unknown"),
        }

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

    async def async_update(self) -> None:
        """Update the entity via the coordinator."""
        await self.coordinator.async_request_refresh()


class SemsWorkStateSensor(CoordinatorEntity, SensorEntity):
    """Workstate sensor for the wallbox EV plug state."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["not_plugged_in", "connected", "finished_charging", "charged", "dash", "unknown"]
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "workstate"

    def __init__(self, coordinator: SemsUpdateCoordinator, sn: str) -> None:
        """Initialize the workstate sensor."""
        super().__init__(coordinator)
        self.sn = sn
        _LOGGER.debug("Creating SemsWorkStateSensor with id %s", self.sn)

    @property
    def unique_id(self) -> str:
        """Unique ID for workstate sensor."""
        sn = self.coordinator.data.get(self.sn, {}).get("sn", self.sn)
        return f"{sn}_workstate"

    @property
    def native_value(self) -> str:
        """Return the workstate of the device as a human-readable string."""
        data = self.coordinator.data.get(self.sn, {})
        last_status = data.get("last_charge_work_status")
        # last_charge_work_status is more reliable than the detail API workstate field.
        # workStu=6 → actively charging (vehicle connected and drawing power)
        # workStu=8 → session finished (vehicle still connected, not drawing power)
        if last_status == 6:
            return "connected"
        if last_status == 8:
            return "charged"
        workstate = data.get("workstate")

        # Old semsportal.com API values
        if workstate == "EVDetail_Status_Waiting_Stat00":
            return "not_plugged_in"
        if workstate == "EVDetail_Status_Waiting_Stat01":
            return "connected"
        if workstate == "EVDetail_Status_Waiting_Stat02":
            return "finished_charging"
        # Gen2 EU gateway values
        if workstate in ("available_gun_no_insered", "available_gun_no_inserted"):
            return "not_plugged_in"
        if workstate in ("available_gun_insered", "available_gun_inserted", "prepare"):
            return "connected"
        if workstate in ("finishing", "finish", "suspended_evse", "suspended_ev"):
            return "finished_charging"
        if workstate == "":
            return "dash"
        return "unknown"

    @property
    def icon(self) -> str:
        """Return a dynamic icon based on workstate."""
        state = self.native_value
        if state == "not_plugged_in":
            return "mdi:power-plug-off-outline"
        if state == "connected":
            return "mdi:power-plug"
        if state in ("finished_charging", "charged"):
            return "mdi:battery-check"
        if state == "dash":
            return "mdi:progress-clock"
        return "mdi:help-circle-outline"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> dict[str, Any]:
        data = self.coordinator.data.get(self.sn, {}) or {}
        return {
            "identifiers": {(DOMAIN, self.sn)},
            "name": data.get("name") or f"GoodWe Wallbox {self.sn}",
            "manufacturer": "GoodWe",
            "model": data.get("model", "unknown"),
            "sw_version": data.get("fireware", "unknown"),
        }

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

    async def async_update(self) -> None:
        """Update the entity via the coordinator."""
        await self.coordinator.async_request_refresh()


class SemsPowerSensor(CoordinatorEntity, SensorEntity):
    """Instant power sensor in kW."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "power"
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator: SemsUpdateCoordinator, sn: str) -> None:
        """Initialize the power sensor."""
        super().__init__(coordinator)
        self.sn = sn
        _LOGGER.debug("Creating SemsPowerSensor with id %s", self.sn)

    @property
    def unique_id(self) -> str:
        """Unique ID for power sensor."""
        sn = self.coordinator.data.get(self.sn, {}).get("sn", self.sn)
        return f"{sn}_power"

    @property
    def native_value(self) -> float:
        """Return the actual charging power in kW; 0 when not actively charging.

        Uses pevChar from getLastCharge (last_charge_power) as the real drawn
        power.  The detail endpoint's chargePower is the inverter allocation
        limit, which can differ (e.g. 2-phase vs 3-phase sessions).
        """
        data = self.coordinator.data.get(self.sn, {}) or {}
        if data.get("last_charge_work_status") != 6:
            return 0.0
        try:
            power = float(data.get("last_charge_power") or 0)
        except (TypeError, ValueError):
            power = 0.0
        return max(0.0, power)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> dict[str, Any]:
        data = self.coordinator.data.get(self.sn, {}) or {}
        return {
            "identifiers": {(DOMAIN, self.sn)},
            "name": data.get("name") or f"GoodWe Wallbox {self.sn}",
            "manufacturer": "GoodWe",
            "model": data.get("model", "unknown"),
            "sw_version": data.get("fireware", "unknown"),
        }

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

    async def async_update(self) -> None:
        """Update the entity via the coordinator."""
        await self.coordinator.async_request_refresh()


class SemsStatisticsSensor(CoordinatorEntity, SensorEntity):
    """Energy sensor in kWh -- shows current session energy from getLastCharge."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "energy"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator: SemsUpdateCoordinator, sn: str) -> None:
        """Initialize the statistics sensor."""
        super().__init__(coordinator)
        self.sn = sn
        _LOGGER.debug("Creating SemsStatisticsSensor with id %s", self.sn)

    @property
    def native_value(self) -> Decimal | None:
        """Return current session energy in kWh (currentChargeQuantity from getLastCharge)."""
        data = self.coordinator.data.get(self.sn, {}) or {}
        raw = data.get("last_charge_energy")
        if raw is None:
            return None
        try:
            return Decimal(str(raw))
        except Exception:  # noqa: BLE001
            return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def unique_id(self) -> str:
        """Unique ID for energy sensor."""
        sn = self.coordinator.data.get(self.sn, {}).get("sn", self.sn)
        return f"{sn}-energy"

    @property
    def device_info(self) -> dict[str, Any]:
        data = self.coordinator.data.get(self.sn, {}) or {}
        return {
            "identifiers": {(DOMAIN, self.sn)},
            "name": data.get("name") or f"GoodWe Wallbox {self.sn}",
            "manufacturer": "GoodWe",
            "model": data.get("model", "unknown"),
            "sw_version": data.get("fireware", "unknown"),
        }

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

    async def async_update(self) -> None:
        """Update the entity via the coordinator."""
        await self.coordinator.async_request_refresh()


class SemsChargePowerLimitSensor(CoordinatorEntity, SensorEntity):
    """Readonly sensor for the current allocated charge power limit (kW).

    In PV modes (1 & 2) the inverter dynamically adjusts this value based on
    solar / battery availability.  In Fast mode (0) it reflects the configured
    fixed limit.  Always available -- unlike the number entity which is only
    editable in Fast mode.
    """

    _attr_device_class = SensorDeviceClass.POWER
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "set_charge_power_limit"
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: SemsUpdateCoordinator, sn: str) -> None:
        """Initialize the charge power limit sensor."""
        super().__init__(coordinator)
        self.sn = sn

    @property
    def unique_id(self) -> str:
        sn = self.coordinator.data.get(self.sn, {}).get("sn", self.sn)
        return f"{sn}_set_charge_power_limit"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data.get(self.sn, {}) or {}
        v = data.get("set_charge_power")
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> dict[str, Any]:
        data = self.coordinator.data.get(self.sn, {}) or {}
        return {
            "identifiers": {(DOMAIN, self.sn)},
            "name": data.get("name") or f"GoodWe Wallbox {self.sn}",
            "manufacturer": "GoodWe",
            "model": data.get("model", "unknown"),
            "sw_version": data.get("fireware", "unknown"),
        }

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

    async def async_update(self) -> None:
        """Update the entity via the coordinator."""
        await self.coordinator.async_request_refresh()


class SemsChargeDurationSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the duration of the current (or last) charge session in minutes."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "charge_duration"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: SemsUpdateCoordinator, sn: str) -> None:
        super().__init__(coordinator)
        self.sn = sn

    @property
    def unique_id(self) -> str:
        sn = self.coordinator.data.get(self.sn, {}).get("sn", self.sn)
        return f"{sn}_charge_duration"

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data.get(self.sn, {}) or {}
        v = data.get("last_charge_duration_minutes")
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> dict[str, Any]:
        data = self.coordinator.data.get(self.sn, {}) or {}
        return {
            "identifiers": {(DOMAIN, self.sn)},
            "name": data.get("name") or f"GoodWe Wallbox {self.sn}",
            "manufacturer": "GoodWe",
            "model": data.get("model", "unknown"),
            "sw_version": data.get("fireware", "unknown"),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()


# ---------------------------------------------------------------------------
# Modbus-specific sensor classes (only created in local Modbus mode)
# ---------------------------------------------------------------------------


def _device_info(coordinator, sn: str) -> dict:
    data = coordinator.data.get(sn, {}) or {}
    return {
        "identifiers": {(DOMAIN, sn)},
        "name": data.get("name") or f"GoodWe Wallbox {sn}",
        "manufacturer": "GoodWe",
        "model": data.get("model", "unknown"),
        "sw_version": data.get("modbus_sw_version") or data.get("fireware", "unknown"),
    }


class SemsModbusVoltageSensor(CoordinatorEntity, SensorEntity):
    """Phase voltage sensor (A, B or C) read via Modbus."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sn: str, phase: str) -> None:
        super().__init__(coordinator)
        self.sn = sn
        self._phase = phase.upper()
        self._field = f"modbus_voltage_{phase.lower()}"
        self._attr_translation_key = f"voltage_{phase.lower()}"

    @property
    def unique_id(self) -> str:
        return f"{self.sn}_modbus_voltage_{self._phase}"

    @property
    def name(self) -> str:
        return f"Phase {self._phase} Voltage"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data.get(self.sn, {}) or {}
        v = data.get(self._field)
        return round(float(v), 1) if v is not None else None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> dict:
        return _device_info(self.coordinator, self.sn)


class SemsModbusCurrentSensor(CoordinatorEntity, SensorEntity):
    """Phase current sensor (A, B or C) read via Modbus."""

    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sn: str, phase: str) -> None:
        super().__init__(coordinator)
        self.sn = sn
        self._phase = phase.upper()
        self._field = f"modbus_current_{phase.lower()}"
        self._attr_translation_key = f"current_{phase.lower()}"

    @property
    def unique_id(self) -> str:
        return f"{self.sn}_modbus_current_{self._phase}"

    @property
    def name(self) -> str:
        return f"Phase {self._phase} Current"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data.get(self.sn, {}) or {}
        v = data.get(self._field)
        return round(float(v), 1) if v is not None else None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> dict:
        return _device_info(self.coordinator, self.sn)


class SemsModbusEnergyTotalSensor(CoordinatorEntity, SensorEntity):
    """Total accumulated energy sensor read via Modbus (register 10065)."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, sn: str) -> None:
        super().__init__(coordinator)
        self.sn = sn

    @property
    def unique_id(self) -> str:
        return f"{self.sn}_modbus_energy_total"

    @property
    def name(self) -> str:
        return "Total Energy (Modbus)"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data.get(self.sn, {}) or {}
        v = data.get("modbus_energy_total")
        return round(float(v), 1) if v is not None else None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> dict:
        return _device_info(self.coordinator, self.sn)


class SemsModbusStatusSensor(CoordinatorEntity, SensorEntity):
    """Direct Modbus status sensor (register 10017, numeric 0-10)."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "idle_no_plug", "idle_plugged", "handshaking", "charging",
        "charging_completed", "abnormal_alarm", "scheduled_start",
        "maintenance", "start_failed", "upgrading", "interrupted", "unknown",
    ]
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "modbus_charging_status"

    def __init__(self, coordinator, sn: str) -> None:
        super().__init__(coordinator)
        self.sn = sn

    @property
    def unique_id(self) -> str:
        return f"{self.sn}_modbus_status"

    @property
    def native_value(self) -> str:
        data = self.coordinator.data.get(self.sn, {}) or {}
        return data.get("modbus_status_name", "unknown")

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data.get(self.sn, {}) or {}
        attrs = {}
        if (v := data.get("modbus_status_raw")) is not None:
            attrs["status_raw"] = v
        for key in ("modbus_fault_01", "modbus_fault_02", "modbus_fault_03",
                    "modbus_warn_05", "modbus_power_source", "modbus_comm_status"):
            if (v := data.get(key)) is not None:
                attrs[key] = v
        return attrs

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> dict:
        return _device_info(self.coordinator, self.sn)


class SemsModbusCarConnectionSensor(CoordinatorEntity, SensorEntity):
    """Car connection state sensor (register 10075 and CP voltage 10084)."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["disconnected", "half_connected", "connected", "unknown"]
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "modbus_car_connection"

    _CAR_MAP = {0: "disconnected", 1: "half_connected", 2: "connected"}

    def __init__(self, coordinator, sn: str) -> None:
        super().__init__(coordinator)
        self.sn = sn

    @property
    def unique_id(self) -> str:
        return f"{self.sn}_modbus_car_connection"

    @property
    def native_value(self) -> str:
        data = self.coordinator.data.get(self.sn, {}) or {}
        v = data.get("modbus_car_connected")
        return self._CAR_MAP.get(v, "unknown") if v is not None else "unknown"

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data.get(self.sn, {}) or {}
        attrs = {}
        if (v := data.get("modbus_cp_state_name")) is not None:
            attrs["cp_voltage"] = v
        if (v := data.get("modbus_cp_state")) is not None:
            attrs["cp_state_raw"] = v
        return attrs

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> dict:
        return _device_info(self.coordinator, self.sn)


# Bit-field descriptions for fault / warning registers
_AC_FAULT_01_BITS = {
    0: "Emergency stop",
    1: "AC overvoltage",
    2: "AC overcurrent",
    3: "AC undervoltage",
    4: "AC frequency fault",
    5: "AC loss of phase",
    6: "Contactor fault",
    7: "Meter communication fault",
    8: "Proximity pilot fault",
    9: "Control pilot fault",
}

_AC_FAULT_02_BITS = {
    0: "Door fault",
    1: "Ground fault",
    2: "Relay fault",
    3: "PLC communication fault",
    4: "Interlock fault",
    5: "Lock fault",
    6: "Lock feedback fault",
    7: "Output short circuit",
}

_AC_FAULT_03_BITS = {
    0: "Leakage fault",
    1: "Insufficient power",
    2: "Power limit fault",
}

_HW_FAULT_07_BITS = {
    0: "External flash fault",
    1: "EEPROM fault",
    2: "Leakage detection board fault",
    3: "SN not registered",
    4: "RTC fault",
}

_WARN_05_BITS = {
    0: "Gun overheat",
    1: "Ground alarm",
    2: "RFID communication alarm",
    3: "AC overvoltage alarm",
    4: "AC undervoltage alarm",
    5: "AC overcurrent alarm",
    6: "AC frequency alarm",
}

_WARN_06_BITS = {
    0: "Environment overheat alarm",
}


def _decode_bits(value, bit_names):
    if value is None or value == 0:
        return []
    return [name for bit, name in bit_names.items() if value & (1 << bit)]


class SemsModbusFaultSensor(CoordinatorEntity, SensorEntity):
    """Aggregate fault / warning state sensor for Modbus mode.

    State is one of: ok | warning | fault
    Extra attributes list all active fault and warning bits.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["ok", "warning", "fault"]
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "modbus_fault_state"

    def __init__(self, coordinator, sn):
        super().__init__(coordinator)
        self.sn = sn

    @property
    def unique_id(self):
        return f"{self.sn}_modbus_fault_state"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.sn, {}) or {}
        fault_regs = (
            data.get("modbus_fault_01"),
            data.get("modbus_fault_02"),
            data.get("modbus_fault_03"),
            data.get("modbus_hw_fault_07"),
        )
        warn_regs = (
            data.get("modbus_warn_05"),
            data.get("modbus_warn_06"),
        )
        if any(v for v in fault_regs if v):
            return "fault"
        if any(v for v in warn_regs if v):
            return "warning"
        return "ok"

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data.get(self.sn, {}) or {}
        attrs = {}

        for reg_key, bit_names, label in (
            ("modbus_fault_01", _AC_FAULT_01_BITS, "ac_fault_01"),
            ("modbus_fault_02", _AC_FAULT_02_BITS, "ac_fault_02"),
            ("modbus_fault_03", _AC_FAULT_03_BITS, "ac_fault_03"),
            ("modbus_hw_fault_07", _HW_FAULT_07_BITS, "hw_fault_07"),
            ("modbus_warn_05", _WARN_05_BITS, "warning_05"),
            ("modbus_warn_06", _WARN_06_BITS, "warning_06"),
        ):
            raw = data.get(reg_key)
            if raw is not None:
                attrs[f"{label}_raw"] = raw
                active = _decode_bits(raw, bit_names)
                if active:
                    attrs[label] = active

        return attrs

    @property
    def available(self):
        return self.coordinator.last_update_success

    @property
    def device_info(self):
        return _device_info(self.coordinator, self.sn)
