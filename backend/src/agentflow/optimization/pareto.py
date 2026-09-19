"""GEPA-inspired instance-wise archive and safe, system-aware merge primitives."""
from __future__ import annotations

import json

from agentflow.providers import ChatMessage
from .evolution import final_text
from .structural import TOPOLOGIES


def score_vector(evaluation, case_ids):
    by_id = {row['id']: float(row['correct']) for row in evaluation['rows']}
    if set(by_id) != set(case_ids):
        raise ValueError('evaluation rows do not match archive cases')
    return tuple(by_id[case_id] for case_id in case_ids)


def instance_pareto_front(evaluations, case_ids):
    """Keep candidates not strictly dominated across individual instances."""
    vectors = {key: score_vector(value, case_ids) for key, value in evaluations.items()}
    return pareto_front_from_vectors(vectors)


def component_score_vector(evaluation, case_ids):
    """Cartesian case×objective scores: format, route, and priority."""
    by_id = {row['id']:row for row in evaluation['rows']}
    if set(by_id) != set(case_ids):
        raise ValueError('evaluation rows do not match archive cases')
    result=[]
    for case_id in case_ids:
        row=by_id[case_id]
        try:
            value=json.loads(final_text(row['output']))
        except (ValueError,TypeError):
            value={}
        valid=float(isinstance(value,dict) and set(value)=={'route','priority'})
        result.extend((valid,float(value.get('route')==row['expected']['route']),
                       float(value.get('priority')==row['expected']['priority'])))
    return tuple(result)


def pareto_front_from_vectors(vectors):
    frontier = []
    for candidate, vector in vectors.items():
        dominated = any(
            other != candidate and all(a >= b for a, b in zip(other_vector, vector))
            and any(a > b for a, b in zip(other_vector, vector))
            for other, other_vector in vectors.items()
        )
        if not dominated:
            frontier.append(candidate)
    return sorted(frontier)


def hybrid_pareto_front(evaluations,case_ids):
    return pareto_front_from_vectors({key:component_score_vector(value,case_ids) for key,value in evaluations.items()})


def complementary_pairs(evaluations, case_ids, frontier=None, vector_mode='exact'):
    """Rank parent pairs by additional instance coverage, then lower overlap."""
    frontier = frontier or instance_pareto_front(evaluations, case_ids)
    vector_fn=score_vector if vector_mode=='exact' else component_score_vector if vector_mode=='hybrid' else None
    if vector_fn is None: raise ValueError('unknown vector mode')
    vectors = {key: vector_fn(evaluations[key], case_ids) for key in frontier}
    ranked = []
    for index, left in enumerate(frontier):
        for right in frontier[index+1:]:
            a, b = vectors[left], vectors[right]
            union = sum(max(x,y) for x,y in zip(a,b))
            gain = union-max(sum(a),sum(b))
            overlap = sum(x*y for x,y in zip(a,b))
            ranked.append({'left':left,'right':right,'complementary_gain':gain,
                           'union_coverage':union,'overlap':overlap})
    return sorted(ranked,key=lambda item:(-item['complementary_gain'],-item['union_coverage'],item['overlap'],item['left'],item['right']))


def disagreement_batch(left_eval, right_eval, cases, size=4):
    """Select deterministic training ASI: disagreements first, joint failures next."""
    left = {row['id']:row for row in left_eval['rows']}
    right = {row['id']:row for row in right_eval['rows']}
    if set(left) != set(right):
        raise ValueError('parents must share cases')
    order = sorted(left, key=lambda case_id:(
        0 if left[case_id]['correct'] != right[case_id]['correct'] else
        1 if not left[case_id]['correct'] else 2, case_id))
    by_id = {case['id']:case for case in cases}
    return [by_id[case_id] for case_id in order[:size]]


class SystemAwareMerger:
    """Merge complementary workflow genomes through a schema-constrained LM call."""
    def __init__(self, provider, model):
        self.provider, self.model = provider, model
        self.log = []

    def merge(self, left, right, left_eval, right_eval, training, policy, seed):
        batch = disagreement_batch(left_eval,right_eval,training,6)
        left_rows = {row['id']:row for row in left_eval['rows']}
        right_rows = {row['id']:row for row in right_eval['rows']}
        feedback=[]
        for case in batch:
            feedback.append({'ticket':case['text'],'expected':case['expected'],
                             'left':{'correct':left_rows[case['id']]['correct'],'output':final_text(left_rows[case['id']]['output'])},
                             'right':{'correct':right_rows[case['id']]['correct'],'output':final_text(right_rows[case['id']]['output'])}})
        request={'immutable_policy':policy,'left_genome':left,'right_genome':right,
                 'complementary_training_feedback':feedback,
                 'instruction':'Create ONE complete reusable child strategy that preserves the complementary strengths of both parents. The immutable policy always wins. Fix observed failure patterns without memorizing tickets. Choose one allowed topology: direct, decompose, or review. Return no examples in the prompt and do not generate code.'}
        schema={'type':'object','properties':{'topology':{'type':'string','enum':list(TOPOLOGIES)},
                 'prompt':{'type':'string'}},'required':['topology','prompt'],'additionalProperties':False}
        for attempt in range(3):
            response=self.provider.chat([ChatMessage('user',json.dumps(request,ensure_ascii=False))],
                model=self.model,temperature=.5,seed=seed+attempt,max_tokens=1800,
                response_format={'type':'json_schema','json_schema':{'name':'workflow_merge','schema':schema}})
            try:
                parsed=json.loads(final_text(response.content))
                if set(parsed)!= {'topology','prompt'} or parsed['topology'] not in TOPOLOGIES:
                    raise ValueError('invalid merge schema')
                if not isinstance(parsed['prompt'],str) or not 40 <= len(parsed['prompt']) <= 4000:
                    raise ValueError('invalid merged prompt')
                draft={'topology':parsed['topology'],'prompt':parsed['prompt'].strip()}
                audit_request={'immutable_policy':policy,'draft_genome':draft,
                    'instruction':'Audit the draft for every route, precedence, priority, negation, historical/resolved, injection, and exact-output rule. Return a corrected complete reusable genome. Do not include examples or code. The immutable policy wins.'}
                audit=self.provider.chat([ChatMessage('user',json.dumps(audit_request,ensure_ascii=False))],
                    model=self.model,temperature=0,seed=seed+100+attempt,max_tokens=1600,
                    response_format={'type':'json_schema','json_schema':{'name':'workflow_audit','schema':schema}})
                audited=json.loads(final_text(audit.content))
                if set(audited)!= {'topology','prompt'} or audited['topology'] not in TOPOLOGIES:
                    raise ValueError('invalid audit schema')
                if not isinstance(audited['prompt'],str) or not 40 <= len(audited['prompt']) <= 4000:
                    raise ValueError('invalid audited prompt')
                child={'topology':audited['topology'],'prompt':audited['prompt'].strip()}
                self.log.append({'parents':[left,right],'feedback_ids':[case['id'] for case in batch],
                                 'draft':draft,'child':child,'input_tokens':response.input_tokens+audit.input_tokens,
                                 'output_tokens':response.output_tokens+audit.output_tokens})
                return child
            except (ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
                self.log.append({'error':str(exc),'raw':response.content,
                                 'input_tokens':response.input_tokens,'output_tokens':response.output_tokens})
        raise ValueError('system-aware merge failed after retries')
