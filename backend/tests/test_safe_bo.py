import math
import pytest
from agentflow.optimization import BayesianExperiment,GaussianProcessOptimizer,TfidfEmbedding
from agentflow.optimization.bayesian import BayesianObservation
from agentflow.optimization.safe_bo import mixed_candidate_vector,estimated_inference_cost,validation_feasible,ConstrainedCostAwareOptimizer


def test_mixed_vector_separates_topology_and_demo_sets_with_unit_norm():
    base={'genome':{'topology':'direct','prompt':'p'},'demo_ids':['a']}
    other={'genome':{'topology':'review','prompt':'p'},'demo_ids':['b']}
    left=mixed_candidate_vector(base,[3,4],['a','b']); right=mixed_candidate_vector(other,[3,4],['a','b'])
    assert sum(value*value for value in left)==pytest.approx(1.0)
    assert left!=right
    assert estimated_inference_cost(other)>estimated_inference_cost(base)
    with pytest.raises(ValueError): mixed_candidate_vector(base,[1],['b'])


def test_gp_posterior_and_constraint_probability_respond_to_observations():
    embedding=TfidfEmbedding(['base','candidate']); gp=GaussianProcessOptimizer(embedding,noise=.01)
    vectors={'base':[1.0,0.0],'candidate':[0.0,1.0]}; vector=vectors['candidate']
    quality=BayesianExperiment([BayesianObservation('base',.5)])
    feasible=BayesianExperiment([BayesianObservation('candidate',1.0),BayesianObservation('base',1.0)])
    unsafe=BayesianExperiment([BayesianObservation('candidate',0.0),BayesianObservation('base',1.0)])
    optimizer=ConstrainedCostAwareOptimizer(gp)
    assert optimizer.feasibility_probability(vector,feasible,vectors)>.9
    assert optimizer.feasibility_probability(vector,unsafe,vectors)<.1
    assert optimizer.acquisition(vector,quality,feasible,vectors,1) > optimizer.acquisition(vector,quality,unsafe,vectors,1)
    mean,variance=gp.posterior(vector,unsafe,vectors)
    assert mean<.1 and 0<variance<.02
    assert math.isfinite(mean)


def test_feasibility_requires_strict_gain_and_no_business_slice_regression():
    def result(bits):
        rows=[{'expected':{'route':'security','priority':'P1'},'correct':bits[0]},
              {'expected':{'route':'other','priority':'P2'},'correct':bits[1]},
              {'expected':{'route':'other','priority':'P1'},'correct':bits[2]}]
        return {'success':sum(bits)/3,'rows':rows}
    baseline=result((1,0,0))
    assert validation_feasible(baseline,result((1,1,0)))
    assert not validation_feasible(baseline,result((0,1,1)))
    assert not validation_feasible(baseline,baseline)
