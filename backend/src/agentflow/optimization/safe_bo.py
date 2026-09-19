"""SafeFlow-Evo mixed-space, cost-aware constrained Bayesian acquisition."""
from __future__ import annotations
import math

from .bayesian import BayesianExperiment,GaussianProcessOptimizer
from .structural import TOPOLOGIES


DEFAULT_WEIGHTS={'text':0.55,'topology':0.25,'demos':0.20}


def mixed_candidate_vector(candidate,prompt_vector,demo_universe,weights=None):
    weights=dict(weights or DEFAULT_WEIGHTS)
    if set(weights)!= {'text','topology','demos'} or any(value<0 for value in weights.values()) or not math.isclose(sum(weights.values()),1.0):
        raise ValueError('mixed-kernel weights must be nonnegative and sum to one')
    topology=candidate['genome']['topology']
    if topology not in TOPOLOGIES: raise ValueError('unsupported topology')
    norm=math.sqrt(sum(value*value for value in prompt_vector)) or 1.0
    text=[value/norm*math.sqrt(weights['text']) for value in prompt_vector]
    topology_part=[math.sqrt(weights['topology']) if name==topology else 0.0 for name in TOPOLOGIES]
    demos=set(candidate.get('demo_ids',()))
    if not demos<=set(demo_universe): raise ValueError('demo outside frozen universe')
    demo_part=[0.0]*(len(demo_universe)+1)
    if demos:
        scale=math.sqrt(weights['demos']/len(demos))
        for index,case_id in enumerate(demo_universe):
            if case_id in demos: demo_part[index]=scale
    else:
        demo_part[-1]=math.sqrt(weights['demos'])
    return text+topology_part+demo_part


def estimated_inference_cost(candidate):
    """Pre-evaluation relative cost proxy; no outcome or test information."""
    calls={'direct':1,'decompose':2,'review':2}[candidate['genome']['topology']]
    prompt_units=max(1,len(candidate['genome']['prompt'])/4)
    return calls*(128+prompt_units)


def validation_feasible(baseline,candidate):
    """Single-run feasibility proxy for acquisition; publication uses repeated gate."""
    if candidate['success'] <= baseline['success']: return False
    def slices(result):
        values={}
        for row in result['rows']:
            for field in ('route','priority'):
                group=field+':'+row['expected'][field]
                correct,count=values.get(group,(0,0)); values[group]=(correct+int(row['correct']),count+1)
        return values
    base,child=slices(baseline),slices(candidate)
    return all(child[group][0]/child[group][1] >= correct/count for group,(correct,count) in base.items())


class ConstrainedCostAwareOptimizer:
    def __init__(self,gp:GaussianProcessOptimizer,cost_power=0.5,feasibility_threshold=0.5,min_feasibility_observations=2):
        if cost_power<0 or not 0<feasibility_threshold<1: raise ValueError('invalid constrained optimizer configuration')
        if min_feasibility_observations<1: raise ValueError('invalid feasibility warmup')
        self.gp=gp; self.cost_power=cost_power; self.feasibility_threshold=feasibility_threshold
        self.min_feasibility_observations=min_feasibility_observations

    def feasibility_probability(self,vector,experiment,vectors):
        labels={item.score for item in experiment.observations}
        if len(experiment.observations)<self.min_feasibility_observations or len(labels)<2: return 1.0
        mean,variance=self.gp.posterior(vector,experiment,vectors)
        z=(mean-self.feasibility_threshold)/math.sqrt(variance)
        return min(.999,max(.001,.5*(1+math.erf(z/math.sqrt(2)))))

    def acquisition(self,vector,quality_history,feasibility_history,vectors,cost,reference_cost=1.0):
        if cost<=0 or reference_cost<=0: raise ValueError('costs must be positive')
        improvement=self.gp._expected_improvement(vector,quality_history,vectors)
        probability=self.feasibility_probability(vector,feasibility_history,vectors)
        return improvement*probability/(cost/reference_cost)**self.cost_power
