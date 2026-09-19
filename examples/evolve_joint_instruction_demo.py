"""MIPRO-inspired joint instruction/demo search with matched acquisition budgets."""
from __future__ import annotations
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'/'src'))
from agentflow.optimization.bayesian import GaussianProcessOptimizer,BayesianExperiment,BayesianObservation
from agentflow.optimization.demonstrations import strip_reference_examples,propose_demo_sets,compose_with_demos
from agentflow.optimization.embeddings import OllamaEmbeddingProvider
from agentflow.optimization.evolution import RewardSpec
from agentflow.optimization.structural import StructuralEvaluator,structural_release
from agentflow.providers import OpenAICompatibleProvider


def key(candidate): return json.dumps(candidate,sort_keys=True,ensure_ascii=False)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('acquisition'); parser.add_argument('--output',required=True)
    parser.add_argument('--budget',type=int,default=6); args=parser.parse_args()
    source=ROOT/args.acquisition; target=ROOT/args.output; target.mkdir(parents=True,exist_ok=True)
    if (target/'report.json').exists(): raise ValueError('use a fresh output directory')
    raw=source.read_bytes(); archive=json.loads(raw.decode('utf-8'))
    source_run=json.loads((ROOT/archive['source_directory']/'report.json').read_text(encoding='utf-8'))
    data=json.loads((ROOT/'evaluation'/'triage_v1.json').read_text(encoding='utf-8'))
    splits={s:[{'id':r[0],'text':r[1],'expected':{'route':r[2],'priority':r[3]}} for r in data[s]] for s in ('train','validation','test')}
    baseline=source_run['baseline']['genome']; baseline_key=key(baseline)
    base_train=archive['evaluations'][baseline_key]['result']; base_val=source_run['baseline']['validation']
    instructions=[]
    for item in archive['evaluations'].values():
        clean=strip_reference_examples(item['genome']['prompt'])
        if clean not in instructions: instructions.append(clean)
    demo_sets=propose_demo_sets(splits['train'],base_train,source_run['seed'],4)
    pool=[]
    for instruction in instructions:
        for demo_ids in demo_sets:
            genome={'topology':'direct','prompt':compose_with_demos(instruction,splits['train'],demo_ids)}
            candidate={'genome':genome,'instruction':instruction,'demo_ids':list(demo_ids)}
            if genome!=baseline and key(genome) not in {key(item['genome']) for item in pool}: pool.append(candidate)
    if args.budget>=len(pool): raise ValueError('budget must leave candidates unevaluated')
    provider=OpenAICompatibleProvider('http://127.0.0.1:11434/v1','local-ollama',120)
    evaluator=StructuralEvaluator(provider,source_run['model'],data['policy'],RewardSpec())
    embedder=OllamaEmbeddingProvider('nomic-embed-text'); optimizer=GaussianProcessOptimizer(embedder)
    vectors={key(baseline):embedder.embed(key(baseline))}
    for item in pool: vectors[key(item['genome'])]=embedder.embed(key(item['genome']))
    report={'source_sha256':hashlib.sha256(raw).hexdigest(),'source_path':args.acquisition,'seed':source_run['seed'],
        'model':source_run['model'],'protocol':'joint instruction/demo pool; shared cached outcomes; six candidate evaluations per arm',
        'budget':args.budget,'demo_sets':[list(group) for group in demo_sets],'pool':pool,
        'baseline':{'genome':baseline,'train':base_train,'validation':base_val},'evaluation_cache':{},'arms':{}}
    def save(): (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    def evaluate(candidate):
        identity=key(candidate['genome'])
        if identity not in report['evaluation_cache']:
            report['evaluation_cache'][identity]=evaluator.evaluate(candidate['genome'],splits['train'],source_run['seed']); save()
        return report['evaluation_cache'][identity]
    for strategy in ('random','gp_ei'):
        remaining=pool[:]; observed=[(baseline,base_train)]; steps=[]; rng=random.Random(source_run['seed'])
        for _ in range(args.budget):
            history=BayesianExperiment([BayesianObservation(key(g),score['reward']) for g,score in observed])
            chosen=rng.choice(remaining) if strategy=='random' else max(remaining,key=lambda item:(optimizer._expected_improvement(vectors[key(item['genome'])],history,vectors),key(item['genome'])))
            remaining.remove(chosen); result=evaluate(chosen); observed.append((chosen['genome'],result))
            steps.append({'candidate':chosen,'train':result}); print(strategy,chosen['demo_ids'],result['success'],flush=True)
        shortlist=sorted(steps,key=lambda item:(item['train']['reward'],-item['train']['tokens']),reverse=True)[:2]
        checked=[{'candidate':item['candidate'],'validation':evaluator.evaluate(item['candidate']['genome'],splits['validation'],source_run['seed'])} for item in shortlist]
        choices=[{'candidate':{'genome':baseline,'instruction':baseline['prompt'],'demo_ids':[]},'validation':base_val}]+checked
        winner=max(choices,key=lambda item:(item['validation']['reward'],-item['validation']['tokens']))
        release=structural_release(baseline,winner['candidate']['genome'],base_val,winner['validation'])
        deployed=winner['candidate']['genome'] if release['released'] else baseline
        report['arms'][strategy]={'steps':steps,'validation_candidates':checked,'winner':winner,'release':release,'deployed':deployed}; save()
    variants={'baseline':baseline,'random':report['arms']['random']['deployed'],'gp_ei':report['arms']['gp_ei']['deployed']}
    report['frozen_variants']=variants; report['test_rows']={name:[] for name in variants}; save()
    for index,case in enumerate(splits['test']):
        names=list(variants); random.Random(source_run['seed']+index).shuffle(names); cache={}
        for name in names:
            identity=key(variants[name])
            if identity not in cache: cache[identity]=evaluator.evaluate(variants[name],[case],source_run['seed'])['rows'][0]
            report['test_rows'][name].append(cache[identity].copy())
        save()
    report['test_summary']={name:{'success':sum(row['correct'] for row in rows)/len(rows),'n':len(rows),
        'tokens':sum(row['input_tokens']+row['output_tokens'] for row in rows)} for name,rows in report['test_rows'].items()}
    save(); print(json.dumps(report['test_summary'],indent=2))


if __name__=='__main__': main()
