from energy_manager.polling import build_read_blocks, sample_quality

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
