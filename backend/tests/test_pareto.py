import json
import pytest
from agentflow.optimization.pareto import score_vector, component_score_vector, instance_pareto_front, hybrid_pareto_front, complementary_pairs, disagreement_batch, SystemAwareMerger
from agentflow.providers.base import ModelResponse


def evaluation(bits):
    return {'rows':[{'id':case_id,'correct':bool(value)} for case_id,value in zip(('a','b','c'),bits)]}


def test_instance_pareto_preserves_complementary_specialists():
    values={'left':evaluation((1,1,0)),'right':evaluation((0,1,1)),'weak':evaluation((0,1,0))}
    assert score_vector(values['left'],('a','b','c'))==(1.0,1.0,0.0)
    assert instance_pareto_front(values,('a','b','c'))==['left','right']
    pair=complementary_pairs(values,('a','b','c'))[0]
    assert pair['complementary_gain']==1
    assert pair['union_coverage']==3


def test_disagreement_batch_uses_only_supplied_cases_and_joint_failures_next():
    cases=[{'id':key} for key in ('a','b','c')]
    batch=disagreement_batch(evaluation((1,0,0)),evaluation((0,0,1)),cases,3)
    assert [case['id'] for case in batch]==['a','c','b']
    with pytest.raises(ValueError):
        score_vector(evaluation((1,0,0)),('a','b'))


def test_hybrid_frontier_preserves_partial_objective_specialists():
    route={'rows':[{'id':'a','correct':False,'valid_json':True,'output':'{"route":"security","priority":"P2"}','expected':{'route':'security','priority':'P0'}}]}
    priority={'rows':[{'id':'a','correct':False,'valid_json':True,'output':'{"route":"other","priority":"P0"}','expected':{'route':'security','priority':'P0'}}]}
    weak={'rows':[{'id':'a','correct':False,'valid_json':False,'output':'bad','expected':{'route':'security','priority':'P0'}}]}
    assert component_score_vector(route,('a',))==(1.0,1.0,0.0)
    assert hybrid_pareto_front({'route':route,'priority':priority,'weak':weak},('a',))==['priority','route']
    assert complementary_pairs({'route':route,'priority':priority},('a',),['route','priority'],'hybrid')[0]['complementary_gain']==1


def test_system_merge_is_audited_before_returning_child():
    class Provider:
        def __init__(self): self.calls=[]
        def chat(self,messages,**kwargs):
            self.calls.append(messages)
            payload={'topology':'direct','prompt':'Draft strategy with enough detail to pass validation safely.'} if len(self.calls)==1 else {'topology':'review','prompt':'Audited complete strategy with immutable policy precedence and exact JSON output.'}
            return ModelResponse(json.dumps(payload),input_tokens=10,output_tokens=5)
    provider=Provider(); merger=SystemAwareMerger(provider,'teacher')
    left_eval={'rows':[{'id':'a','correct':True,'output':'ok'}]}; right_eval={'rows':[{'id':'a','correct':False,'output':'bad'}]}
    training=[{'id':'a','text':'ticket','expected':{'route':'other','priority':'P2'}}]
    child=merger.merge({'topology':'direct','prompt':'left'},{'topology':'review','prompt':'right'},left_eval,right_eval,training,'policy',1)
    assert child['topology']=='review'
    assert len(provider.calls)==2
    assert merger.log[0]['input_tokens']==20
