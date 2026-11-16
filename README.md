<!-- Written by Claude, guided by Chris. -->

# grundfos-modbus

Read Grundfos pumps through a CIM 200 / CIM 500 Modbus module, as typed Python
objects, on top of
[modbus-connection](https://github.com/home-assistant-libs/modbus-connection).

## Supported devices

The register map is Grundfos' "Modbus for Grundfos pumps" functional profile
(document 6012947), which covers MAGNA3 and MAGNA3-D circulators, E-pumps with
MGE motors (TPE, NBE, NKE, CRE and so on) and CUE drives, fitted with a CIM
200 (Modbus RTU) or CIM 500 (Modbus TCP) module.

It has been run against one **MAGNA3 40-80 F with a CIM 500** on Modbus TCP.
Other pumps in the profile should work but are untested.

## CIM 500 setup notes

- Set the module's rotary switch to **1 (Modbus TCP)**. It ships at 0
  (PROFINET), where its IP fields are read-only. Changing the switch resets the
  module's network settings to the factory address.
- The module has two addresses: the **web server** (factory 192.168.1.100,
  login admin / Grundfos, which forces a new password) and a separate
  **Modbus TCP** address, set on the "Real Time Ethernet Protocol" page once
  the switch is at 1. Modbus is on port 502; the unit ID is ignored.
- The module is powered by the pump. If the pump's supply is switched (by a
  zone relay, say), the module is unreachable whenever the pump is off.

## What it covers

| Component | Registers | What |
| :--- | :--- | :--- |
| `cim` | 00021-00037 | Module version, GENIbus link counters, the product's unit family/type (decoded to a name such as "MAGNA3"), product software version and date |
| `status` | 00201-00225 | Status bits (on, rotating, alarm, warning, at max speed...), process feedback, control and operating mode, alarm and warning codes, feedback sensor unit and range, frequency limits, setpoint range, flow-estimation state, PI gains, control source |
| `data` | 00301-00362 | Head, flow, relative performance, speed, frequency, setpoints, motor current, DC-link voltage, power, temperatures, specific energy, operating/powered hours, energy, starts, differential and remote pressures, flow limit, the heat meter and pumped volume |

Each component is one block read, three requests per update. The module
answers both function code 3 and 4 for these blocks; this library uses 3.

Decoding conventions:

- A register the pump doesn't supply reads 0xFFFF (0xFFFFFFFF for 32-bit
  values) and decodes to `None`.
- Temperatures arrive in hundredths of a kelvin and decode to °C.
- Codes decode to `ControlMode`, `OperationMode`, `AlarmCode`,
  `ControlSource`, `FlowEstimationState` and `FeedbackSensorUnit`; a code the
  profile doesn't list stays a plain `int`. Status bits decode to the
  `PumpStatus` flag.
- `data.has_heat_meter` is true only when heat power is available. Without a
  second temperature sensor the heat energy counters read 0, not "not
  available".

## Read-only

The profile has a control block (00101-00112: remote/local, on/off, control
mode, setpoint, flow limit). This library doesn't write it. Taking a pump
into remote control is a decision for whoever wires it up, not a default.

## Installation

```
pip install grundfos-modbus
```

For Home Assistant, you don't need this directly: use the
[ha-grundfos](https://github.com/cwm12345/ha-grundfos) integration, which
includes a copy.

## Usage

```python
import asyncio

from modbus_connection import ModbusTcpParams
from modbus_connection.tmodbus import ModbusConnection
from grundfos_modbus import GrundfosPump


async def main() -> None:
    connection = ModbusConnection(ModbusTcpParams(host="192.168.1.50", port=502))
    try:
        pump = GrundfosPump(connection.for_unit(1))
        await pump.async_update()
        print(pump.cim.product, pump.status.control_mode)
        print(
            pump.data.volume_flow,
            "m³/h at",
            pump.data.head,
            "bar,",
            pump.data.power,
            "W",
        )
    finally:
        await connection.close()


asyncio.run(main())
```

Or from the command line: `uv run script/query.py 192.168.1.50`.

## Development

```
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

The tests run against modbus-connection's in-memory mock backend, seeded with
registers captured from a live MAGNA3. No hardware is needed.

## License

[Unlicense](LICENSE): public domain.
