# AC EV Charger Gen2 — Modbus Protocol

> Document version: **V1.0.15** (2025-09-12)
> Protocol: Modbus TCP, port 502, unit ID 247 (0xF7)

---

## Version history

| Version | Date       | Author      | Change                                                                                              |
|---------|------------|-------------|-----------------------------------------------------------------------------------------------------|
| V1.0.00 | 2024-07-25 | leiminghong | Initial Modbus register protocol                                                                    |
| V1.0.01 | 2024-07-29 | leiminghong | Added on/off control, hardware version, charger type, power spec                                    |
| V1.0.02 | 2024-08-20 | leiminghong | Opened write access for selected registers; added additional register descriptions                  |
| V1.0.03 | 2024-09-09 | leiminghong | Added English comments                                                                              |
| V1.0.04 | 2024-09-11 | leiminghong | Added function codes, frame format, baud rate; completed RW register range                         |
| V1.0.05 | 2024-09-29 | leiminghong | Corrected STR register addresses; corrected register 10066 operation value                         |
| V1.0.06 | 2024-11-21 | leiminghong | Corrected SN, software version and hardware version register addresses and counts                  |
| V1.0.07 | 2024-11-27 | leiminghong | Added OTA address operation; added registers 10061–10153                                           |
| V1.0.08 | 2024-11-28 | leiminghong | Corrected charger time registers                                                                    |
| V1.0.09 | 2025-07-01 | leiminghong | Added charging record registers; enabled scheduled-charge write; defined fault-info (IOT) registers |
| V1.0.10 | 2025-07-02 | leiminghong | Corrected size of 30000 alarm register                                                              |
| V1.0.11 | 2025-08-07 | yuanzhiping | HEMS polling strategy: updated some register addresses and types                                   |
| V1.0.12 | 2025-08-07 | yuanzhiping | MQTT status display: redefined upgrade state values                                                 |
| V1.0.13 | 2025-08-13 | tanri       | Added meaning of bits 5 and 6 of register 10018; added register 10176 (session energy clear flag) |
| V1.0.14 | 2025-09-08 | tanri       | Added cybersecurity version register at address 10109                                              |
| V1.0.15 | 2025-09-12 | tanri       | Cybersecurity version moved to 10592; 10109 deprecated. Note: single-connection Modbus TCP does not support remote OTA — requires GoodWe gateway. |

---

## 1. Data types

| Type | Description   | Bytes | NaN value  |
|------|---------------|-------|------------|
| STR  | unsigned char | 2     | 0x0        |
| S16  | signed int    | 2     | 0x8000     |
| U16  | unsigned int  | 2     | 0xFFFF     |
| S32  | signed long   | 4     | 0x80000000 |
| U32  | unsigned long | 4     | 0xFFFFFFFF |

## 2. Access types

| Code | Meaning        |
|------|----------------|
| RO   | Read-only      |
| WO   | Write-only     |
| RW   | Read and write |

## 3. SCI communication format

| Parameter | Value |
|-----------|-------|
| Baud rate | 9600  |
| Byte size | 8     |
| Stop bits | 1     |
| Parity    | N     |

## 4. Modbus exception codes

| Code   | Name                 |
|--------|----------------------|
| 0x0001 | Illegal Function     |
| 0x0002 | Illegal Data Address |
| 0x0003 | Illegal Data Value   |
| 0x0004 | Slave Device Failure |

---

## 5. Register table — block 10000 (status & control)

