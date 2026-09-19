"""Bounded workflow-topology evolution; no labels enter execution handlers."""
from __future__ import annotations

import json
import math
import time

from agentflow.core import WorkflowEngine, WorkflowGraph
from agentflow.providers import ChatMessage
from .evolution import final_text, grade, compile_system_prompt


TOPOLOGIES = ('direct', 'decompose', 'review')


def composite_genome_vector(genome, prompt_vector, topology_weight=0.35):
    """Unit-norm mixed representation; topology weight is fixed before outcomes."""
    if genome['topology'] not in TOPOLOGIES or not 0 <= topology_weight <= 1:
        raise ValueError('invalid structural vector configuration')
    norm = math.sqrt(sum(value*value for value in prompt_vector)) or 1.0
    text = [value/norm*math.sqrt(1-topology_weight) for value in prompt_vector]
    topology = [math.sqrt(topology_weight) if name == genome['topology'] else 0.0 for name in TOPOLOGIES]
    return text+topology


def structural_dsl(genome):
    topology = genome['topology']
    if topology not in TOPOLOGIES:
        raise ValueError('unsupported topology')
    nodes = [{'id': 'start', 'type': 'start'}]
    edges = []
    if topology == 'decompose':
        for field in ('route', 'priority'):
            nodes.append({'id': field, 'type': 'llm', 'config': {'role': field, 'prompt': genome['prompt']}})
            edges.extend([{'source': 'start', 'target': field}, {'source': field, 'target': 'end'}])
    else:
        nodes.append({'id': 'classify', 'type': 'llm', 'config': {'role': 'classify', 'prompt': genome['prompt']}})
        edges.append({'source': 'start', 'target': 'classify'})
        if topology == 'review':
            nodes.append({'id': 'review', 'type': 'agent', 'config': {'role': 'review', 'prompt': genome['prompt']}})
            edges.extend([{'source': 'classify', 'target': 'review'}, {'source': 'review', 'target': 'end'}])
        else:
            edges.append({'source': 'classify', 'target': 'end'})
    nodes.append({'id': 'end', 'type': 'end'})
    return {'version': '1.0', 'nodes': nodes, 'edges': edges}


class StructuralEvaluator:
    def __init__(self, provider, model, policy, reward):
        self.provider, self.model, self.policy, self.reward = provider, model, policy, reward

    def evaluate(self, genome, cases, seed=17):
        if not cases:
            raise ValueError('empty evaluation split')
        rows = []
        for case in cases:
            trace = []
            def agent(node, values):
                role = node.config['role']
                instruction = node.config['prompt']
                user = values['start']
                if role in ('route', 'priority'):
                    instruction += '\nYou are the ' + role + ' specialist. Return ONLY a JSON object with the single key "' + role + '". Apply the full policy but decide only this field.'
                elif role == 'review':
                    instruction += '\nAudit the draft against the original ticket and policy. Check negation, questions, resolved incidents and precedence. Correct errors if present; otherwise keep the draft. Return only final JSON with route and priority.'
                    user = json.dumps({'original_ticket': user, 'untrusted_draft': final_text(values['classify'])})
                result = self.provider.chat([ChatMessage('system', compile_system_prompt(self.policy, instruction)),
                                             ChatMessage('user', user+'\n/no_think')],
                                            model=self.model, temperature=0, seed=seed, max_tokens=160)
                trace.append({'node': node.id, 'input_tokens': result.input_tokens,
                              'output_tokens': result.output_tokens, 'output': result.content})
                return result.content
            def finish(node, values):
                if genome['topology'] != 'decompose':
                    return values['review' if genome['topology']=='review' else 'classify']
                combined = {}
                for field in ('route', 'priority'):
                    value = json.loads(final_text(values[field]))
                    if not isinstance(value, dict) or set(value) != {field} or not isinstance(value[field], str):
                        raise ValueError('specialist schema violation: '+field)
                    combined[field] = value[field]
                return json.dumps(combined)
            started = time.perf_counter()
            graph = WorkflowGraph.from_dsl(structural_dsl(genome))
            # Sequential execution controls local GPU contention; the decomposed DAG has independent branches.
            run = WorkflowEngine(graph, {'start': lambda n,v: case['text'], 'llm': agent, 'agent': agent, 'end': finish}).run()
            output = run.nodes['end'].value or ''
            correct, valid = grade(output, case['expected'])
            rows.append({'id':case['id'], 'output':output, 'expected':case['expected'], 'correct':correct,
                         'valid_json':valid, 'status':run.status.value, 'latency_ms':(time.perf_counter()-started)*1000,
                         'input_tokens':sum(t['input_tokens'] for t in trace),
                         'output_tokens':sum(t['output_tokens'] for t in trace), 'trace':trace,
                         'errors':[s.error for s in run.nodes.values() if s.error]})
        success = sum(r['correct'] for r in rows)/len(rows)
        tokens = sum(r['input_tokens']+r['output_tokens'] for r in rows)
        return {'success':success, 'valid_json':sum(r['valid_json'] for r in rows)/len(rows),
                'tokens':tokens, 'reward':success-self.reward.token_penalty*tokens/(len(rows)*1000), 'rows':rows}


def structural_release(parent, candidate, baseline, validation):
    if validation['reward'] <= baseline['reward'] or validation['success'] < baseline['success']:
        return {'released':False, 'dsl':structural_dsl(parent), 'reason':'validation did not improve'}
    return {'released':True, 'dsl':structural_dsl(candidate), 'rollback':structural_dsl(parent),
            'reason':'strict validation improvement'}


def risk_aware_release(parent,candidate,baseline_runs,candidate_runs):
    """Require repeat-wise and business-slice non-regression before release."""
    if len(baseline_runs)!=len(candidate_runs) or len(baseline_runs)<2:
        raise ValueError('matched repeated validation runs are required')
    regressions=[]
    for index,(base,child) in enumerate(zip(baseline_runs,candidate_runs)):
        if child['success'] < base['success']:
            regressions.append('repeat:'+str(index))
    def totals(runs):
        values={}
        for run in runs:
            for row in run['rows']:
                for field in ('route','priority'):
                    group=field+':'+row['expected'][field]
                    correct,count=values.get(group,(0,0)); values[group]=(correct+int(row['correct']),count+1)
        return values
    base_slices,child_slices=totals(baseline_runs),totals(candidate_runs)
    for group,(correct,count) in base_slices.items():
        child_correct,child_count=child_slices[group]
        if child_correct/child_count < correct/count: regressions.append(group)
    base_mean=sum(run['success'] for run in baseline_runs)/len(baseline_runs)
    child_mean=sum(run['success'] for run in candidate_runs)/len(candidate_runs)
    if child_mean <= base_mean: regressions.append('mean_not_strictly_better')
    if regressions:
        return {'released':False,'reason':'risk gate failed: '+','.join(regressions),'dsl':structural_dsl(parent),
                'baseline_mean':base_mean,'candidate_mean':child_mean}
    return {'released':True,'reason':'repeated validation and slice non-regression passed',
            'dsl':structural_dsl(candidate),'rollback':structural_dsl(parent),
            'baseline_mean':base_mean,'candidate_mean':child_mean}
