"""Automatic prompt mutation plus budgeted GP selection on BFCL-derived calls.

Development uses IDs 0-19, validation 20-59, and IDs 60-119 stay untouched for
a later frozen confirmation. This is not an official BFCL leaderboard score.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import math
import random
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'/'src'))
from agentflow.benchmarks import evaluate_bfcl_case
from agentflow.optimization import BayesianExperiment,GaussianProcessOptimizer,OllamaEmbeddingProvider
from agentflow.optimization.bayesian import BayesianObservation
from agentflow.providers import ChatMessage,OpenAICompatibleProvider
from bfcl_native_eval import DATA,ANSWERS,DEFAULT_PROMPT,read_jsonl


def prompt_id(prompt: str) -> str:
    return hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:12]


def summary(rows: dict) -> dict:
    values=list(rows.values())
    return {'correct':sum(row['correct'] for row in values),'n':len(values),
            'accuracy':sum(row['correct'] for row in values)/len(values),
            'tokens':sum(row['input_tokens']+row['output_tokens'] for row in values)}


def parse_candidates(content: str) -> list[str]:
    decoder=json.JSONDecoder()
    for index,char in enumerate(content):
        if char!='[': continue
        try: value,_=decoder.raw_decode(content[index:])
        except json.JSONDecodeError: continue
        if isinstance(value,list) and len(value)>=4 and all(isinstance(item,str) and item.strip() for item in value):
            return value[:8]
    raise ValueError('mutation model did not return at least four prompt strings')


def generate_candidates(provider,failures,seed):
    request=("You optimize a system instruction for native function calling. Generate exactly 8 diverse, general instructions. "
             "They must improve argument grounding and schema-faithful representation without mentioning or memorizing case IDs. "
             "Return only a JSON array of strings. Baseline: "+DEFAULT_PROMPT+"\nDevelopment failures:\n"+
             json.dumps(failures,ensure_ascii=False))
    response=provider.chat([ChatMessage('user',request)],model='qwen3:4b',temperature=.7,seed=seed,max_tokens=1800,think=False)
    candidates=parse_candidates(response.content)
    fallbacks=[
        DEFAULT_PROMPT+' Preserve mathematical expressions in the exact syntax implied by the schema examples; use ** for exponentiation.',
        DEFAULT_PROMPT+' Before calling, verify every required argument, type, enum, list shape, date, percentage, and expression syntax.',
        DEFAULT_PROMPT+' Copy literal user values faithfully, normalize only when the schema explicitly requires it, and never invent optional values.',
        DEFAULT_PROMPT+' Internally extract constraints, then emit exactly one native function call with no prose.',
    ]
    for item in fallbacks:
        if len(candidates)>=8: break
        if item not in candidates: candidates.append(item)
    if len(set(candidates))!=8: raise ValueError('mutation model returned duplicate prompts')
    return candidates,response.raw


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',required=True); parser.add_argument('--seed',type=int,default=17); parser.add_argument('--budget',type=int,default=4)
    args=parser.parse_args(); target=ROOT/args.output
    cases=read_jsonl(DATA); answers={item['id']:item['ground_truth'] for item in read_jsonl(ANSWERS)}
    split_cases={'development':cases[:20],'validation':cases[20:60]}
    signature={'data_sha256':hashlib.sha256(DATA.read_bytes()).hexdigest(),'answers_sha256':hashlib.sha256(ANSWERS.read_bytes()).hexdigest(),
               'development_ids':[item['id'] for item in split_cases['development']],
               'validation_ids':[item['id'] for item in split_cases['validation']],
               'sealed_confirmation_ids':[item['id'] for item in cases[60:120]],
               'task_model':'qwen3:1.7b','mutation_model':'qwen3:4b','seed':args.seed,'budget':args.budget,
               'protocol':'BFCL-derived native tool-call score; full candidate table for audit; confirmation sealed; not official BFCL'}
    provider=OpenAICompatibleProvider('http://127.0.0.1:11434/v1','local-ollama',120)
    if target.exists():
        report=json.loads(target.read_text(encoding='utf-8'))
        if report['signature']!=signature: raise ValueError('refusing to mix configurations')
    else:
        report={'signature':signature,'prompts':{},'evaluations':{}}
    baseline_id=prompt_id(DEFAULT_PROMPT); report['prompts'][baseline_id]=DEFAULT_PROMPT
    baseline=report['evaluations'].setdefault(baseline_id,{})
    development=baseline.setdefault('development',{})
    for case in split_cases['development']:
        if case['id'] not in development:
            development[case['id']]=evaluate_bfcl_case(provider,'qwen3:1.7b',case,answers[case['id']],DEFAULT_PROMPT,args.seed)
            target.parent.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if 'mutation_raw' not in report:
        failures=[{'question':case['question'][0][-1]['content'],'predicted':development[case['id']]['call'],'acceptable':answers[case['id']]}
                  for case in split_cases['development'] if not development[case['id']]['correct']]
        candidates,raw=generate_candidates(provider,failures,args.seed)
        report['mutation_raw']=raw
        for prompt in candidates: report['prompts'][prompt_id(prompt)]=prompt
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for pid,prompt in report['prompts'].items():
        evaluation=report['evaluations'].setdefault(pid,{})
        for split,items in split_cases.items():
            rows=evaluation.setdefault(split,{})
            for case in items:
                if case['id'] not in rows:
                    rows[case['id']]=evaluate_bfcl_case(provider,'qwen3:1.7b',case,answers[case['id']],prompt,args.seed)
                    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                    print(pid,split,len(rows),rows[case['id']]['correct'],flush=True)
            evaluation[split+'_summary']=summary(rows)
    candidate_ids=[pid for pid in report['prompts'] if pid!=baseline_id]
    failures=[{'question':case['question'][0][-1]['content'],'predicted':development[case['id']]['call'],'acceptable':answers[case['id']]}
              for case in split_cases['development'] if not development[case['id']]['correct']]
    scores={pid:report['evaluations'][pid]['development_summary']['accuracy'] for pid in report['prompts']}
    embedder=OllamaEmbeddingProvider('nomic-embed-text'); gp=GaussianProcessOptimizer(embedder)
    vectors={pid:embedder.embed(prompt) for pid,prompt in report['prompts'].items()}
    feedback_vector=embedder.embed('Function-call failure feedback: '+json.dumps(failures,ensure_ascii=False,sort_keys=True))
    def similarity(pid):
        vector=vectors[pid]
        return sum(left*right for left,right in zip(vector,feedback_vector))/(math.sqrt(sum(value*value for value in vector))*math.sqrt(sum(value*value for value in feedback_vector)))
    report['reflection_ranking']=sorted(candidate_ids,key=lambda pid:(similarity(pid),pid),reverse=True)
    report['reflection_similarity']={pid:similarity(pid) for pid in candidate_ids}
    def trajectory(method):
        observed=[baseline_id]; remaining=candidate_ids[:]; steps=[]
        for step in range(args.budget):
            if method=='random': selected=random.Random(args.seed+step).choice(remaining)
            elif method=='reflection_gp' and step==0: selected=report['reflection_ranking'][0]
            else:
                history=BayesianExperiment([BayesianObservation(pid,scores[pid]) for pid in observed])
                selected=max(remaining,key=lambda pid:(gp._expected_improvement(vectors[pid],history,vectors),pid))
            remaining.remove(selected); observed.append(selected); steps.append(selected)
        winner=max(observed,key=lambda pid:(scores[pid],pid))
        return {'steps':steps,'best_development':scores[winner],'winner':winner,
                'validation':report['evaluations'][winner]['validation_summary']}
    subsets=list(itertools.combinations(candidate_ids,args.budget)); oracle=max(scores.values())
    bests=[max(scores[pid] for pid in (baseline_id,)+subset) for subset in subsets]
    report['result']={'baseline':{'development':report['evaluations'][baseline_id]['development_summary'],'validation':report['evaluations'][baseline_id]['validation_summary']},
                      'oracle_development':oracle,'random_exact':{'subsets':len(subsets),'mean_best':sum(bests)/len(bests),'probability_find_oracle':sum(value==oracle for value in bests)/len(bests)},
                      'trajectories':{'random_seeded':trajectory('random'),'gp_text':trajectory('gp'),'reflection_gp':trajectory('reflection_gp')},
                      'confirmation_status':'SEALED_NOT_RUN'}
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(report['result'],indent=2))


if __name__=='__main__': main()