| Address | English Name                         | R/W | Type | Size | SF  | Unit | Range   | Flash | Description                                                                                                                                                                                                                         |
|---------|--------------------------------------|-----|------|------|-----|------|---------|-------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 10000   | EMS Energy Dispatch                  | RW  | U16  | 1    | —   | —    | [0,1]   | N     | 1 = reduce charging power to minimum; 0 = normal operation                                                                                                                                                                          |
| 10001   | AC Fault Bytes 01                    | RO  | U16  | 1    | —   | —    | [0,255] |       | bit0: emergency stop; bit1: overvoltage; bit2: overcurrent; bit3: undervoltage; bit4: connector fault; bit5: S2 disconnected; bit6: environment overtemp; bit7: gun overtemp                                                       |
| 10002   | AC Fault Bytes 02                    | RO  | U16  | 1    | —   | —    | [0,255] |       | bit0: door access fault; bit1: grounding fault; bit2: handshake timeout; bit3: RF card comm fault; bit4: serial display comm fault; bit5: on-board meter IC comm fault; bit6: output relay fault; bit7: gun lock fault              |
| 10003   | AC Fault Bytes 03                    | RO  | U16  | 1    | —   | —    | [0,255] |       | bit0: output short circuit; bit1: leakage current; bit2: charge pause >10 min; bit3: abnormal meter reading; bit4: charger offline on PV/battery start; bit5: insufficient PV/battery power; bit6–7: reserved                     |
| 10004   | AC Fault Bytes 04                    | RO  | U16  | 1    | —   | —    | [0,255] |       | Reserved                                                                                                                                                                                                                            |
| 10005   | AC Fault Bytes 05 (warnings)         | RO  | U16  | 1    | —   | —    | [0,255] |       | bit0: gun overtemp alarm; bit1: grounding alarm; bit2: handshake timeout alarm; bit3: RF card comm alarm; bit4: serial display comm alarm; bit5: on-board meter IC comm alarm; bit6: charging stop alarm; bit7: abnormal meter reading |
| 10006   | AC Fault Bytes 06 (warnings)         | RO  | U16  | 1    | —   | —    | [0,255] |       | bit0: environment overtemp alarm                                                                                                                                                                                                    |
| 10007   | AC Fault Bytes 07 (HW faults)        | RO  | U16  | 1    | —   | —    | [0,255] |       | bit0: external flash fault; bit1: EEPROM fault; bit2: leak detection device fault; bit3: abnormal input power; bit4: SN not registered; bit5: factory parameters abnormal; bit6: unauthorized firmware                              |
| 10008   | AC Fault Bytes 08 (HW faults)        | RO  | U16  | 1    | —   | —    | [0,255] | N     | Reserved                                                                                                                                                                                                                            |
| 10009   | A Phase Charging Voltage             | RO  | U16  | 1    | 10  | V    |         |       | Single-phase stations: only phase A is valid                                                                                                                                                                                       |
| 10010   | B Phase Charging Voltage             | RO  | U16  | 1    | 10  | V    |         |       |                                                                                                                                                                                                                                     |
| 10011   | C Phase Charging Voltage             | RO  | U16  | 1    | 10  | V    |         |       |                                                                                                                                                                                                                                     |
| 10012   | A Phase Charging Current             | RO  | U16  | 1    | 10  | A    |         |       | Single-phase stations: only phase A is valid                                                                                                                                                                                       |
| 10013   | B Phase Charging Current             | RO  | U16  | 1    | 10  | A    |         |       |                                                                                                                                                                                                                                     |
| 10014   | C Phase Charging Current             | RO  | U16  | 1    | 10  | A    |         |       |                                                                                                                                                                                                                                     |
| 10015   | Charging Power                       | RO  | U16  | 1    | 10  | kW   |         |       |                                                                                                                                                                                                                                     |
| 10016   | Charging Capacity (session)          | RO  | U16  | 1    | 10  | kWh  |         |       |                                                                                                                                                                                                                                     |
| 10017   | Charging Station Status              | RO  | U16  | 1    | —   | —    |         |       | 0: idle (no plug); 1: idle (plug in); 2: handshaking; 3: charging; 4: completed; 5: abnormal alarm; 6: scheduled start; 7: maintenance; 8: start failed; 9: upgrading; 10: interrupted (PV/bat insufficient)                       |
| 10018   | Communication Connection Status      | RO  | U16  | 1    | —   | —    |         |       | bit0: Wi-Fi to router; bit1: IoT cloud; bit2: inverter online; bit3: MID meter online; bit4: GW meter online; bit5: EMS online; bit6–15: reserved                                                                                  |
| 10019   | Plug and Charge Function Status      | RW  | U16  | 1    | —   | —    | [0,1]   | Y     | 0: off; 1: on                                                                                                                                                                                                                       |

