"""Full-table audit of SafeFlow-Evo acquisition; train/validation only."""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import random
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'/'src'))
from agentflow.optimization import BayesianExperiment,GaussianProcessOptimizer,OllamaEmbeddingProvider
from agentflow.optimization.bayesian import BayesianObservation
from agentflow.optimization.evolution import RewardSpec
from agentflow.optimization.safe_bo import ConstrainedCostAwareOptimizer,mixed_candidate_vector,estimated_inference_cost,validation_feasible
from agentflow.optimization.structural import StructuralEvaluator
from agentflow.providers import OpenAICompatibleProvider


def key(candidate): return json.dumps(candidate['genome'],sort_keys=True,ensure_ascii=False)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('joint_report'); parser.add_argument('--output',required=True); parser.add_argument('--budget',type=int,default=6)
    args=parser.parse_args(); source=ROOT/args.joint_report; target=ROOT/args.output
    raw=source.read_bytes(); joint=json.loads(raw.decode('utf-8')); data=json.loads((ROOT/'evaluation'/'triage_v1.json').read_text(encoding='utf-8'))
    splits={s:[{'id':r[0],'text':r[1],'expected':{'route':r[2],'priority':r[3]}} for r in data[s]] for s in ('train','validation')}
    baseline={'genome':joint['baseline']['genome'],'instruction':joint['baseline']['genome']['prompt'],'demo_ids':[]}
    candidates=joint['pool']; universe=[case['id'] for case in splits['train']]
    if target.exists():
        report=json.loads(target.read_text(encoding='utf-8'))
        if report['source_sha256']!=hashlib.sha256(raw).hexdigest(): raise ValueError('source changed')
    else:
        report={'source_sha256':hashlib.sha256(raw).hexdigest(),'source_path':args.joint_report,'budget':args.budget,
                'protocol':'full train/validation audit table; test unseen; exact random subsets; fixed mixed weights',
                'model':joint['model'],'seed':joint['seed'],'candidates':candidates,'evaluations':{}}
    provider=OpenAICompatibleProvider('http://127.0.0.1:11434/v1','local-ollama',120)
    evaluator=StructuralEvaluator(provider,joint['model'],data['policy'],RewardSpec())
    for index,candidate in enumerate([baseline]+candidates):
        identity=key(candidate)
        if identity not in report['evaluations']:
            report['evaluations'][identity]={'candidate':candidate}
        for split in ('train','validation'):
            if split not in report['evaluations'][identity]:
                report['evaluations'][identity][split]=evaluator.evaluate(candidate['genome'],splits[split],joint['seed'])
                target.parent.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                print('measured',index,split,report['evaluations'][identity][split]['success'],flush=True)
    table=report['evaluations']; baseline_key=key(baseline); base_val=table[baseline_key]['validation']
    quality={identity:item['train']['reward'] for identity,item in table.items()}
    feasible={identity:float(identity==baseline_key or validation_feasible(base_val,item['validation'])) for identity,item in table.items()}
    costs={key(candidate):estimated_inference_cost(candidate) for candidate in [baseline]+candidates}
    embedder=OllamaEmbeddingProvider('nomic-embed-text'); gp=GaussianProcessOptimizer(embedder); safe=ConstrainedCostAwareOptimizer(gp,cost_power=.5,min_feasibility_observations=2)
    text_vectors={identity:embedder.embed(item['candidate']['genome']['prompt']) for identity,item in table.items()}
    mixed_vectors={identity:mixed_candidate_vector(item['candidate'],text_vectors[identity],universe) for identity,item in table.items()}
    candidate_keys=[key(candidate) for candidate in candidates]; reference_cost=costs[baseline_key]
    def trajectory(method,vectors):
        observed=[baseline_key]; remaining=candidate_keys[:]; steps=[]
        for _ in range(args.budget):
            qhist=BayesianExperiment([BayesianObservation(identity,quality[identity]) for identity in observed])
            fhist=BayesianExperiment([BayesianObservation(identity,feasible[identity]) for identity in observed])
            if method=='random': selected=random.Random(joint['seed']+len(steps)).choice(remaining)
            elif method=='safe': selected=max(remaining,key=lambda identity:(safe.acquisition(vectors[identity],qhist,fhist,vectors,costs[identity],reference_cost),identity))
            else: selected=max(remaining,key=lambda identity:(gp._expected_improvement(vectors[identity],qhist,vectors),identity))
            remaining.remove(selected); observed.append(selected)
            steps.append({'candidate':table[selected]['candidate'],'quality':quality[selected],'feasible':bool(feasible[selected]),'estimated_cost':costs[selected]})
        feasible_scores=[quality[identity] for identity in observed if feasible[identity]]
        return {'steps':steps,'best_feasible_quality':max(feasible_scores),'estimated_cost':sum(step['estimated_cost'] for step in steps)}
    trajectories={'random_seeded':trajectory('random',mixed_vectors),'gp_text':trajectory('gp',text_vectors),
                  'gp_mixed':trajectory('gp',mixed_vectors),'safeflow':trajectory('safe',mixed_vectors)}
    subset_best=[]
    for subset in itertools.combinations(candidate_keys,args.budget):
        scores=[quality[identity] for identity in (baseline_key,)+subset if feasible[identity]]; subset_best.append(max(scores))
    oracle=max(quality[identity] for identity in [baseline_key]+candidate_keys if feasible[identity])
    report['result']={'feasible_candidates':sum(feasible[identity] for identity in candidate_keys),'oracle_feasible_quality':oracle,
        'random_exact':{'subsets':len(subset_best),'mean_best_feasible':sum(subset_best)/len(subset_best),
                        'probability_find_oracle':sum(value==oracle for value in subset_best)/len(subset_best)},
        'trajectories':trajectories,'weights':{'text':.55,'topology':.25,'demos':.20},'cost_power':.5,
        'feasibility_warmup':'inactive until at least two observations and both labels are present'}
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(report['result'],indent=2))


if __name__=='__main__': main()
