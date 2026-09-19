import pytest
from agentflow.optimization.demonstrations import strip_reference_examples, propose_demo_sets, compose_with_demos


def test_demo_proposals_are_training_only_deterministic_and_diverse():
    train=[{'id':str(i),'text':'t'+str(i),'expected':{'route':route,'priority':priority}} for i,(route,priority) in enumerate([
        ('access','P1'),('billing','P1'),('security','P0'),('other','P2'),('access','P2')])]
    evaluation={'rows':[{'id':str(i),'correct':i not in (1,4)} for i in range(5)]}
    sets=propose_demo_sets(train,evaluation,17,4)
    assert sets==propose_demo_sets(train,evaluation,17,4)
    assert sets[0]==()
    assert all(set(group)<=set(str(i) for i in range(5)) for group in sets)
    assert any('1' in group for group in sets[1:])


def test_compose_strips_old_examples_and_rejects_nontraining_id():
    train=[{'id':'a','text':'ticket','expected':{'route':'other','priority':'P2'}}]
    prompt=compose_with_demos('rule\nReference training cases: OLD',train,('a',))
    assert 'OLD' not in prompt and 'ticket' in prompt
    assert strip_reference_examples(prompt)=='rule'
    with pytest.raises(ValueError): compose_with_demos('rule',train,('test-id',))