## 6. Register table — block 10020 (configuration)

| Address | English Name                                    | R/W | Type | Size | SF  | Unit | Range     | Flash | Description                                                                                                                                                  |
|---------|-------------------------------------------------|-----|------|------|-----|------|-----------|-------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 10020   | Reservation Status                              | RW  | U16  | 1    | —   | —    | [0,2]     | Y     | 0: not effective; 1: valid once; 2: permanently valid                                                                                                        |
| 10021   | Reservation Start Time                          | RW  | U16  | 1    | 1   | —    |           | Y     | High byte = hour, low byte = minute (hex, e.g. 0x0C1E = 12:30). Returns 0xFFFF if not set.                                                                  |
| 10022   | Reservation Charging Duration                   | RW  | U16  | 1    | 1   | min  |           | Y     |                                                                                                                                                              |
| 10023   | Single/Three-Phase Switching Enable             | RW  | U16  | 1    | —   | —    | [0,1]     | Y     | 0: off; 1: on                                                                                                                                                |
| 10024   | Maintain Minimum Charging Power Enable          | RW  | U16  | 1    | —   | —    | [0,1]     | Y     | 0: off; 1: on                                                                                                                                                |
| 10025   | Dynamic Load Management Enable                  | RW  | U16  | 1    | —   | —    | [0,1]     | Y     | 0: off; 1: on                                                                                                                                                |
| 10026   | Household Circuit Breaker Rated Current         | RW  | U16  | 1    | —   | A    | [0,2000]  | Y     |                                                                                                                                                              |
| 10027   | Maximum Charging Capacity                       | RW  | U16  | 1    | 10  | kWh  | [0,2000]  | Y     |                                                                                                                                                              |
| 10028   | Minimum Charging Capacity                       | RW  | U16  | 1    | 10  | kWh  | [0,2000]  | Y     |                                                                                                                                                              |
| 10029   | Maximum Charging Power                          | RW  | U16  | 1    | 10  | kW   | [14,220]  | Y     | 7 kW single-phase: 1.4–7 kW; 11 kW three-phase: 4.2–11 kW; 22 kW three-phase: 4.2–22 kW                                                                   |
| 10030   | Battery Discharge SOC Value                     | RW  | U16  | 1    | 1   | %    | [0,100]   | Y     | Battery stops discharging to the charger when actual SOC < this value; household loads can still use the battery                                             |
| 10031   | Completion Time                                 | RW  | U16  | 1    | 1   | h    | [0,10]    | Y     | Minimum time to reach the minimum charging energy                                                                                                            |
| 10032   | Current Advanced Charging Mode                  | RW  | U16  | 1    | —   | —    | [0,2]     | Y     | 0: fast charging; 1: PV charging; 2: PV + battery hybrid                                                                                                   |
| 10033   | Current Advanced Charging Mode (Reservation)    | RW  | U16  | 1    | —   | —    | [0,2]     | Y     | Same values as 10032, applies to scheduled charging                                                                                                          |
| 10034   | Maximum Charging Capacity (Reservation)         | RW  | U16  | 1    | 10  | kWh  | [0,2000]  | Y     |                                                                                                                                                              |
| 10035   | Minimum Charging Capacity (Reservation)         | RW  | U16  | 1    | 10  | kWh  | [0,2000]  | Y     |                                                                                                                                                              |
| 10036   | Maximum Charging Power (Reservation)            | RW  | U16  | 1    | 10  | kW   | [14,220]  | Y     | Same range rules as 10029                                                                                                                                    |
| 10037   | Battery Discharge SOC Value (Reservation)       | RW  | U16  | 1    | 1   | %    | [0,100]   | Y     | Same semantics as 10030                                                                                                                                      |
| 10038   | Completion Time (Reservation)                   | RW  | U16  | 1    | 1   | h    | [0,10]    | Y     |                                                                                                                                                              |
| 10039   | Maximum Grid Electricity Draw Power (Grid Limit) | RW  | U16  | 1    | 10  | kW   | [14,220]  | Y     | Same range rules as 10029                                                                                                                                    |

