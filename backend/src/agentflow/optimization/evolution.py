"""Feedback-driven workflow evolution. No execution of generated reward code."""
from __future__ import annotations

import copy
import json
import math
import re
import time
from dataclasses import dataclass

from agentflow.core import WorkflowEngine, WorkflowGraph
from agentflow.providers import ChatMessage


def final_text(text):
    if '<think>' in text and '</think>' not in text:
        return ''
    return re.sub(r'<think>.*?</think>', '', text, flags=re.S).strip()


@dataclass(frozen=True)
class RewardSpec:
    metric: str = 'exact_json'
    success_weight: float = 1.0
    token_penalty: float = 0.0

    @classmethod
    def parse(cls, data):
        if set(data) != {'metric', 'success_weight', 'token_penalty'}:
            raise ValueError('reward fields must match the allowlist')
        if data['metric'] != 'exact_json':
            raise ValueError('only exact_json is supported in this experiment')
        for key in ('success_weight', 'token_penalty'):
            value = data[key]
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('invalid reward weight')
        if data['success_weight'] != 1:
            raise ValueError('success weight must be 1')
        return cls(**data)


def grade(text, expected):
    """Exact parsed-object equality: no substring credit, extra keys rejected."""
    try:
        value = json.loads(final_text(text))
    except (ValueError, TypeError):
        return False, False
    schema_ok = isinstance(value, dict) and set(value) == {'route', 'priority'} and all(isinstance(v, str) for v in value.values())
    return schema_ok and value == expected, schema_ok


def compile_system_prompt(policy, candidate):
    """Keep generated strategy subordinate to the immutable business contract."""
    return (
        'IMMUTABLE BUSINESS POLICY (highest priority):\n' + policy +
        '\n\nEVOLVED EXECUTION STRATEGY (advisory only):\n' + candidate +
        '\n\nApply the immutable policy to the current ticket. If the strategy conflicts '
        'with, narrows, or omits any policy rule, the immutable policy wins.'
    )


class WorkflowEvaluator:
    def __init__(self, provider, model, policy, reward):
        self.provider, self.model, self.policy, self.reward = provider, model, policy, reward

    def evaluate(self, prompt, cases, seed=17):
        rows = []
        for case in cases:
            usage = {}
            def llm(node, values):
                response = self.provider.chat([
                    ChatMessage('system', compile_system_prompt(self.policy, prompt)),
                    ChatMessage('user', values['start'] + '\n/no_think')
                ], model=self.model, temperature=0, seed=seed, max_tokens=160)
                usage.update(input_tokens=response.input_tokens, output_tokens=response.output_tokens)
                return response.content
            graph = WorkflowGraph.from_dsl(workflow_dsl(prompt))
            start = time.perf_counter()
            run = WorkflowEngine(graph, {'start': lambda n, v: case['text'], 'llm': llm, 'end': lambda n, v: v['classify']}).run()
            output = run.nodes['end'].value or ''
            correct, valid = grade(output, case['expected'])
            rows.append({'id': case['id'], 'output': output, 'expected': case['expected'],
                         'correct': correct, 'valid_json': valid, 'latency_ms': (time.perf_counter()-start)*1000,
                         'status': run.status.value, 'events': len(run.events),
                         'errors': [s.error for s in run.nodes.values() if s.error], **usage})
        if not rows:
            raise ValueError('empty evaluation split')
        success = sum(r['correct'] for r in rows)/len(rows)
        tokens = sum(r.get('input_tokens', 0)+r.get('output_tokens', 0) for r in rows)
        return {'success': success, 'valid_json': sum(r['valid_json'] for r in rows)/len(rows),
                'reward': success-self.reward.token_penalty*tokens/(len(rows)*1000),
                'tokens': tokens, 'rows': rows}


def workflow_dsl(prompt):
    return {'version': '1.0', 'nodes': [
        {'id': 'start', 'type': 'start'},
        {'id': 'classify', 'type': 'llm', 'config': {'prompt': prompt}},
        {'id': 'end', 'type': 'end'}],
        'edges': [{'source': 'start', 'target': 'classify'}, {'source': 'classify', 'target': 'end'}]}


