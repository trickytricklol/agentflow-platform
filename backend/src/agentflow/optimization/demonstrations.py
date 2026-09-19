"""Deterministic, training-only demonstration proposals for joint optimization."""
from __future__ import annotations
import json
import random


REFERENCE_MARKER='\nReference training cases'


def strip_reference_examples(prompt):
    return prompt.split(REFERENCE_MARKER,1)[0].strip()


def _greedy_diverse(cases,size,preferred_ids=()):
    by_id={case['id']:case for case in cases}; ordered=[]
    for case_id in preferred_ids:
        if case_id in by_id and case_id not in ordered: ordered.append(case_id)
    ordered += [case['id'] for case in sorted(cases,key=lambda item:item['id']) if case['id'] not in ordered]
    selected=[]; routes=set(); priorities=set()
    while ordered and len(selected)<size:
        best=max(ordered,key=lambda case_id:(
            int(by_id[case_id]['expected']['route'] not in routes)+int(by_id[case_id]['expected']['priority'] not in priorities),
            int(case_id in preferred_ids),-ordered.index(case_id)))
        ordered.remove(best); selected.append(best)
        routes.add(by_id[best]['expected']['route']); priorities.add(by_id[best]['expected']['priority'])
    return selected


def propose_demo_sets(training,baseline_evaluation,seed,size=4):
    ids=[case['id'] for case in training]
    rng=random.Random(seed); random_ids=ids[:]; rng.shuffle(random_ids)
    failures=[row['id'] for row in baseline_evaluation['rows'] if not row['correct']]
    proposals=[(),tuple(_greedy_diverse(training,size)),tuple(_greedy_diverse(training,size,failures)),tuple(random_ids[:size])]
    result=[]; seen=set()
    for proposal in proposals:
        if proposal not in seen:
            seen.add(proposal); result.append(proposal)
    return result


def compose_with_demos(instruction,training,demo_ids):
    if not demo_ids: return strip_reference_examples(instruction)
    by_id={case['id']:case for case in training}
    if any(case_id not in by_id for case_id in demo_ids): raise ValueError('demo id is not in training split')
    examples=[{'ticket':by_id[case_id]['text'],'answer':by_id[case_id]['expected']} for case_id in demo_ids]
    return strip_reference_examples(instruction)+REFERENCE_MARKER+' (apply policy to the NEW ticket; never copy an unrelated answer):\n'+json.dumps(examples,ensure_ascii=False)