## 7. Register table — block 10040 (device information)

| Address  | English Name                          | R/W | Type | Size | SF  | Unit | Description                                                              |
|----------|---------------------------------------|-----|------|------|-----|------|--------------------------------------------------------------------------|
| 10040    | SN Number                             | RO  | STR  | 8    | —   | —    | ASCII, 16 bytes                                                          |
| 10048    | Software Version (external)           | RO  | STR  | 2    | —   | —    | ASCII, 4 bytes                                                           |
| 10050    | SVN Software Version (internal)       | RO  | U16  | 1    | —   | —    |                                                                          |
| 10051    | HF-WIFI-BLE Module Software Version   | RO  | STR  | 5    | —   | —    | Format: xx.xx.xx, e.g. 1.01.01                                           |
| 10056    | Hardware Version                      | RO  | STR  | 2    | —   | —    | ASCII, 4 bytes                                                           |
| 10058    | Power Specification                   | RO  | U16  | 1    | —   | —    | 0: 7 kW; 1: 11 kW; 2: 22 kW                                             |
| 10059    | Type of Charging Station              | RO  | U16  | 1    | —   | —    | 0: three-phase; 1: single-phase                                          |

## 8. Register table — block 10060 (runtime / control)

| Address  | English Name                        | R/W | Type | Size | SF  | Unit | Range  | Flash | Description                                                                                                                                                              |
|----------|-------------------------------------|-----|------|------|-----|------|--------|-------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 10060    | Turn On/Off Charging                | RW  | U16  | 1    | —   | —    | [1,2]  | N     | 1: off; 2: on                                                                                                                                                            |
| 10061    | Charge Amount (operation mode)      | RO  | U32  | 2    | 100 | —    |        |       | Available only in operation mode                                                                                                                                         |
| 10063    | Charge Duration                     | RO  | U32  | 2    | —   | s    |        |       | Valid only when charging                                                                                                                                                  |
| 10065    | Accumulated Historical Energy       | RO  | U32  | 2    | 10  | kWh  |        |       | Resolution: 0.1 kWh                                                                                                                                                      |
| 10067    | Query Charger Time (year/month)     | RO  | U16  | 1    | —   | —    |        |       | High byte = year (offset from 2000); low byte = month                                                                                                                   |
| 10068    | Query Charger Time (day/hour)       | RO  | U16  | 1    | —   | —    |        |       | High byte = day; low byte = hour                                                                                                                                         |
| 10069    | Query Charger Time (minute/second)  | RO  | U16  | 1    | —   | —    |        |       | High byte = minute; low byte = second                                                                                                                                    |
| 10070    | Reserved                            | RO  | U16  | 1    | —   | —    |        |       |                                                                                                                                                                          |
| 10071    | Set Charger Time (year/month)       | RW  | U16  | 1    | —   | —    |        | Y     | High byte = year; low byte = month                                                                                                                                       |
| 10072    | Set Charger Time (day/hour)         | RW  | U16  | 1    | —   | —    |        | Y     | High byte = day; low byte = hour                                                                                                                                         |
| 10073    | Set Charger Time (minute/second)    | RW  | U16  | 1    | —   | —    |        | Y     | High byte = minute; low byte = second                                                                                                                                    |
| 10074    | Reserved                            | RO  | U16  | 1    | —   | —    |        |       |                                                                                                                                                                          |
| 10075    | Car Connection Status               | RO  | U16  | 1    | —   | —    |        |       | 0: disconnected; 1: half-connected; 2: connected                                                                                                                        |
| 10076    | Charge Starting Mode                | RO  | U16  | 1    | —   | —    |        |       | 0: auth card; 1: backend; 2: local admin; 3: VIN; 4: wallet card; 5: plug and charge; 6: scheduled; 7: Bluetooth app                                                   |
| 10077    | Charging Strategy                   | RO  | U16  | 1    | —   | —    |        |       | 0: auto full; 1: fill by time; 2: fixed amount; 3: charge by energy                                                                                                    |
| 10078    | Charging Strategy Parameter         | RO  | U16  | 1    | —   | —    |        |       | Depends on strategy in 10077                                                                                                                                             |
| 10079    | Appointment Sign                    | RO  | U16  | 1    | —   | —    |        |       | 0: no reservation; 1: reservation valid                                                                                                                                  |
| 10080–10083 | Reserved (fill 0)               | —   | —    | —    | —   | —    |        |       |                                                                                                                                                                          |

