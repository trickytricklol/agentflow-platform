"""Repeated, matched validation audit with route/priority non-regression gates."""
import json
import random
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'/'src'))
from agentflow.optimization.evolution import RewardSpec
from agentflow.optimization.structural import StructuralEvaluator,risk_aware_release
from agentflow.providers import OpenAICompatibleProvider


def key(genome): return json.dumps(genome,sort_keys=True,ensure_ascii=False)


def main():
    folder=Path(sys.argv[1]); target=folder/'stability.json'
    if target.exists(): raise ValueError('preserve prior stability audit')
    experiment=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    data=json.loads((ROOT/'evaluation'/'triage_v1.json').read_text(encoding='utf-8'))
    cases=[{'id':r[0],'text':r[1],'expected':{'route':r[2],'priority':r[3]}} for r in data['validation']]
    baseline=experiment['baseline']['genome']; candidates={arm:value['winner']['candidate']['genome'] for arm,value in experiment['arms'].items()}
    seeds=[experiment['seed'],experiment['seed']+12,experiment['seed']+26]
    evaluator=StructuralEvaluator(OpenAICompatibleProvider('http://127.0.0.1:11434/v1','local-ollama',120),experiment['model'],data['policy'],RewardSpec())
    result={'seeds':seeds,'baseline':baseline,'candidates':candidates,'runs':{'baseline':[]},'decisions':{}}
    for arm in candidates: result['runs'][arm]=[]
    for seed in seeds:
        variants={'baseline':baseline}; variants.update(candidates); cache={}
        names=list(variants); random.Random(seed).shuffle(names)
        for name in names:
            identity=key(variants[name])
            if identity not in cache: cache[identity]=evaluator.evaluate(variants[name],cases,seed)
            result['runs'][name].append(cache[identity])
        target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    for arm,genome in candidates.items():
        result['decisions'][arm]=risk_aware_release(baseline,genome,result['runs']['baseline'],result['runs'][arm])
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({arm:{'released':decision['released'],'baseline_mean':decision['baseline_mean'],
        'candidate_mean':decision['candidate_mean'],'reason':decision['reason']} for arm,decision in result['decisions'].items()},indent=2))


if __name__=='__main__': main()
