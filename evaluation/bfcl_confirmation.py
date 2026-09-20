"""Run a frozen BFCL-derived winner once on the registered confirmation IDs."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'/'src'))
from agentflow.benchmarks import evaluate_bfcl_case
from agentflow.providers import OpenAICompatibleProvider,OllamaProvider
from bfcl_native_eval import DATA,ANSWERS,DEFAULT_PROMPT,read_jsonl


def summarize(rows):
    values=list(rows.values()); correct=sum(row['correct'] for row in values); n=len(values)
    z=1.959963984540054; denominator=1+z*z/n; center=(correct/n+z*z/(2*n))/denominator
    half=z*math.sqrt((correct/n)*(1-correct/n)/n+z*z/(4*n*n))/denominator
    return {'correct':correct,'n':n,'accuracy':correct/n,'wilson95':[center-half,center+half],
            'tokens':sum(row['input_tokens']+row['output_tokens'] for row in values)}


def exact_sign_p(improved,regressed):
    discordant=improved+regressed
    if not discordant: return 1.0
    choose=lambda n,k: math.factorial(n)//(math.factorial(k)*math.factorial(n-k))
    tail=sum(choose(discordant,k) for k in range(min(improved,regressed)+1))/(2**discordant)
    return min(1.0,2*tail)


def evaluate_or_error(provider,model,case,ground_truth,prompt,seed):
    try: return evaluate_bfcl_case(provider,model,case,ground_truth,prompt,seed)
    except Exception as exc:
        return {'id':case['id'],'correct':False,'call':None,'input_tokens':0,'output_tokens':0,'raw':{},
                'error':type(exc).__name__+': '+str(exc)}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('source_report'); parser.add_argument('--output',required=True)
    args=parser.parse_args(); source=ROOT/args.source_report; target=ROOT/args.output
    source_raw=source.read_bytes(); experiment=json.loads(source_raw.decode('utf-8'))
    trajectory=experiment['result']['trajectories']['reflection_gp']; winner=trajectory['winner']
    if winner!=experiment['reflection_ranking'][0]: raise ValueError('winner is not the frozen reflection selection')
    all_cases=read_jsonl(DATA); case_map={item['id']:item for item in all_cases}
    cases=[case_map[case_id] for case_id in experiment['signature']['sealed_confirmation_ids']]
    answers={item['id']:item['ground_truth'] for item in read_jsonl(ANSWERS)}
    variants={'baseline':DEFAULT_PROMPT,'reflection_gp':experiment['prompts'][winner]}
    signature={'source_report_sha256':hashlib.sha256(source_raw).hexdigest(),'winner':winner,
               'ids':[case['id'] for case in cases],'model':experiment['signature']['task_model'],'seed':experiment['signature']['seed'],
               'protocol':'single frozen confirmation; no reselection; BFCL-derived score, not official BFCL'}
    if target.exists():
        report=json.loads(target.read_text(encoding='utf-8'))
        if report['signature']!=signature: raise ValueError('source or frozen selection changed')
    else: report={'signature':signature,'variants':variants,'rows':{}}
    provider=OllamaProvider(timeout=300) if experiment['signature'].get('task_transport','').startswith('ollama-native') else OpenAICompatibleProvider('http://127.0.0.1:11434/v1','local-ollama',300)
    for name,prompt in variants.items():
        rows=report['rows'].setdefault(name,{})
        for case in cases:
            if case['id'] not in rows:
                rows[case['id']]=evaluate_or_error(provider,experiment['signature']['task_model'],case,answers[case['id']],prompt,experiment['signature']['seed'])
                target.parent.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                print(name,len(rows),rows[case['id']]['correct'],flush=True)
    report['summary']={name:summarize(rows) for name,rows in report['rows'].items()}
    base=report['rows']['baseline']; child=report['rows']['reflection_gp']
    improved=sum(not base[key]['correct'] and child[key]['correct'] for key in base)
    regressed=sum(base[key]['correct'] and not child[key]['correct'] for key in base)
    report['paired']={'improved':improved,'regressed':regressed,'unchanged':len(base)-improved-regressed,
                      'two_sided_exact_sign_p':exact_sign_p(improved,regressed)}
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps({'summary':report['summary'],'paired':report['paired']},indent=2))


if __name__=='__main__': main()
