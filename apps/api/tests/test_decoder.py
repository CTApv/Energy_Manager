import struct
import pytest
from energy_manager.decoder import decode_registers

def words(fmt, value): return list(struct.unpack(">" + "H" * (struct.calcsize(fmt) // 2), struct.pack(">" + fmt, value)))

@pytest.mark.parametrize("kind,fmt,value", [("int16","h",-12),("uint16","H",65000),("int32","i",-123456),("uint32","I",4000000000),("int64","q",-123456789012),("uint64","Q",123456789012),("float32","f",42.5),("float64","d",42.125)])
def test_numeric_types(kind, fmt, value): assert decode_registers(words(fmt,value),{"data_type":kind}) == pytest.approx(value)

def test_word_order(): assert decode_registers([0, 0x4228], {"data_type":"float32","word_order":"little"}) == pytest.approx(42)
def test_byte_order(): assert decode_registers([0x2842, 0], {"data_type":"float32","byte_order":"little"}) == pytest.approx(42)
def test_scaling_offset(): assert decode_registers([100], {"data_type":"uint16","scale":0.1,"offset":2}) == 12
def test_boolean_and_bit():
    assert decode_registers([1], {"data_type":"boolean"}) is True
    assert decode_registers([8], {"data_type":"bit_field","bit":3}) is True
def test_ascii(): assert decode_registers([0x454d,0x0000],{"data_type":"ascii"}) == "EM"

def test_enum_can_preserve_numeric_value_for_telemetry():
    definition = {"data_type": "uint16", "enum": {"1": "Running"}}
    assert decode_registers([1], definition) == "Running"
    assert decode_registers([1], definition, resolve_enum=False) == 1