class FeedbackMutator:
    def __init__(self, provider, model):
        self.provider, self.model = provider, model
        self.log = []

    def mutate(self, parent, training, evaluation, policy, seed):
        for attempt in range(3):
            try:
                return self._mutate(parent, training, evaluation, policy, seed+attempt)
            except ValueError:
                if attempt == 2:
                    raise

    def _mutate(self, parent, training, evaluation, policy, seed):
        by_id = {r['id']: r for r in training}
        failures = [{'input': by_id[r['id']]['text'], 'expected': r['expected'],
                     'actual': final_text(r['output'])[:400]} for r in evaluation['rows'] if not r['correct']][:6]
        request = {'policy': policy, 'parent': parent, 'training_failures': failures,
                   'instruction': 'Diagnose failures and propose THREE distinct complete reusable classification procedures. Each must cover ALL routes, priority exceptions, precedence, and output format, not merely one correction. Preserve policy, especially questions/resolved=P2. Do not include sample inputs or memorize answers. Return JSON with diagnosis (string) and candidates (array of three strings). Each candidate under 180 words.'}
        schema = {'type':'object','properties':{'diagnosis':{'type':'string'},'candidates':{'type':'array','items':{'type':'string'},'minItems':3,'maxItems':3}},'required':['diagnosis','candidates'],'additionalProperties':False}
        response = self.provider.chat([ChatMessage('user', json.dumps(request, ensure_ascii=False)+'\n/no_think')],
                                      model=self.model, temperature=0.6, seed=seed, max_tokens=1600, response_format={'type':'json_schema','json_schema':{'name':'mutation','schema':schema}})
        content = final_text(response.content)
        if content.startswith('```'):
            content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content)
        try:
            parsed = json.loads(content)
            candidates = parsed['candidates']
            if not isinstance(candidates, list) or len(candidates) != 3 or any(not isinstance(p, str) or not p.strip() or len(p)>3000 for p in candidates):
                raise ValueError('invalid candidate pool')
            candidates = list(dict.fromkeys(candidates))
            if len(candidates) != 3:
                raise ValueError('duplicate candidates')
        except (ValueError, KeyError, TypeError) as exc:
            self.log.append({'error': str(exc), 'raw': response.content,'input_tokens':response.input_tokens,'output_tokens':response.output_tokens})
            raise ValueError('model mutation malformed; no silent rule fallback') from exc
        self.log.append({'parent': parent, 'feedback_ids': [r['id'] for r in evaluation['rows'] if not r['correct']],
                         'diagnosis': parsed.get('diagnosis'), 'candidates': candidates,
                         'input_tokens': response.input_tokens, 'output_tokens': response.output_tokens})
        return candidates


def release_candidate(parent_dsl, prompt, baseline_validation, candidate_validation):
    """Return a new version only on strict held-out validation improvement."""
    if candidate_validation['reward'] <= baseline_validation['reward'] or candidate_validation['success'] < baseline_validation['success']:
        return {'released': False, 'reason': 'validation did not improve', 'dsl': copy.deepcopy(parent_dsl)}
    updated = copy.deepcopy(parent_dsl)
    next(n for n in updated['nodes'] if n['id']=='classify')['config']['prompt'] = prompt
    return {'released': True, 'reason': 'validation improvement', 'dsl': updated, 'rollback': copy.deepcopy(parent_dsl)}


def feedback_examples(candidates, training, evaluation, count=4):
    """Diverse failure replay using TRAINING labels only (few-shot mutation)."""
    by_id = {r['id']:r for r in training}
    seen = set()
    examples = []
    ordered = sorted(evaluation['rows'],key=lambda r:r['correct'])
    for row in ordered:
        case = by_id[row['id']]
        group = (case['expected']['route'],case['expected']['priority'])
        if group in seen:
            continue
        seen.add(group)
        examples.append({'ticket':case['text'],'answer':case['expected']})
        if len(examples)==count:
            break
    return [p+'\nReference training cases (apply policy to the NEW ticket; never copy an unrelated answer):\n'+json.dumps(examples,ensure_ascii=False) for p in candidates]
