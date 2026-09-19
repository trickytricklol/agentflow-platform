"""GEPA-inspired bounded merge experiment over an already audited candidate archive."""
from __future__ import annotations
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'/'src'))
from agentflow.optimization.evolution import RewardSpec
from agentflow.optimization.pareto import instance_pareto_front, hybrid_pareto_front, complementary_pairs, disagreement_batch, SystemAwareMerger
from agentflow.optimization.structural import StructuralEvaluator, structural_release
from agentflow.providers import OpenAICompatibleProvider


def genome_key(genome):
    return json.dumps(genome,sort_keys=True,ensure_ascii=False)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('acquisition')
    parser.add_argument('--output',required=True)
    parser.add_argument('--teacher-model',default='qwen3:4b')
    parser.add_argument('--merges',type=int,default=3)
    parser.add_argument('--minibatch',type=int,default=4)
    parser.add_argument('--frontier',choices=['exact','hybrid'],default='hybrid')
    args=parser.parse_args()
    source=ROOT/args.acquisition; target=ROOT/args.output
    target.mkdir(parents=True,exist_ok=True)
    report_path=target/'report.json'
    if report_path.exists(): raise ValueError('use a fresh output directory')
    raw=source.read_bytes(); archive=json.loads(raw.decode('utf-8'))
    source_run=json.loads((ROOT/archive['source_directory']/'report.json').read_text(encoding='utf-8'))
    data=json.loads((ROOT/'evaluation'/'triage_v1.json').read_text(encoding='utf-8'))
    splits={name:[{'id':r[0],'text':r[1],'expected':{'route':r[2],'priority':r[3]}} for r in data[name]] for name in ('train','validation','test')}
    provider=OpenAICompatibleProvider('http://127.0.0.1:11434/v1','local-ollama',120)
    evaluator=StructuralEvaluator(provider,source_run['model'],data['policy'],RewardSpec())
    evaluations={key:item['result'] for key,item in archive['evaluations'].items()}
    genomes={key:item['genome'] for key,item in archive['evaluations'].items()}
    case_ids=tuple(case['id'] for case in splits['train'])
    frontier=hybrid_pareto_front(evaluations,case_ids) if args.frontier=='hybrid' else instance_pareto_front(evaluations,case_ids)
    pairs=complementary_pairs(evaluations,case_ids,frontier,args.frontier)
    merger=SystemAwareMerger(provider,args.teacher_model)
    baseline=source_run['baseline']['genome']; baseline_key=genome_key(baseline)
    report={'source_sha256':hashlib.sha256(raw).hexdigest(),'source_path':args.acquisition,
            'seed':source_run['seed'],'task_model':source_run['model'],'teacher_model':args.teacher_model,
            'protocol':args.frontier+' case-objective Pareto parents; disagreement ASI; minibatch gate; full train then validation release',
            'frontier':frontier,'pair_ranking':pairs,'attempts':[],'merge_log':merger.log,
            'baseline':{'genome':baseline,'train':evaluations[baseline_key],
                        'validation':source_run['baseline']['validation']}}
    def save(): report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    save(); children=[]; seen={genome_key(g) for g in genomes.values()}
    for index,pair in enumerate(pairs[:args.merges]):
        left,right=pair['left'],pair['right']
        child=merger.merge(genomes[left],genomes[right],evaluations[left],evaluations[right],splits['train'],data['policy'],source_run['seed']+index)
        identity=genome_key(child)
        batch=disagreement_batch(evaluations[left],evaluations[right],splits['train'],args.minibatch)
        child_mini=evaluator.evaluate(child,batch,source_run['seed'])
        batch_ids={case['id'] for case in batch}
        parent_score=max(sum(row['correct'] for row in evaluations[parent]['rows'] if row['id'] in batch_ids)/len(batch) for parent in (left,right))
        accepted=identity not in seen and child_mini['success'] >= parent_score
        attempt={'pair':pair,'child':child,'minibatch_ids':sorted(batch_ids),'parent_best_minibatch':parent_score,
                 'child_minibatch':child_mini,'accepted':accepted}
        if accepted:
            seen.add(identity); full=evaluator.evaluate(child,splits['train'],source_run['seed'])
            attempt['train']=full; children.append((child,full))
        report['attempts'].append(attempt); save()
        print('merge',index,'mini',child_mini['success'],'gate',accepted,flush=True)
    shortlist=sorted(children,key=lambda item:(item[1]['reward'],-item[1]['tokens']),reverse=True)[:2]
    checked=[{'genome':g,'validation':evaluator.evaluate(g,splits['validation'],source_run['seed'])} for g,_ in shortlist]
    winner=max([{'genome':baseline,'validation':report['baseline']['validation']}]+checked,
               key=lambda item:(item['validation']['reward'],-item['validation']['tokens']))
    release=structural_release(baseline,winner['genome'],report['baseline']['validation'],winner['validation'])
    deployed=winner['genome'] if release['released'] else baseline
    proposal=winner['genome'] if winner['genome']!=baseline else (shortlist[0][0] if shortlist else baseline)
    report.update(validation_candidates=checked,winner=winner,release=release,
                  frozen_variants={'baseline':baseline,'best_merge_proposal':proposal,'released':deployed},test_rows={})
    save()
    for name,genome in report['frozen_variants'].items(): report['test_rows'][name]=[]
    for index,case in enumerate(splits['test']):
        names=list(report['frozen_variants']); random.Random(source_run['seed']+index).shuffle(names)
        cache={}
        for name in names:
            identity=genome_key(report['frozen_variants'][name])
            if identity not in cache: cache[identity]=evaluator.evaluate(report['frozen_variants'][name],[case],source_run['seed'])['rows'][0]
            report['test_rows'][name].append(cache[identity].copy())
        save()
    report['test_summary']={name:{'success':sum(row['correct'] for row in rows)/len(rows),'n':len(rows),
        'tokens':sum(row['input_tokens']+row['output_tokens'] for row in rows)} for name,rows in report['test_rows'].items()}
    save(); print(json.dumps(report['test_summary'],indent=2))


if __name__=='__main__': main()
