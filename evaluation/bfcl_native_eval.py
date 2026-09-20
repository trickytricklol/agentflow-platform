"""Resumable BFCL-derived native tool-call evaluation (not an official score)."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'/'src'))
from agentflow.benchmarks import evaluate_bfcl_case
from agentflow.providers import OpenAICompatibleProvider

DATA=ROOT/'evaluation/external/BFCL/berkeley-function-call-leaderboard/bfcl_eval/data/BFCL_v4_simple_python.json'
ANSWERS=ROOT/'evaluation/external/BFCL/berkeley-function-call-leaderboard/bfcl_eval/data/possible_answer/BFCL_v4_simple_python.json'
DEFAULT_PROMPT='Use the supplied function to satisfy the user. Ground every argument in the request and function schema; omit optional arguments unless explicitly requested.'


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--limit',type=int,default=20)
    parser.add_argument('--offset',type=int,default=0)
    parser.add_argument('--model',default='qwen3:1.7b')
    parser.add_argument('--seed',type=int,default=17)
    parser.add_argument('--prompt',default=DEFAULT_PROMPT)
    args=parser.parse_args()
    cases=read_jsonl(DATA)[args.offset:args.offset+args.limit]
    answer_map={item['id']:item['ground_truth'] for item in read_jsonl(ANSWERS)}
    target=ROOT/args.output
    signature={"data_sha256":hashlib.sha256(DATA.read_bytes()).hexdigest(),"answers_sha256":hashlib.sha256(ANSWERS.read_bytes()).hexdigest(),
               "offset":args.offset,"limit":args.limit,"model":args.model,"seed":args.seed,"prompt":args.prompt,
               "protocol":"BFCL-derived simple_python native tool-call exact acceptable-value score; not official BFCL"}
    if target.exists():
        report=json.loads(target.read_text(encoding='utf-8'))
        if report['signature']!=signature: raise ValueError('refusing to mix configurations')
    else:
        report={"signature":signature,"rows":{}}
    provider=OpenAICompatibleProvider('http://127.0.0.1:11434/v1','local-ollama',120)
    for index,case in enumerate(cases,1):
        if case['id'] not in report['rows']:
            report['rows'][case['id']]=evaluate_bfcl_case(provider,args.model,case,answer_map[case['id']],args.prompt,args.seed)
            target.parent.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(index,case['id'],report['rows'][case['id']]['correct'],flush=True)
    rows=list(report['rows'].values())
    report['summary']={"correct":sum(row['correct'] for row in rows),"n":len(rows),
                       "accuracy":sum(row['correct'] for row in rows)/len(rows),
                       "tokens":sum(row['input_tokens']+row['output_tokens'] for row in rows)}
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report['summary'],indent=2))


if __name__=='__main__': main()
