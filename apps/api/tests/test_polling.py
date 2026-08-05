from energy_manager.models import Connection, Device
from energy_manager.polling import _client_key, _effective_config, build_read_blocks, sample_quality

def test_groups_contiguous_registers():
    points=[{"key":"a","function_code":3,"address":100,"register_count":2},{"key":"b","function_code":3,"address":102,"register_count":2},{"key":"c","function_code":4,"address":102,"register_count":1}]
    blocks=build_read_blocks(points); assert len(blocks)==2 and blocks[0]["start"]==100 and blocks[0]["end"]==104
def test_respects_maximum():
    points=[{"key":"a","function_code":3,"address":0,"register_count":2},{"key":"b","function_code":3,"address":120,"register_count":2}]
    assert len(build_read_blocks(points,120)) == 2

def test_rejects_obvious_register_map_decode_errors():
    assert sample_quality("electrical.voltage.l1n", 230.4)[0] == "good"
    assert sample_quality("electrical.voltage.l1n", 1.14e-37)[0] == "bad"
    assert sample_quality("electrical.frequency", 630)[0] == "bad"
    assert sample_quality("electrical.active_power.total", float("nan"))[0] == "bad"
    assert sample_quality("storage.soc", 101)[0] == "bad"
    assert sample_quality("environment.irradiance.poa", 850)[0] == "good"


def test_direct_tcp_uses_device_endpoint_and_independent_session():
    connection = Connection(id="tcp-channel", name="TCP", kind="modbus_tcp", config={"port": 502, "timeout": 2})
    first = Device(id="meter-a", connection_id=connection.id, profile_id="p", name="A", unit_id=1, config={"host": "192.168.2.10", "port": 502})
    second = Device(id="meter-b", connection_id=connection.id, profile_id="p", name="B", unit_id=1, config={"host": "192.168.2.11", "port": 502})
    assert _effective_config(connection, first)["host"] == "192.168.2.10"
    assert _client_key(connection, first) != _client_key(connection, second)


def test_rtu_over_tcp_shares_gateway_session():
    connection = Connection(id="gateway", name="Gateway", kind="modbus_rtu_tcp", config={"host": "192.168.2.20", "port": 5020})
    first = Device(id="slave-a", connection_id=connection.id, profile_id="p", name="A", unit_id=1)
    second = Device(id="slave-b", connection_id=connection.id, profile_id="p", name="B", unit_id=2)
    assert _effective_config(connection, first)["host"] == "192.168.2.20"
    assert _client_key(connection, first) == _client_key(connection, second) == connection.id
