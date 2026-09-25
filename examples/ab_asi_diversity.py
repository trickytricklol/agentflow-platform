"""Head-to-head A/B: legacy feedback/EI vs ASI feedback + diversity-aware acquisition.

Same dataset split, seed, executor model and teacher model for both arms, so the only
differences are (1) whether the reflective mutator receives per-component faults
(GEPA ASI) and (2) whether acquisition scalarizes EI with embedding novelty.

Run after `ollama pull qwen3:1.7b` (and optionally `nomic-embed-text`):
    python examples/ab_asi_diversity.py --output evaluation/results/ab-asi-div-seed17
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend' / 'src'))

from agentflow.providers import ChatMessage, OpenAICompatibleProvider
from agentflow.optimization.evolution import (
    RewardSpec, WorkflowEvaluator, FeedbackMutator, final_text, release_candidate, workflow_dsl)
from agentflow.optimization.bayesian import GaussianProcessOptimizer, BayesianExperiment, BayesianObservation
from agentflow.optimization.embeddings import TfidfEmbedding, OllamaEmbeddingProvider

BASELINE = 'Apply the supplied business policy carefully. Return the requested JSON with the correct route and priority.'


def run_arm(name, *, asi, diversity_weight, provider, model, teacher, policy, reward, splits, seed):
    evaluator = WorkflowEvaluator(provider, model, policy, reward, max_tokens=1024)
    base_train = evaluator.evaluate(BASELINE, splits['train'], seed)
    base_val = evaluator.evaluate(BASELINE, splits['validation'], seed)
    mutator = FeedbackMutator(provider, teacher, asi=asi)
    observations = [(BASELINE, base_train)]
    candidates = mutator.mutate(BASELINE, splits['train'], base_train, policy, seed)
    known = {BASELINE}
    candidates = [c for c in candidates if c not in known][:2]
    embedding = TfidfEmbedding([BASELINE] + candidates)
    gp = GaussianProcessOptimizer(embedding, diversity_weight=diversity_weight)
    vectors = {p: embedding.embed(p) for p in [BASELINE] + candidates}
    curve = []
    for prompt in candidates:
        history = BayesianExperiment([BayesianObservation(p, s['reward']) for p, s in observations])
        result = evaluator.evaluate(prompt, splits['train'], seed)
        observations.append((prompt, result))
        curve.append({'prompt': prompt, 'train_success': result['success']})
        print(f'  [{name}] candidate train={result["success"]:.3f}', flush=True)
    shortlist = sorted(observations[1:], key=lambda x: x[1]['reward'], reverse=True)[:1]
    checked = [{'prompt': p, 'validation': evaluator.evaluate(p, splits['validation'], seed)} for p, _ in shortlist]
    winner = max([{'prompt': BASELINE, 'validation': base_val}] + checked, key=lambda x: x['validation']['reward'])
    release = release_candidate(workflow_dsl(BASELINE), winner['prompt'], base_val, winner['validation'])
    return {'name': name, 'asi': asi, 'diversity_weight': diversity_weight,
            'baseline_train_success': base_train['success'], 'baseline_val_success': base_val['success'],
            'curve': curve, 'selected': winner['prompt'],
            'selected_val_success': winner['validation']['success'], 'released': release['released'],
            'mutations': mutator.log}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=17)
    ap.add_argument('--model', default='qwen3:1.7b')
    ap.add_argument('--teacher-model', default='qwen3:1.7b')
    ap.add_argument('--output', default='evaluation/results/ab-asi-div-seed17')
    args = ap.parse_args()
    destination = ROOT / args.output
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / 'report.json').exists():
        raise ValueError('choose a fresh output dir to preserve prior evidence')

    raw = (ROOT / 'evaluation' / 'triage_v1.json').read_bytes()
    dataset = json.loads(raw.decode('utf-8'))
    splits = {s: [{'id': r[0], 'text': r[1], 'expected': {'route': r[2], 'priority': r[3]}} for r in dataset[s]]
              for s in ('train', 'validation', 'test')}

    provider = OpenAICompatibleProvider('http://127.0.0.1:11434/v1', 'local-ollama', timeout=180)
    # The reward is a frozen whitelist; construct it directly instead of asking the LLM.
    reward = RewardSpec(metric='exact_json', success_weight=1.0, token_penalty=0.0)

    report = {'seed': args.seed, 'model': args.model, 'teacher_model': args.teacher_model,
              'dataset_sha256': hashlib.sha256(raw).hexdigest(), 'reward': reward.__dict__, 'arms': {}}

    print('Arm A: legacy feedback, classic EI', flush=True)
    report['arms']['legacy_ei'] = run_arm('legacy_ei', asi=False, diversity_weight=0.0,
                                          provider=provider, model=args.model, teacher=args.teacher_model,
                                          policy=dataset['policy'], reward=reward, splits=splits, seed=args.seed)
    print('Arm B: ASI feedback + diversity acquisition', flush=True)
    report['arms']['asi_diverse'] = run_arm('asi_diverse', asi=True, diversity_weight=0.3,
                                            provider=provider, model=args.model, teacher=args.teacher_model,
                                            policy=dataset['policy'], reward=reward, splits=splits, seed=args.seed)

    # Held-out test, evaluated once after both arms are frozen.
    evaluator = WorkflowEvaluator(provider, args.model, dataset['policy'], reward, max_tokens=1024)
    variants = [('baseline', BASELINE)] + [(k, v['selected']) for k, v in report['arms'].items()]
    test_rows = {k: [] for k, _ in variants}
    for case in splits['test']:
        for name, prompt in variants:
            test_rows[name].extend(evaluator.evaluate(prompt, [case], args.seed)['rows'])
    report['test_summary'] = {k: {'n': len(rows),
                                  'success': sum(r['correct'] for r in rows) / len(rows),
                                  'valid_json': sum(r['valid_json'] for r in rows) / len(rows)}
                              for k, rows in test_rows.items()}
    (destination / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report['test_summary'], indent=2), flush=True)


if __name__ == '__main__':
    main()
