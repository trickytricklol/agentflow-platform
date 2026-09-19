import pytest
from agentflow.optimization.evolution import RewardSpec, grade, final_text, release_candidate, workflow_dsl, feedback_examples, compile_system_prompt
from agentflow.optimization.bayesian import GaussianProcessOptimizer
from agentflow.optimization.embeddings import TfidfEmbedding


def test_reward_cannot_execute_code_or_accept_nan():
    with pytest.raises(ValueError):
        RewardSpec.parse({'metric':'eval(code)','success_weight':1,'token_penalty':0})
    with pytest.raises(ValueError):
        RewardSpec.parse({'metric':'exact_json','success_weight':1,'token_penalty':float('nan')})


def test_strict_grader_ignores_thinking_but_rejects_substrings_and_extra_keys():
    expected = {'route':'billing','priority':'P1'}
    assert grade('<think>route access</think>{"route":"billing","priority":"P1"}',expected)==(True,True)
    assert grade('billing P1',expected)==(False,False)
    assert grade('{"route":"billing","priority":"P1","extra":1}',expected)==(False,False)
    assert final_text('<think>unfinished billing P1')==''


def test_release_requires_validation_gain_and_preserves_parent():
    dsl = workflow_dsl('base')
    base = {'reward':0.5,'success':0.5}
    assert not release_candidate(dsl,'new',base,base)['released']
    release = release_candidate(dsl,'new',base,{'reward':0.75,'success':0.75})
    assert release['released']
    assert release['rollback']==dsl
    assert dsl['nodes'][1]['config']['prompt']=='base'
    assert release['dsl']['nodes'][1]['config']['prompt']=='new'


def test_gp_honors_budget_instead_of_exhaustive_search():
    candidates = ['alpha','beta','gamma','delta']
    calls = []
    def evaluate(p):
        calls.append(p)
        return 0.5
    result = GaussianProcessOptimizer(TfidfEmbedding(candidates)).run(candidates,evaluate,2)
    assert len(result.observations)==len(calls)==2
    assert len(set(calls))==2


def test_feedback_replay_only_reads_training_and_prioritizes_failures():
    train=[{'id':'a','text':'question','expected':{'route':'other','priority':'P2'}},
           {'id':'b','text':'outage','expected':{'route':'other','priority':'P0'}}]
    evaluation={'rows':[{'id':'a','correct':True},{'id':'b','correct':False}]}
    result=feedback_examples(['classify'],train,evaluation,count=1)[0]
    assert 'outage' in result
    assert 'question' not in result
    with pytest.raises(KeyError):
        feedback_examples(['classify'],train,{'rows':[{'id':'test-leak','correct':False}]})


def test_generated_strategy_is_explicitly_subordinate_to_policy():
    compiled=compile_system_prompt('security overrides billing','billing always wins')
    assert compiled.index('security overrides billing') < compiled.index('billing always wins')
    assert 'immutable policy wins' in compiled.lower()
