from energy_manager.kpi import counter_delta, unattributed_energy

def test_normal_delta(): assert counter_delta(10,15).value == 5
def test_reset():
    result=counter_delta(100,3); assert result.value == 3 and result.quality == "estimated"
def test_overflow(): assert counter_delta(990,5,1000).value == 15
def test_missing(): assert counter_delta(None,4).quality == "missing"
def test_unattributed():
    result=unattributed_energy(100,[40,42]); assert result["value"] == 18 and result["percentage"] == 18
def test_unattributed_missing(): assert unattributed_energy(100,[40,None])["quality"] == "missing"

