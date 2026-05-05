# GoodWe Wallbox -- Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Tests](https://github.com/prezervos/goodwe-wallbox-sems-home-assistant/actions/workflows/tests.yml/badge.svg)](https://github.com/prezervos/goodwe-wallbox-sems-home-assistant/actions/workflows/tests.yml)
[![Validate](https://github.com/prezervos/goodwe-wallbox-sems-home-assistant/actions/workflows/validate.yml/badge.svg)](https://github.com/prezervos/goodwe-wallbox-sems-home-assistant/actions/workflows/validate.yml)
[![GitHub release](https://img.shields.io/github/release/prezervos/goodwe-wallbox-sems-home-assistant.svg)](https://github.com/prezervos/goodwe-wallbox-sems-home-assistant/releases)

Home Assistant custom integration for the **GoodWe Wallbox**.

Supports two independent connection modes:

| Mode | How it works | Internet required |
|------|-------------|-------------------|
| **Local Modbus TCP** | Connects directly to the wallbox over your LAN using Modbus TCP | No |
| **SEMS cloud** | Polls the SEMS / SEMS Plus EU gateway API | Yes |

---

## Features

### Both modes

| Entity | Type | Description |
|--------|------|-------------|
| Charging | Switch | Start / stop charging |
| Charge mode | Select | Fast / PV priority / PV & battery |
| Status | Sensor | Current charging state |
| Vehicle state | Sensor | Car plug connection state |
| Charging power | Sensor (kW) | Actual power drawn |
| Session energy | Sensor (kWh) | Energy delivered in current session |
| Charge duration | Sensor (min) | Duration of current / last session |
| Charge power limit | Number (kW) | Set max charge power |
| Ensure minimum power | Switch | Keep charging when PV is insufficient (PV modes only) |

### Local Modbus TCP only

| Entity | Type | Description |
|--------|------|-------------|
| Charging station status | Sensor (Enum) | Detailed 12-state status from register 10017 |
| Car connection | Sensor (Enum) | Plug / CP state (disconnected / half-connected / connected) |
| Fault state | Sensor (Enum) | Aggregated ok / warning / fault with decoded bit attributes |
| Phase A/B/C voltage | Sensor (V) | Per-phase AC voltage |
| Phase A/B/C current | Sensor (A) | Per-phase AC current |
| Total energy | Sensor (kWh) | Lifetime accumulated energy (register 10065) |
| Max charge power | Number (kW) | Register 10029 limit (range depends on hardware model) |
| Max session energy | Number (kWh) | Stop after delivering this energy (0 = unlimited) |
| Min session energy | Number (kWh) | Keep charging until this energy is delivered |
| Battery discharge SOC | Number (%) | Discharge limit for PV+battery mode |
| Plug & Charge | Switch | Enable automatic charging on plug-in |
| Dynamic load management | Switch | Enable DLM current redistribution |
| EMS minimum power mode | Switch | Force minimum power dispatch via EMS |

All entities are translated -- Czech (`cs`) and English (`en`) are included.

---

## Requirements

- Home Assistant 2023.6 or newer
- GoodWe EV Charger (Wallbox Gen2)
- For **Modbus mode**: wallbox reachable on your LAN, port 502 open
- For **SEMS cloud mode**: SEMS / SEMS Plus account with the wallbox registered

---

## Installation

### Via HACS (recommended)

1. Open HACS → Integrations → ⋮ → **Custom repositories**
2. Add `https://github.com/prezervos/goodwe-wallbox-sems-home-assistant` as **Integration**
3. Search for **GoodWe Wallbox** and download it
4. Restart Home Assistant

### Manual

Copy the `custom_components/sems_wallbox/` folder into your HA `config/custom_components/` directory and restart.

---

## Configuration

Go to **Settings → Devices & Services → Add Integration** and search for **GoodWe Wallbox**.

The first step asks you to choose a connection type.

---

## Option A: Local Modbus TCP (recommended)

This mode communicates directly with the wallbox over your local network. No cloud account is needed and it exposes more entities than the cloud mode.

### Prerequisites

- The wallbox must have a static IP address -- set a DHCP reservation in your router.
- Port **502** must be reachable from Home Assistant.

### Setup steps

1. Choose **Local Modbus TCP** in the connection type step.
2. Enter the wallbox **IP address** (e.g. `192.168.1.50`) and **port** (default `502`).
3. Leave **Modbus device ID** as `0` to auto-detect -- the integration scans common IDs and finds the wallbox automatically. GoodWe Wallbox Gen2 uses ID **247 (0xF7)**; enter it directly to skip the scan.
4. The integration reads the serial number directly from the device and creates the entry automatically.

### Finding the IP address

- Your router's DHCP client list -- look for a device named `GOODWE` or with a GoodWe MAC prefix.
- The GoodWe SEMS app (device details screen).
- A LAN scanner: `nmap -sn 192.168.1.0/24`.

---

## Option B: SEMS cloud

This mode polls the SEMS / SEMS Plus EU gateway API. An internet connection and a SEMS account are required.

### Recommended: use a visitor account

Create a **dedicated visitor account** in the SEMS app and use those credentials here:

1. Open the **SEMS Plus** mobile app, log in with your **main** account.
2. Go to your station (plant) → **Share** (or **Visitor Management**).
3. Tap **Add visitor**, enter the visitor e-mail and set privileges to **Read and Modify**.
4. Register the visitor account at [semsportal.com](https://www.semsportal.com) or in the app.
5. Use the **visitor e-mail and password** when setting up this integration.

### Setup steps

1. Choose **SEMS cloud** in the connection type step.
2. Enter your **SEMS Plus / semsportal.com** username and password.
3. If you have multiple plants, select the one that contains the wallbox.
4. Confirm the detected wallbox (or enter the serial number manually if auto-detection fails).
5. The integration stores the Plant ID and product model automatically.

### Gen2 / HCA series chargers

Chargers in the HCA product family (e.g. `GW7K-HCA-20`) use the SEMS Plus EU gateway for control commands. The integration handles this automatically -- no manual configuration needed.

You can review or override the Plant ID and product model at any time via  
**Settings → Devices & Services → GoodWe Wallbox → Configure**.

---

## Update interval (cloud mode)

Default polling: **60 s** idle, **30 s** while charging. Adjust via  
**Settings → Devices & Services → GoodWe Wallbox → Configure**.

---

## Debugging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.sems_wallbox: debug
```

---

## Development

```bash
# Install test dependencies
pip install pytest pytest-asyncio requests pymodbus

# Run tests (must run from repo root, NOT from inside custom_components/)
pytest tests/ -v
```

> On Windows, always run `pytest` from outside the project root to avoid the stdlib `select` module being shadowed by `custom_components/sems_wallbox/select.py`.

---

## Changelog

### 1.5.0
- **Local Modbus TCP mode**: connect directly to the wallbox without cloud or internet
  - Auto-detects Modbus device ID (scans common IDs, GoodWe Gen2 uses 247/0xF7)
  - 10 writable registers: start/stop, charge mode, max power, session energy limits, battery SOC threshold, Plug&Charge, dynamic load management, EMS dispatch
  - New sensors: charging station status (12 states), car connection, per-phase voltage/current, total energy, fault state with decoded bit attributes
  - New controls: max charge power, max/min session energy, battery discharge SOC, Plug&Charge, dynamic load management, EMS minimum power mode
- **Integration renamed** to "GoodWe Wallbox" (domain `sems_wallbox`)
- Config flow now shows a connection type choice (cloud vs. Modbus) as the first step

### 1.4.0
- `getLastCharge` polling: each coordinator update also calls `getLastCharge` to get the real charging state
- **Status sensor** driven by `workStu=6` from `getLastCharge` -- correctly shows Charging in all PV modes
- **Charging power sensor** shows `pevChar` (actual drawn power) instead of the configured limit
- **Session energy sensor** reads `currentChargeQuantity` from `getLastCharge`
- **New: Allocated charge power sensor** -- readonly, shows inverter's dynamic allocation
- **New: Charge duration sensor** -- current/last session duration in minutes
- **Charge power limit slider** always visible; moving it from any mode switches to Fast
- 128 unit tests, all passing

### 1.3.0
- Visitor account support in config flow
- Auto-discovery of `productModel` via EU gateway
- set-mode timeout raised to 90 s

### 1.2.0
- Auto-discovery of plants and EV chargers in config flow
- Full Gen2 / HCA series support via SEMS Plus EU gateway
- Dynamic polling (faster while charging)
- Options flow for Plant ID, product model and polling intervals

### 1.1.0
- Full Czech and English entity translations
- `SemsWorkStateSensor` -- vehicle connection state
- Charge power slider disabled when charge mode is not Fast
- Grace period logic in charging switch (130 s)

### 1.0.0
- Initial release by [@prezervos](https://github.com/prezervos)

## Credits

Based on the original work by [@prezervos](https://github.com/prezervos/goodwe-wallbox-sems-home-assistant),  
which was itself inspired by [@TimSoethout/goodwe-sems-home-assistant](https://github.com/TimSoethout/goodwe-sems-home-assistant).
