# Written by Claude, guided by Chris.
"""The pump profile's register map, decoded over the mock backend."""

from __future__ import annotations

from datetime import date

import pytest
from modbus_connection import IllegalDataAddressError, ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit

from grundfos_modbus import (
    COMPONENTS,
    AlarmCode,
    ControlMode,
    ControlSource,
    FeedbackSensorUnit,
    FlowEstimationState,
    GrundfosPump,
    OperationMode,
    PumpStatus,
)
from grundfos_modbus._decode import bcd, bcd_date, bcd_pair


def test_nothing_before_the_first_read(pump: GrundfosPump) -> None:
    assert pump.data.liquid_temperature is None
    assert pump.status.flags is None
    assert pump.status.control_mode is None
    assert pump.cim.product is None


async def test_live_magna3(pump: GrundfosPump) -> None:
    report = await pump.async_update()
    assert report.updated == set(COMPONENTS)
    assert report.complete

    c = pump.cim
    assert c.product == "MAGNA3"
    assert c.version == "10.01"
    assert c.software_version is None
    assert c.software_date == date(2018, 6, 5)
    assert (c.genibus_tx_count, c.genibus_rx_count) == (222, 219)

    s = pump.status
    assert s.flags == (
        PumpStatus.ROTATING
        | PumpStatus.COUNTERCLOCKWISE
        | PumpStatus.ON
        | PumpStatus.AT_MAX_SPEED
    )
    assert s.flag(PumpStatus.ALARM) is False
    assert s.control_mode is ControlMode.CONSTANT_FLOW
    assert s.operation_mode is OperationMode.AUTO_CONTROL
    assert s.alarm is AlarmCode.NONE
    assert s.warning is AlarmCode.NONE
    assert s.feedback_sensor_unit is FeedbackSensorUnit.WATT
    assert s.flow_estimation_state is FlowEstimationState.WITHIN_RANGE
    assert s.control_source is ControlSource.DISPLAY
    assert s.process_feedback == 9.69
    assert s.nominal_frequency == 145.0
    assert (s.kp, s.ti) == (1.0, 8.0)

    d = pump.data
    assert d.head == 0.803
    assert d.differential_pressure == 0.803
    assert d.volume_flow == 2.2
    assert d.relative_performance == 98.03
    assert d.speed == 4288
    assert d.frequency == 141.2
    assert d.power == 199
    assert d.motor_current == 1.0
    assert d.dc_link_voltage == 198.0
    assert d.liquid_temperature == 47.23
    assert d.electronics_temperature == 42.0
    assert d.specific_energy == 103
    assert (d.operating_hours, d.powered_hours) == (5760, 5762)
    assert d.energy == 1264
    assert d.starts == 449
    assert d.user_setpoint == 63.81
    assert d.actual_setpoint == 60.77
    assert d.max_flow_limit == 133.0
    assert d.volume_1 == 13629.0
    assert d.clock == 27386 * 65536 + 34255


async def test_values_the_pump_does_not_supply_are_none(pump: GrundfosPump) -> None:
    await pump.async_update()
    d = pump.data
    assert d.motor_voltage is None
    assert d.inlet_pressure is None
    assert d.remote_temperature_1 is None
    assert d.remote_temperature_2 is None
    assert d.torque is None
    assert d.heat_power is None
    assert d.has_heat_meter is False
    # The heat counters read 0, not "not available", without a heat meter.
    assert d.heat_energy_1 == 0


async def test_offsets(unit: MockModbusUnit, pump: GrundfosPump) -> None:
    unit.holding[314] = 1500  # inlet pressure: 1.5 bar raw, offset -1 bar
    unit.holding[316] = 10250  # feed tank level: 102.5 m raw, offset -100 m
    unit.holding[336] = 29315  # remote temperature 2: 293.15 K
    await pump.async_update()
    assert pump.data.inlet_pressure == 0.5
    assert pump.data.feed_tank_level == 2.5
    assert pump.data.remote_temperature_2 == 20.0


async def test_heat_meter(unit: MockModbusUnit, pump: GrundfosPump) -> None:
    unit.holding[353], unit.holding[354] = 0, 4200  # 4200 W
    unit.holding[355] = 550  # 5.50 K
    await pump.async_update()
    assert pump.data.has_heat_meter is True
    assert pump.data.heat_power == 4200
    assert pump.data.heat_differential_temperature == 5.5


async def test_alarm(unit: MockModbusUnit, pump: GrundfosPump) -> None:
    unit.holding[200] = 8896 | PumpStatus.ALARM
    unit.holding[204] = 57  # dry running
    unit.holding[205] = 250  # not in the profile's table
    await pump.async_update()
    assert pump.status.flag(PumpStatus.ALARM) is True
    assert pump.status.alarm is AlarmCode.DRY_RUNNING
    assert pump.status.warning == 250


async def test_unknown_product(unit: MockModbusUnit, pump: GrundfosPump) -> None:
    unit.holding[29], unit.holding[30] = 99, 1
    unit.holding[33], unit.holding[34] = 0x0102, 0x0304
    await pump.async_update()
    assert pump.cim.product is None
    assert pump.cim.software_version == "01.02.03.04"


async def test_three_block_reads(unit: MockModbusUnit, pump: GrundfosPump) -> None:
    await pump.async_update()
    blocks = sorted(
        (event.register_type, event.address, event.count) for event in unit.read_events
    )
    assert blocks == [("holding", 20, 17), ("holding", 200, 25), ("holding", 300, 62)]


async def test_a_refused_block_only_fails_itself(
    unit: MockModbusUnit, pump: GrundfosPump
) -> None:
    unit.fail_read(20, IllegalDataAddressError())
    report = await pump.async_update()
    assert report.updated == {"status", "data"}
    assert set(report.failed) == {"cim"}
    assert pump.data.liquid_temperature == 47.23


async def test_a_powered_off_pump_raises(
    unit: MockModbusUnit, pump: GrundfosPump
) -> None:
    unit.fail_requests(ModbusTimeoutError())
    with pytest.raises(ModbusTimeoutError):
        await pump.async_update()


@pytest.mark.parametrize(
    ("raw", "expected"), [(0x2018, 2018), (0x0506, 506), (0x0000, 0)]
)
def test_bcd(raw: int, expected: int) -> None:
    assert bcd(raw) == expected


def test_bcd_helpers() -> None:
    assert bcd_pair(None) is None
    assert bcd_pair(0x1001) == "10.01"
    assert bcd_date(0x3102, 0x2018) is None  # 31 February
    assert bcd_date(None, 0x2018) is None


async def test_raw_dump_covers_all_three_blocks(pump: GrundfosPump) -> None:
    raw = await pump.async_read_raw()
    holding = raw["holding"]
    assert holding[30] == 10  # unit type: MAGNA3
    assert holding[202] == 7  # control mode: constant flow
    assert holding[321] == 32038  # liquid temperature
