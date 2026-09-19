"""Matched-budget acquisition benchmark over one fixed, fully measured candidate pool."""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import math
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'/'src'))
from agentflow.optimization.bayesian import GaussianProcessOptimizer, BayesianExperiment, BayesianObservation
from agentflow.optimization.embeddings import OllamaEmbeddingProvider
from agentflow.optimization.evolution import RewardSpec
from agentflow.optimization.structural import StructuralEvaluator, composite_genome_vector
from agentflow.providers import OpenAICompatibleProvider


def key(genome):
    return json.dumps(genome,sort_keys=True,ensure_ascii=False)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('--output',required=True,help='JSON path, preferably evaluation/results/<run>/acquisition.json')
    parser.add_argument('--budget',type=int,default=4)
    args=parser.parse_args()
    source=ROOT/args.source
    target=ROOT/args.output
    source_raw=(source/'report.json').read_bytes()
    source_report=json.loads(source_raw.decode('utf-8'))
    dataset=json.loads((ROOT/'evaluation'/'triage_v1.json').read_text(encoding='utf-8'))
    train=[{'id':r[0],'text':r[1],'expected':{'route':r[2],'priority':r[3]}} for r in dataset['train']]
    baseline=source_report['baseline']['genome']
    candidates=source_report['pool']
    if not 0 < args.budget < len(candidates):
        raise ValueError('budget must be smaller than pool')
    if target.exists():
        report=json.loads(target.read_text(encoding='utf-8'))
        if report['source_report_sha256'] != hashlib.sha256(source_raw).hexdigest():
            raise ValueError('source report changed')
    else:
        report={'source_report_sha256':hashlib.sha256(source_raw).hexdigest(),
                'protocol':'fixed pool; training split only; four candidate evaluations; exhaustive random-subset distribution',
                'budget':args.budget,'topology_weight':0.35,'evaluations':{}}
    report['source_directory']=source.relative_to(ROOT).as_posix()
    evaluator=StructuralEvaluator(OpenAICompatibleProvider('http://127.0.0.1:11434/v1','local-ollama',120),
                                  source_report['model'],dataset['policy'],RewardSpec())
    # Full measurement is an audit-table construction cost, not charged as an online acquisition run.
    for index,genome in enumerate([baseline]+candidates):
        identity=key(genome)
        if identity not in report['evaluations']:
            result=evaluator.evaluate(genome,train,source_report['seed'])
            report['evaluations'][identity]={'index':index,'genome':genome,'result':result}
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print('measured',index,genome['topology'],result['success'],flush=True)
    measured=report['evaluations']
    score={identity:item['result']['reward'] for identity,item in measured.items()}
    base_key=key(baseline)
    candidate_keys=[key(item) for item in candidates]
    embedder=OllamaEmbeddingProvider('nomic-embed-text')
    prompt_vectors={identity:embedder.embed(measured[identity]['genome']['prompt']) for identity in measured}
    vector_sets={
        'gp_prompt':prompt_vectors,
        'gp_hybrid':{identity:composite_genome_vector(measured[identity]['genome'],vector,report['topology_weight']) for identity,vector in prompt_vectors.items()}}
    optimizer=GaussianProcessOptimizer(embedder)
    trajectories={}
    for name,vectors in vector_sets.items():
        observed=[base_key]
        remaining=candidate_keys[:]
        steps=[]
        for _ in range(args.budget):
            history=BayesianExperiment([BayesianObservation(identity,score[identity]) for identity in observed])
            selected=max(remaining,key=lambda identity:(optimizer._expected_improvement(vectors[identity],history,vectors),identity))
            remaining.remove(selected); observed.append(selected)
            steps.append({'candidate':measured[selected]['genome'],'score':score[selected],
                          'tokens':measured[selected]['result']['tokens']})
        trajectories[name]={'steps':steps,'best_score':max(score[i] for i in observed),
                            'tokens':sum(step['tokens'] for step in steps)}
    subset_bests=[max(score[i] for i in subset) for subset in itertools.combinations(candidate_keys,args.budget)]
    oracle=max(score[i] for i in candidate_keys)
    report['result']={'candidate_count':len(candidate_keys),'oracle_score':oracle,
                      'random_exact':{'subsets':len(subset_bests),'mean_best':sum(subset_bests)/len(subset_bests),
                                      'probability_find_oracle':sum(value==oracle for value in subset_bests)/len(subset_bests),
                                      'p50_best':sorted(subset_bests)[len(subset_bests)//2]},
                      'trajectories':trajectories,
                      'audit_table_tokens':sum(item['result']['tokens'] for item in measured.values())}
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report['result'],ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