## 9. Register table — block 10084 (extras)

| Address  | English Name            | R/W | Type | Size | SF  | Unit | Description                                                                                                                                                  |
|----------|-------------------------|-----|------|------|-----|------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 10084    | CP Voltage State        | RO  | U16  | 1    | —   | —    | 0: no voltage; 1: 12 V; 2: 9 V; 3: 6 V; 4: 3 V                                                                                                             |
| 10085    | SEMS Account Number     | RO  | STR  | 18   | —   | —    | ASCII, 36 bytes                                                                                                                                              |
| 10103    | Green Energy            | RO  | U32  | 2    | 10  | kWh  | Resolution: 0.1 kWh                                                                                                                                         |
| 10105    | Grid Energy (bought)    | RO  | U32  | 2    | 10  | kWh  | Resolution: 0.1 kWh                                                                                                                                         |
| 10107    | Project Type            | RO  | U16  | 1    | —   | —    | 0, 1: DC; 2: AC                                                                                                                                              |
| 10108    | Charging Power Source   | RO  | U16  | 1    | —   | —    | bit0: grid; bit1: PV; bit2: battery; bit3–7: reserved. Multiple bits can be set simultaneously, e.g. 0b00000101 = grid + battery                           |
| 10109–10116 | Reserved (fill 0)   | —   | —    | —    | —   | —    | 10109 deprecated as of V1.0.15                                                                                                                               |
| 10117–10156 | Reserved (fill 0)   | —   | —    | —    | —   | —    |                                                                                                                                                              |
| 10157    | Transparent Mode        | RW  | U16  | 1    | —   | —    | 1: charger communicates via gateway (not directly with IoT); 0: default IoT communication                                                                   |

## 10. Register table — charging record (10158–10176)

| Address | English Name                    | R/W | Type | Size | SF  | Unit   | Description                                                       |
|---------|---------------------------------|-----|------|------|-----|--------|-------------------------------------------------------------------|
| 10158   | Charging Start Time (year/month) | RO | U16  | 1    | —   | —      | High byte = year; low byte = month                                |
| 10159   | Charging Start Time (day/hour)  | RO  | U16  | 1    | —   | —      | High byte = day; low byte = hour                                  |
| 10160   | Charging Start Time (min/sec)   | RO  | U16  | 1    | —   | —      | High byte = minute; low byte = second                             |
| 10161   | Reserved                        | RO  | U16  | 1    | —   | —      |                                                                   |
| 10162   | Charging End Time (year/month)  | RO  | U16  | 1    | —   | —      |                                                                   |
| 10163   | Charging End Time (day/hour)    | RO  | U16  | 1    | —   | —      |                                                                   |
| 10164   | Charging End Time (min/sec)     | RO  | U16  | 1    | —   | —      |                                                                   |
| 10165   | Reserved                        | RO  | U16  | 1    | —   | —      |                                                                   |
| 10166   | Charging Duration               | RO  | U32  | 2    | —   | s      |                                                                   |
| 10168   | Reason for Charging Termination | RO  | U32  | 2    | —   | —      | Refer to Appendix 2 of the backend communication protocol         |
| 10170   | Meter Reading Before Charging   | RO  | U32  | 2    | —   | 0.01 kWh |                                                                |
| 10172   | Meter Reading After Charging    | RO  | U32  | 2    | —   | 0.01 kWh |                                                                |
| 10174   | Current Charging Record Index   | RO  | U32  | 2    | —   | —      |                                                                   |
| 10176   | Session Energy Clear Flag       | RO  | U16  | 1    | —   | —      | Write 1 to clear session energy (register 10016) to zero         |

