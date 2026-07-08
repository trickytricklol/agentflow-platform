"""Auditable local experiment: fixed vs feedback/random vs feedback/GP-EI."""
from __future__ import annotations
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'/'src'))
from agentflow.providers import ChatMessage, OpenAICompatibleProvider
from agentflow.optimization.evolution import RewardSpec, WorkflowEvaluator, FeedbackMutator, final_text, workflow_dsl, release_candidate
from agentflow.optimization.bayesian import GaussianProcessOptimizer, BayesianExperiment, BayesianObservation
from agentflow.optimization.embeddings import TfidfEmbedding

BASELINE = 'Apply the supplied business policy carefully. Return the requested JSON with the correct route and priority.'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=17)
    parser.add_argument('--rounds', type=int, default=2)
    parser.add_argument('--output', default='evaluation/results/evolution-v1')
    parser.add_argument('--embedding', choices=['tfidf','nomic'], default='tfidf')
    parser.add_argument('--failure-replay', action='store_true')
    parser.add_argument('--teacher-model', default='qwen3:1.7b')
    args = parser.parse_args()
    destination = ROOT/args.output
    destination.mkdir(parents=True, exist_ok=True)
    if (destination/'report.json').exists():
        raise ValueError('Choose a new output directory to preserve previous evidence')
    raw = (ROOT/'evaluation'/'triage_v1.json').read_bytes()
    dataset = json.loads(raw.decode('utf-8'))
    splits = {split: [{'id': r[0], 'text': r[1], 'expected': {'route': r[2], 'priority': r[3]}} for r in dataset[split]] for split in ('train','validation','test')}
    provider = OpenAICompatibleProvider('http://127.0.0.1:11434/v1', 'local-ollama', timeout=120)
    model = 'qwen3:1.7b'
    # Goal is translated into a restricted configuration, never executable code.
    goal = 'Improve exact business-policy-compliant JSON routing. Success weight 1, token penalty 0. Freeze this reward throughout the experiment.'
    response = provider.chat([ChatMessage('user', goal+' Return ONLY JSON with metric="exact_json", success_weight=1, token_penalty=0. /no_think')], model=model, temperature=0, max_tokens=300, response_format={'type':'json_object'})
    reward = RewardSpec.parse(json.loads(final_text(response.content)))
    evaluator = WorkflowEvaluator(provider, model, dataset['policy'], reward)
    report = {'seed': args.seed, 'dataset_sha256': hashlib.sha256(raw).hexdigest(), 'provenance': dataset['provenance'],
              'model': model, 'teacher_model':args.teacher_model, 'goal': goal, 'reward': reward.__dict__, 'embedding': args.embedding, 'failure_replay':args.failure_replay,
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'budget': {'rounds': args.rounds, 'candidates_per_round':3, 'evaluated_per_round':2},
              'goal_tokens': response.input_tokens+response.output_tokens, 'arms': {}}
    def save():
        (destination/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Reward frozen; warmup complete', flush=True)
    base_train = evaluator.evaluate(BASELINE, splits['train'], args.seed)
    base_val = evaluator.evaluate(BASELINE, splits['validation'], args.seed)
    report['baseline'] = {'prompt': BASELINE, 'train': base_train, 'validation': base_val}
    save()
    for strategy in ('random','gp_ei'):
        rng = random.Random(args.seed)
        mutator = FeedbackMutator(provider, args.teacher_model)
        observations = [(BASELINE, base_train)]
        curve = []
        report['arms'][strategy] = {'curve': curve, 'mutations': mutator.log}
        for iteration in range(args.rounds):
            parent, scores = max(observations, key=lambda item: item[1]['reward'])
            try:
                candidates = mutator.mutate(parent, splits['train'], scores, dataset['policy'], args.seed+iteration)
                if args.failure_replay:
                    from agentflow.optimization.evolution import feedback_examples
                    candidates = feedback_examples(candidates,splits['train'],scores)
            except Exception as exc:
                report['error'] = str(exc)
                save()
                raise
            known = {p for p, _ in observations}
            candidates = [p for p in candidates if p not in known]
            all_prompts = list(known)+candidates
            if args.embedding == 'nomic':
                from agentflow.optimization.embeddings import OllamaEmbeddingProvider
                embedding = OllamaEmbeddingProvider('nomic-embed-text')
            else:
                embedding = TfidfEmbedding(all_prompts)
            gp = GaussianProcessOptimizer(embedding)
            vectors = {p: embedding.embed(p) for p in all_prompts}
            for step in range(min(2, len(candidates))):
                history = BayesianExperiment([BayesianObservation(p, s['reward']) for p, s in observations])
                selected = rng.choice(candidates) if strategy=='random' else max(candidates, key=lambda p: gp._expected_improvement(vectors[p], history, vectors))
                candidates.remove(selected)
                result = evaluator.evaluate(selected, splits['train'], args.seed)
                observations.append((selected, result))
                curve.append({'iteration': iteration, 'prompt': selected, 'train': result, 'best_reward': max(s['reward'] for _, s in observations)})
                print(strategy, iteration, step, 'train', result['success'], flush=True)
                save()
        # Select using validation only; test is evaluated after both arms are frozen.
        shortlist = sorted(observations[1:], key=lambda x:x[1]['reward'], reverse=True)[:2]
        checked = [{'prompt':p, 'validation':evaluator.evaluate(p, splits['validation'], args.seed)} for p,_ in shortlist]
        winner = max([{'prompt':BASELINE, 'validation':base_val}]+checked, key=lambda x:x['validation']['reward'])
        report['arms'][strategy].update(validation_candidates=checked, selected=winner,
                                       release=release_candidate(workflow_dsl(BASELINE),winner['prompt'],base_val,winner['validation']))
        save()
    # No test examples or outcomes were visible to the optimizer above.
    variants = [('baseline',BASELINE)]+[(k,v['selected']['prompt']) for k,v in report['arms'].items()]
    tests = {k:[] for k,_ in variants}
    for case in splits['test']:
        shuffled = variants[:]
        random.Random(args.seed+len(tests['baseline'])).shuffle(shuffled)
        for name,prompt in shuffled:
            tests[name].extend(evaluator.evaluate(prompt,[case],args.seed)['rows'])
        report['test_rows'] = tests
        save()
    report['test_summary'] = {k:{'n':len(rows),'success':sum(r['correct'] for r in rows)/len(rows),
                               'valid_json':sum(r['valid_json'] for r in rows)/len(rows),
                               'tokens':sum(r.get('input_tokens',0)+r.get('output_tokens',0) for r in rows),
                               'mean_latency_ms':sum(r['latency_ms'] for r in rows)/len(rows)} for k,rows in tests.items()}
    save()
    print(json.dumps(report['test_summary'],indent=2),flush=True)


if __name__ == '__main__':
    main()
