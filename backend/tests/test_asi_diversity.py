import json

from agentflow.providers.base import ModelResponse
from agentflow.optimization.evolution import diagnose_output, grade, FeedbackMutator
from agentflow.optimization.bayesian import GaussianProcessOptimizer, BayesianExperiment, BayesianObservation
from agentflow.optimization.embeddings import EmbeddingProvider


# --- ASI / blame-aware attribution -----------------------------------------

def test_diagnose_locates_wrong_route_not_priority():
    diag = diagnose_output('{"route":"login","priority":"P0"}', {'route': 'other', 'priority': 'P0'})
    assert diag['correct'] is False
    assert diag['format_ok'] is True
    assert diag['route']['correct'] is False
    assert diag['route']['actual'] == 'login'
    assert diag['route']['expected'] == 'other'
    assert diag['priority']['correct'] is True
    assert any('route' in fault for fault in diag['faults'])
    assert not any('priority' in fault for fault in diag['faults'])


def test_diagnose_marks_bad_schema_and_unparseable():
    bad = diagnose_output('{"route":"login"}', {'route': 'other', 'priority': 'P0'})
    assert bad['correct'] is False and bad['format_ok'] is False
    assert bad['faults']
    raw = diagnose_output('not json', {'route': 'other', 'priority': 'P0'})
    assert raw['correct'] is False and raw['format_ok'] is False
    assert raw['faults'] == ['output is not parseable JSON']


def test_grade_backward_compatible_with_diagnose():
    expected = {'route': 'billing', 'priority': 'P1'}
    assert grade('<think>ok</think>{"route":"billing","priority":"P1"}', expected) == (True, True)
    assert grade('{"route":"billing","priority":"P1","extra":1}', expected) == (False, False)
    assert grade('billing P1', expected) == (False, False)


class _JsonProvider:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def chat(self, messages, **kwargs):
        self.requests.append(messages)
        return ModelResponse(json.dumps(self.payload), input_tokens=1, output_tokens=1)


def _mutator_case(asi):
    provider = _JsonProvider({'diagnosis': 'd', 'candidates': ['c1', 'c2', 'c3']})
    mut = FeedbackMutator(provider, 'teacher', asi=asi)
    training = [{'id': 'a', 'text': 'outage now', 'expected': {'route': 'other', 'priority': 'P0'}}]
    evaluation = {'rows': [{'id': 'a', 'correct': False,
                            'output': '{"route":"login","priority":"P0"}',
                            'expected': {'route': 'other', 'priority': 'P0'}}]}
    candidates = mut.mutate('parent strategy', training, evaluation, 'policy', seed=0)
    return provider, candidates


def test_asi_opt_in_injects_per_component_faults():
    provider, candidates = _mutator_case(asi=True)
    assert len(candidates) == 3
    raw = provider.requests[0][0].content.split('\n/no_think', 1)[0]
    request = json.loads(raw)
    failure = request['training_failures'][0]
    assert 'faults' in failure
    assert any('route' in fault for fault in failure['faults'])
    assert 'component' in request['instruction'].lower()


def test_asi_off_preserves_legacy_feedback_shape():
    provider, candidates = _mutator_case(asi=False)
    assert len(candidates) == 3
    raw = provider.requests[0][0].content.split('\n/no_think', 1)[0]
    request = json.loads(raw)
    failure = request['training_failures'][0]
    assert 'faults' not in failure
    assert set(failure) == {'input', 'expected', 'actual'}


# --- Diversity-aware acquisition -------------------------------------------

class _StaticEmbedding(EmbeddingProvider):
    def __init__(self, vectors):
        self.vectors = vectors

    def embed(self, text):
        return list(self.vectors[text])


def test_diversity_weight_prefers_far_untouched_region():
    emb = _StaticEmbedding({'p1': [0.0, 0.0], 'p2': [1.0, 0.0], 'p3': [2.0, 0.0], 'p4': [3.0, 0.0]})
    seeded = BayesianExperiment(observations=[BayesianObservation('p1', 0.9)])
    picked = []
    gp = GaussianProcessOptimizer(emb, diversity_weight=1.0)
    gp.run(['p1', 'p2', 'p3', 'p4'], lambda p: picked.append(p) or 0.5, rounds=1, experiment=seeded)
    # Pure novelty: farthest unobserved point from p1 is p4.
    assert picked == ['p4']


def test_diversity_weight_zero_keeps_classic_ei_selection():
    emb = _StaticEmbedding({'p1': [0.0, 0.0], 'p2': [1.0, 0.0], 'p3': [2.0, 0.0]})
    seeded = BayesianExperiment(observations=[BayesianObservation('p1', 0.9)])
    picked = []
    GaussianProcessOptimizer(emb, diversity_weight=0.0).run(
        ['p1', 'p2', 'p3'], lambda p: picked.append(p) or 0.5, rounds=2, experiment=seeded)
    assert sorted(picked) == ['p2', 'p3']


def test_invalid_exploration_config_rejected():
    emb = _StaticEmbedding({'a': [1.0]})
    try:
        GaussianProcessOptimizer(emb, diversity_weight=1.5)
        raise AssertionError('diversity_weight out of range must raise')
    except ValueError:
        pass
    try:
        GaussianProcessOptimizer(emb, xi=-0.1)
        raise AssertionError('negative xi must raise')
    except ValueError:
        pass