## 11. Register table — RFID cards (10500–10592)

| Address | English Name               | R/W | Type | Size | SF  | Unit | Description                                                                                             |
|---------|----------------------------|-----|------|------|-----|------|---------------------------------------------------------------------------------------------------------|
| 10500   | Charging Card Number       | RO  | STR  | 7    | —   | —    | UID fixed 14 bytes, ASCII, zero-padded                                                                  |
| 10507   | Add RFID Card Number       | RW  | STR  | 7    | —   | —    | UID fixed 14 bytes; one card delivered at a time                                                        |
| 10514   | Delete RFID Card Number    | RW  | STR  | 7    | —   | —    | UID fixed 14 bytes; one card deleted at a time                                                          |
| 10521   | Query All RFID Card Numbers | RO | STR  | 70   | —   | —    | Returns all stored cards; fixed storage for 10 cards, 14 bytes each                                    |
| 10592   | Safety (Cybersecurity) Version | RO | STR | 2   | —   | —    | Format: XX.XX.XXXX, e.g. 1.0.13 stored as 0x31, 0x30, 0x31, 0x33. Added in V1.0.15 (replaced 10109). |

## 12. Register table — OTA firmware upgrade (20000–20098)

> **Note:** Single-connection Modbus TCP does not support remote OTA. A GoodWe gateway device is required for remote upgrades.

| Address     | English Name              | R/W | Type | Size | SF  | Unit | Flash | Description                                                                                                  |
|-------------|---------------------------|-----|------|------|-----|------|-------|--------------------------------------------------------------------------------------------------------------|
| 20000–20079 | Firmware Download URL     | WO  | STR  | 80   | —   | —    | N     | ASCII string, null-terminated, zero-padded. HTTPS URL.                                                       |
| 20080–20095 | Firmware MD5              | WO  | STR  | 16   | —   | —    | N     | ASCII MD5 hash of the firmware file                                                                          |
| 20096       | Upgrade Trigger           | WO  | U16  | 1    | —   | —    | N     | Write any value to start the upgrade after URL+MD5 are written                                               |
| 20097       | Upgrade State             | RO  | U16  | 1    | —   | —    |       | 0: no upgrade; 1: download complete; 2: download failed; 3: upgrade successful; 4: upgrade failed; 7: upgrading |
| 20098       | Upgrade Percentage        | RO  | U16  | 1    | —   | —    |       |                                                                                                              |

## 13. Register table — IOT alarm information (30000–30015)

Registers 30000–30015 each hold one U16 alarm code (RO, not flash-saved, big-endian).  
For detailed alarm code definitions refer to Appendix 1 of the backend communication protocol.

| Address     | English Name           | R/W | Type | Size |
|-------------|------------------------|-----|------|------|
| 30000–30015 | Alarm Information (IOT)| RO  | U16  | 1    |

---

## Scale factor note

A scale factor (SF) of **10** means the register value must be divided by 10 to get the physical value.  
Example: register 10029 reads `70` → 70 / 10 = **7.0 kW**.

A scale factor of **100** means divide by 100, etc.
