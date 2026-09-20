from agentflow.benchmarks.bfcl import BFCLCall, score_bfcl_call


GROUND=[{"area":{"base":[10],"height":[5],"unit":["units",""]}}]


def test_bfcl_call_accepts_documented_values_and_optional_omission():
    assert score_bfcl_call(BFCLCall("area",{"base":10,"height":5}),GROUND)
    assert score_bfcl_call(BFCLCall("area",{"base":10.0,"height":5,"unit":"units"}),GROUND)


def test_bfcl_call_rejects_wrong_name_missing_required_and_unknown_arguments():
    assert not score_bfcl_call(BFCLCall("other",{"base":10,"height":5}),GROUND)
    assert not score_bfcl_call(BFCLCall("area",{"base":10}),GROUND)
    assert not score_bfcl_call(BFCLCall("area",{"base":10,"height":5,"extra":1}),GROUND)
