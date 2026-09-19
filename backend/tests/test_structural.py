import pytest
from agentflow.core import WorkflowGraph
from agentflow.providers.base import ModelResponse
from agentflow.optimization.evolution import RewardSpec
from agentflow.optimization.structural import StructuralEvaluator, structural_dsl, structural_release, composite_genome_vector


class SequenceProvider:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(messages)
        return ModelResponse(next(self.outputs), input_tokens=10, output_tokens=5)


CASE = {'id':'a','text':'Cannot sign in','expected':{'route':'access','priority':'P1'}}


@pytest.mark.parametrize('topology,outputs', [
    ('direct',['{"route":"access","priority":"P1"}']),
    ('decompose',['{"route":"access"}','{"priority":"P1"}']),
    ('review',['{"route":"other","priority":"P2"}','{"route":"access","priority":"P1"}'])])
def test_topology_executes_real_nodes_and_counts_all_calls(topology, outputs):
    provider = SequenceProvider(outputs)
    genome = {'topology':topology,'prompt':'classify'}
    result = StructuralEvaluator(provider,'test','immutable policy',RewardSpec()).evaluate(genome,[CASE])
    assert result['success'] == 1
    assert result['tokens'] == len(outputs)*15
    assert len(result['rows'][0]['trace']) == len(outputs)
    assert all('IMMUTABLE BUSINESS POLICY' in messages[0].content for messages in provider.calls)
    assert all('immutable policy' in messages[0].content.lower() for messages in provider.calls)
    assert all('expected' not in messages[-1].content for messages in provider.calls)
    if topology == 'review':
        assert 'untrusted_draft' in provider.calls[-1][-1].content


def test_decomposition_graph_and_schema_failure():
    genome = {'topology':'decompose','prompt':'classify'}
    graph = WorkflowGraph.from_dsl(structural_dsl(genome))
    assert set(graph.parents['end']) == {'route','priority'}
    provider = SequenceProvider(['not-json','{"priority":"P1"}'])
    result = StructuralEvaluator(provider,'test','policy',RewardSpec()).evaluate(genome,[CASE])
    assert result['success'] == 0
    assert result['rows'][0]['status'] == 'ERROR'
    assert result['tokens'] == 30


def test_release_changes_topology_and_can_rollback():
    parent = {'topology':'direct','prompt':'base'}
    child = {'topology':'review','prompt':'new'}
    base = {'reward':.5,'success':.5}
    assert not structural_release(parent,child,base,base)['released']
    released = structural_release(parent,child,base,{'reward':.75,'success':.75})
    assert released['released']
    assert len(released['dsl']['nodes']) == 4
    assert released['rollback'] == structural_dsl(parent)
    with pytest.raises(ValueError):
        structural_dsl({'topology':'arbitrary-code','prompt':'bad'})


def test_composite_vector_encodes_topology_and_stays_normalized():
    direct=composite_genome_vector({'topology':'direct'},[3.0,4.0])
    review=composite_genome_vector({'topology':'review'},[3.0,4.0])
    assert sum(v*v for v in direct)==pytest.approx(1.0)
    assert direct != review
    with pytest.raises(ValueError):
        composite_genome_vector({'topology':'unknown'},[1.0])
