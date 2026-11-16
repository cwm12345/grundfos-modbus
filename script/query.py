#!/usr/bin/env python3
# Written by Claude, guided by Chris.

"""Query a Grundfos pump through a CIM Modbus module and print every value."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

from modbus_connection import ModbusError
from modbus_connection.cli_helper import (
    CountingUnit,
    add_connection_args,
    connect_from_args,
    print_component,
)

from grundfos_modbus import COMPONENTS, GrundfosPump

# A CIM 500 answers Modbus TCP; a CIM 200 is Modbus RTU on RS-485, directly or
# through a serial server. Both framers are named on purpose: offered a single
# framer, cli_helper defaults every transport to it.
CONNECTIONS = (("tcp", "socket"), ("serial", "rtu"))

EXAMPLES = """examples:
  uv run script/query.py 192.168.1.50
  uv run script/query.py /dev/ttyUSB0 --transport serial --baudrate 19200 --raw
"""


async def main() -> int:
    """Read one pump and print it."""
    logging.getLogger().addHandler(logging.NullHandler())

    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_connection_args(parser, connections=CONNECTIONS)
    parser.add_argument(
        "--unit", type=int, default=1, help="Modbus unit id (ignored by a CIM 500)"
    )
    parser.add_argument(
        "--raw", action="store_true", help="also dump every register read, as JSON"
    )
    args = parser.parse_args()

    try:
        connection = await connect_from_args(args)
    except ModbusError as err:
        print(f"Could not connect to {args.target}: {str(err) or type(err).__name__}")
        return 1

    counting = CountingUnit(connection.for_unit(args.unit))
    pump = GrundfosPump(counting)
    try:
        report = await pump.async_update()
        reads = counting.reads
        raw = await pump.async_read_raw() if args.raw else None
    except ModbusError as err:
        print(f"Could not read the pump: {str(err) or type(err).__name__}")
        return 1
    finally:
        await connection.close()

    for name in COMPONENTS:
        print()
        print_component(getattr(pump, name), title=name)

    c, s, d = pump.cim, pump.status, pump.data
    print("\nDecoded")
    print(f"  product           {c.product} (CIM {c.version})")
    print(f"  status            {s.flags!r}")
    print(f"  control mode      {s.control_mode!r}")
    print(f"  operation mode    {s.operation_mode!r}")
    print(f"  alarm / warning   {s.alarm!r} / {s.warning!r}")
    print(f"  flow / head       {d.volume_flow} m³/h / {d.head} bar")
    print(f"  power / speed     {d.power} W / {d.speed} rpm")
    print(f"  liquid            {d.liquid_temperature} °C")
    if report.failed:
        print("\nFailed to read:")
        for name, error in report.failed.items():
            print(f"  {name}: {str(error) or type(error).__name__}")
    if raw is not None:
        print("\nRaw registers")
        print(json.dumps(raw, indent=2))
    print(f"\n{reads} Modbus reads")
    return 0


raise SystemExit(asyncio.run(main()))
