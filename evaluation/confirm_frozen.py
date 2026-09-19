"""Evaluate ALL frozen structural variants on fresh utterances; never select a winner."""
import hashlib
import copy
import json
import random
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'/'src'))
from agentflow.optimization.structural import StructuralEvaluator
from agentflow.optimization.evolution import RewardSpec
from agentflow.providers import OpenAICompatibleProvider
from analyze_evolution import wilson


def main():
    source=Path(sys.argv[1])
    target=source/'confirmation.json'
    if target.exists():
        raise ValueError('preserve prior confirmation evidence')
    original=(source/'report.json').read_bytes()
    experiment=json.loads(original.decode('utf-8'))
    if 'test_summary' not in experiment:
        raise ValueError('source run must be complete and frozen')
    variants=experiment['frozen_variants']
    data=json.loads((ROOT/'evaluation'/'triage_v1.json').read_text(encoding='utf-8'))
    confirmation_raw=(ROOT/'evaluation'/'triage_confirmation_v1.json').read_bytes()
    confirmation=json.loads(confirmation_raw.decode('utf-8'))
    seen={r[1] for s in ('train','validation','test') for r in data[s]}
    cases=[{'id':r[0],'text':r[1],'expected':{'route':r[2],'priority':r[3]}} for r in confirmation['cases']]
    assert all(c['text'] not in seen for c in cases)
    report={'source_report_sha256':hashlib.sha256(original).hexdigest(),
            'confirmation_sha256':hashlib.sha256(confirmation_raw).hexdigest(),
            'provenance':confirmation['provenance'], 'variants':variants,
            'deduplicated_identical_variants':True, 'rows':{name:[] for name in variants}}
    evaluator=StructuralEvaluator(OpenAICompatibleProvider('http://127.0.0.1:11434/v1','local-ollama',120),experiment['model'],data['policy'],RewardSpec())
    for i,case in enumerate(cases):
        names=list(variants)
        random.Random(experiment['seed']+i).shuffle(names)
        cache={}
        for name in names:
            identity=json.dumps(variants[name],sort_keys=True,ensure_ascii=False)
            if identity not in cache:
                cache[identity]=evaluator.evaluate(variants[name],[case],experiment['seed'])['rows'][0]
            report['rows'][name].append(copy.deepcopy(cache[identity]))
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 冻结版本的新样本确认','','全部版本原样评估，不据此选版或调参。模拟同域工单，不是外部独立 benchmark。','',
           '| 方法 | 正确数 | 成功率 | 95% Wilson | Token |','|---|---:|---:|---:|---:|']
    report['summary']={}
    for name,rows in report['rows'].items():
        k=sum(r['correct'] for r in rows); n=len(rows); lo,hi=wilson(k,n)
        tokens=sum(r['input_tokens']+r['output_tokens'] for r in rows)
        report['summary'][name]={'correct':k,'n':n,'success':k/n,'tokens':tokens}
        lines.append('| {} | {}/{} | {:.1%} | {:.1%}–{:.1%} | {} |'.format(name,k,n,k/n,lo,hi,tokens))
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (source/'confirmation.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(report['summary'],indent=2))


if __name__=='__main__':
    main()
