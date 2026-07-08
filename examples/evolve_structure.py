"""Topology+instruction search: equal candidate budgets, shared mutation pool."""
from __future__ import annotations
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'/'src'))
from agentflow.optimization.structural import StructuralEvaluator, structural_release
from agentflow.optimization.evolution import RewardSpec, FeedbackMutator, feedback_examples
from agentflow.optimization.embeddings import OllamaEmbeddingProvider
from agentflow.optimization.bayesian import GaussianProcessOptimizer, BayesianExperiment, BayesianObservation
from agentflow.providers import OpenAICompatibleProvider

BASE = 'Apply the supplied business policy carefully. Return the requested JSON with the correct route and priority.'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=17)
    parser.add_argument('--teacher-model', default='qwen3:1.7b')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    folder = ROOT/args.output
    folder.mkdir(parents=True, exist_ok=True)
    if (folder/'report.json').exists():
        raise ValueError('use a fresh output folder')
    raw = (ROOT/'evaluation'/'triage_v1.json').read_bytes()
    data = json.loads(raw.decode('utf-8'))
    splits = {s:[{'id':r[0], 'text':r[1], 'expected':{'route':r[2], 'priority':r[3]}} for r in data[s]] for s in ('train','validation','test')}
    provider = OpenAICompatibleProvider('http://127.0.0.1:11434/v1', 'local-ollama',120)
    evaluator = StructuralEvaluator(provider,'qwen3:1.7b',data['policy'],RewardSpec())
    baseline = {'topology':'direct', 'prompt':BASE}
    report = {'seed':args.seed, 'model':'qwen3:1.7b', 'teacher_model':args.teacher_model,
              'dataset_sha256':hashlib.sha256(raw).hexdigest(), 'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'protocol':'shared pool, four new candidates per search arm, top two validation, test after freeze',
              'baseline':{'genome':baseline}, 'arms':{}}
    def save():
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for split in ('train','validation'):
        report['baseline'][split] = evaluator.evaluate(baseline,splits[split],args.seed)
    save()
    # Feedback is derived exclusively from training rollouts. The pool is shared for a fair acquisition ablation.
    mutator = FeedbackMutator(provider,args.teacher_model)
    report['mutations'] = mutator.log
    try:
        prompts = mutator.mutate(BASE,splits['train'],report['baseline']['train'],data['policy'],args.seed)
    except Exception as exc:
        report['error'] = str(exc)
        save()
        raise
    prompts = feedback_examples(prompts,splits['train'],report['baseline']['train'])
    pool = [{'topology':topology, 'prompt':prompt} for topology in ('direct','decompose','review') for prompt in [BASE]+prompts]
    pool = [g for g in pool if g != baseline]
    encode = lambda g: json.dumps(g,sort_keys=True)
    by_key = {encode(g):g for g in [baseline]+pool}
    embedding = OllamaEmbeddingProvider('nomic-embed-text')
    vectors = {k:embedding.embed(k) for k in by_key}
    optimizer = GaussianProcessOptimizer(embedding)
    report['pool'] = pool
    save()
    for strategy in ('random','gp_ei'):
        rng = random.Random(args.seed)
        observations = [(baseline,report['baseline']['train'])]
        candidates = pool[:]
        record = {'curve':[]}
        report['arms'][strategy] = record
        for step in range(4):
            history = BayesianExperiment([BayesianObservation(encode(g),r['reward']) for g,r in observations])
            chosen = rng.choice(candidates) if strategy=='random' else max(candidates,key=lambda g:optimizer._expected_improvement(vectors[encode(g)],history,vectors))
            candidates.remove(chosen)
            result = evaluator.evaluate(chosen,splits['train'],args.seed)
            observations.append((chosen,result))
            record['curve'].append({'genome':chosen, 'train':result})
            print(strategy,step,chosen['topology'],result['success'],flush=True)
            save()
        shortlist = sorted(observations[1:],key=lambda pair:(pair[1]['reward'],-pair[1]['tokens']),reverse=True)[:2]
        checked = [{'genome':g,'validation':evaluator.evaluate(g,splits['validation'],args.seed)} for g,r in shortlist]
        winner = max([{'genome':baseline,'validation':report['baseline']['validation']}]+checked,key=lambda item:(item['validation']['reward'],-item['validation']['tokens']))
        record.update(validation_candidates=checked,selected=winner,release=structural_release(baseline,winner['genome'],report['baseline']['validation'],winner['validation']))
        # Never deploy a candidate that failed the gate, including tied cheaper candidates.
        if not record['release']['released']:
            record['selected'] = {'genome':baseline,'validation':report['baseline']['validation']}
        save()
    # Fixed few-shot is a predeclared strong baseline with training examples only.
    train = splits['train'][:]
    random.Random(args.seed).shuffle(train)
    examples = [{'ticket':c['text'],'answer':c['expected']} for c in train[:4]]
    fixed = {'topology':'direct','prompt':BASE+'\nReference training cases:\n'+json.dumps(examples)}
    variants = {'baseline':baseline,'static_fewshot':fixed}
    variants.update({arm:record['selected']['genome'] for arm,record in report['arms'].items()})
    report['frozen_variants'] = variants
    report['test_rows'] = {name:[] for name in variants}
    save()
    for i,case in enumerate(splits['test']):
        names = list(variants)
        random.Random(args.seed+i).shuffle(names)
        for name in names:
            report['test_rows'][name].extend(evaluator.evaluate(variants[name],[case],args.seed)['rows'])
        save()
    report['test_summary'] = {name:{'success':sum(r['correct'] for r in rows)/len(rows),
                                          'tokens':sum(r['input_tokens']+r['output_tokens'] for r in rows),
                                          'n':len(rows)} for name,rows in report['test_rows'].items()}
    save()
    print(json.dumps(report['test_summary'],indent=2),flush=True)


if __name__=='__main__':
    main()
