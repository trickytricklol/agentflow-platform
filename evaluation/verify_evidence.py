"""Read-only consistency checks on saved model outputs; incomplete runs are identified."""
import json
import hashlib
import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'/'src'))
from agentflow.optimization.evolution import grade
from agentflow.optimization.pareto import instance_pareto_front, hybrid_pareto_front, complementary_pairs
from agentflow.optimization.structural import risk_aware_release
from agentflow.optimization.safe_bo import estimated_inference_cost, validation_feasible


def verify(folder):
    data = json.loads((ROOT/'evaluation'/'triage_v1.json').read_text(encoding='utf-8'))
    expected = {r[0]:{'route':r[2],'priority':r[3]} for r in data['test']}
    report = json.loads((folder/'report.json').read_text(encoding='utf-8'))
    if 'test_summary' not in report:
        return 'INCOMPLETE (not evidence of successful evaluation)'
    for arm, rows in report['test_rows'].items():
        assert len(rows)==len(expected), (folder,arm,'wrong number of test cases')
        assert {r['id'] for r in rows}==set(expected), (folder,arm,'split mismatch')
        for row in rows:
            assert row['expected']==expected[row['id']], (folder,arm,row['id'],'changed label')
            correct, valid = grade(row['output'],expected[row['id']])
            assert (correct,valid)==(row['correct'],row['valid_json']), (folder,arm,row['id'],'incorrect score')
            if 'trace' in row:
                for key in ('input_tokens','output_tokens'):
                    assert row[key]==sum(t[key] for t in row['trace']), (folder,arm,'usage mismatch')
        summary = report['test_summary'][arm]
        assert summary['n']==len(rows)
        assert abs(summary['success']-sum(r['correct'] for r in rows)/len(rows))<1e-12
        assert summary['tokens']==sum(r.get('input_tokens',0)+r.get('output_tokens',0) for r in rows)
    for arm, record in report['arms'].items():
        if record['release']['released']:
            selection=record.get('selected') or record.get('winner')
            assert selection['validation']['reward']>report['baseline']['validation']['reward']
            assert 'rollback' in record['release']
    confirmation_path=folder/'confirmation.json'
    if confirmation_path.exists():
        confirmation=json.loads(confirmation_path.read_text(encoding='utf-8'))
        raw=(ROOT/'evaluation'/'triage_confirmation_v1.json').read_bytes()
        labels={r[0]:{'route':r[2],'priority':r[3]} for r in json.loads(raw.decode('utf-8'))['cases']}
        assert confirmation['source_report_sha256']==hashlib.sha256((folder/'report.json').read_bytes()).hexdigest()
        assert confirmation['confirmation_sha256']==hashlib.sha256(raw).hexdigest()
        assert confirmation['variants']==report['frozen_variants'], 'confirmation changed selected versions'
        for arm, rows in confirmation['rows'].items():
            assert len(rows)==len(labels) and {r['id'] for r in rows}==set(labels)
            for row in rows:
                assert row['expected']==labels[row['id']]
                assert grade(row['output'],row['expected'])==(row['correct'],row['valid_json'])
                for key in ('input_tokens','output_tokens'):
                    assert row[key]==sum(t[key] for t in row['trace'])
            summary=confirmation['summary'][arm]
            assert summary['correct']==sum(r['correct'] for r in rows)
            assert summary['n']==len(rows)
            assert summary['success']==summary['correct']/len(rows)
            assert summary['tokens']==sum(r['input_tokens']+r['output_tokens'] for r in rows)
    return 'PASS'


def verify_joint(folder):
    status=verify(folder)
    report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    source=ROOT/report['source_path']
    assert report['source_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
    data=json.loads((ROOT/'evaluation'/'triage_v1.json').read_text(encoding='utf-8'))
    labels={split:{r[0]:{'route':r[2],'priority':r[3]} for r in data[split]} for split in ('train','validation','test')}
    training_ids=set(labels['train'])
    for candidate in report['pool']:
        assert set(candidate['demo_ids'])<=training_ids
    for result in report['evaluation_cache'].values(): verify_rows(result['rows'],labels['train'],True)
    for record in report['arms'].values():
        assert len(record['steps'])==report['budget']
        for step in record['steps']:
            identity=json.dumps(step['candidate']['genome'],sort_keys=True,ensure_ascii=False)
            assert step['train']==report['evaluation_cache'][identity]
        for item in record['validation_candidates']: verify_rows(item['validation']['rows'],labels['validation'],True)
    stability_path=folder/'stability.json'
    if stability_path.exists():
        stability=json.loads(stability_path.read_text(encoding='utf-8'))
        assert len(stability['seeds'])>=2 and stability['baseline']==report['baseline']['genome']
        for name,runs in stability['runs'].items():
            assert len(runs)==len(stability['seeds'])
            for run in runs: verify_rows(run['rows'],labels['validation'],True)
        for arm,genome in stability['candidates'].items():
            expected=risk_aware_release(stability['baseline'],genome,stability['runs']['baseline'],stability['runs'][arm])
            assert stability['decisions'][arm]==expected
    return status


def verify_acquisition(path):
    report=json.loads(path.read_text(encoding='utf-8'))
    source=ROOT/report['source_directory']/'report.json'
    assert report['source_report_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
    data=json.loads((ROOT/'evaluation'/'triage_v1.json').read_text(encoding='utf-8'))
    labels={r[0]:{'route':r[2],'priority':r[3]} for r in data['train']}
    scores={}
    for identity,item in report['evaluations'].items():
        assert identity==json.dumps(item['genome'],sort_keys=True,ensure_ascii=False)
        rows=item['result']['rows']
        assert len(rows)==len(labels) and {row['id'] for row in rows}==set(labels)
        for row in rows:
            assert row['expected']==labels[row['id']]
            assert grade(row['output'],row['expected'])==(row['correct'],row['valid_json'])
        scores[identity]=sum(row['correct'] for row in rows)/len(rows)
        assert abs(scores[identity]-item['result']['reward'])<1e-12
    source_report=json.loads(source.read_text(encoding='utf-8'))
    candidate_keys=[json.dumps(g,sort_keys=True,ensure_ascii=False) for g in source_report['pool']]
    budget=report['budget']
    bests=[max(scores[k] for k in subset) for subset in itertools.combinations(candidate_keys,budget)]
    result=report['result']
    assert result['candidate_count']==len(candidate_keys)
    assert result['oracle_score']==max(scores[k] for k in candidate_keys)
    assert result['random_exact']['subsets']==len(bests)
    assert abs(result['random_exact']['mean_best']-sum(bests)/len(bests))<1e-12
    assert abs(result['random_exact']['probability_find_oracle']-sum(v==result['oracle_score'] for v in bests)/len(bests))<1e-12
    for trajectory in result['trajectories'].values():
        assert len(trajectory['steps'])==budget
        seen=set()
        for step in trajectory['steps']:
            identity=json.dumps(step['candidate'],sort_keys=True,ensure_ascii=False)
            assert identity in candidate_keys and identity not in seen
            seen.add(identity)
            assert step['score']==scores[identity]
            assert step['tokens']==report['evaluations'][identity]['result']['tokens']
        assert trajectory['best_score']==max(step['score'] for step in trajectory['steps'])
        assert trajectory['tokens']==sum(step['tokens'] for step in trajectory['steps'])
    return 'PASS'


def verify_rows(rows,labels,require_all=False):
    if require_all:
        assert len(rows)==len(labels) and {row['id'] for row in rows}==set(labels)
    for row in rows:
        assert row['id'] in labels and row['expected']==labels[row['id']]
        assert grade(row['output'],row['expected'])==(row['correct'],row['valid_json'])
        if 'trace' in row:
            assert row['input_tokens']==sum(item['input_tokens'] for item in row['trace'])
            assert row['output_tokens']==sum(item['output_tokens'] for item in row['trace'])


def verify_pareto(folder):
    report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    source=ROOT/report['source_path']
    assert report['source_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
    archive=json.loads(source.read_text(encoding='utf-8'))
    evaluations={key:item['result'] for key,item in archive['evaluations'].items()}
    data=json.loads((ROOT/'evaluation'/'triage_v1.json').read_text(encoding='utf-8'))
    labels={split:{r[0]:{'route':r[2],'priority':r[3]} for r in data[split]} for split in ('train','validation','test')}
    case_ids=tuple(labels['train'])
    mode='hybrid' if report['protocol'].startswith('hybrid') else 'exact'
    frontier=hybrid_pareto_front(evaluations,case_ids) if mode=='hybrid' else instance_pareto_front(evaluations,case_ids)
    assert report['frontier']==frontier
    assert report['pair_ranking']==complementary_pairs(evaluations,case_ids,frontier,mode)
    for attempt in report['attempts']:
        verify_rows(attempt['child_minibatch']['rows'],labels['train'])
        assert set(attempt['minibatch_ids'])=={row['id'] for row in attempt['child_minibatch']['rows']}
        if attempt['accepted']:
            assert attempt['child_minibatch']['success']>=attempt['parent_best_minibatch']
            verify_rows(attempt['train']['rows'],labels['train'],True)
    for item in report['validation_candidates']:
        verify_rows(item['validation']['rows'],labels['validation'],True)
    for rows in report['test_rows'].values(): verify_rows(rows,labels['test'],True)
    if report['release']['released']:
        assert report['winner']['validation']['reward']>report['baseline']['validation']['reward']
        assert 'rollback' in report['release']
    else:
        assert report['frozen_variants']['released']==report['baseline']['genome']
    return 'PASS'


def verify_safeflow(path):
    report=json.loads(path.read_text(encoding='utf-8'))
    source=ROOT/report['source_path']
    assert report['source_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
    data=json.loads((ROOT/'evaluation'/'triage_v1.json').read_text(encoding='utf-8'))
    labels={split:{r[0]:{'route':r[2],'priority':r[3]} for r in data[split]} for split in ('train','validation')}
    training_ids=set(labels['train'])
    candidate_keys=[]
    for candidate in report['candidates']:
        assert set(candidate['demo_ids'])<=training_ids
        candidate_keys.append(json.dumps(candidate['genome'],sort_keys=True,ensure_ascii=False))
    evaluations=report['evaluations']
    assert len(evaluations)==len(candidate_keys)+1
    baseline_keys=[]
    quality={}
    feasible={}
    costs={}
    for identity,item in evaluations.items():
        assert identity==json.dumps(item['candidate']['genome'],sort_keys=True,ensure_ascii=False)
        verify_rows(item['train']['rows'],labels['train'],True)
        verify_rows(item['validation']['rows'],labels['validation'],True)
        assert item['train']['reward']==item['train']['success']
        assert item['validation']['reward']==item['validation']['success']
        quality[identity]=item['train']['reward']
        costs[identity]=estimated_inference_cost(item['candidate'])
        if identity not in candidate_keys:
            baseline_keys.append(identity)
    assert len(baseline_keys)==1
    baseline_key=baseline_keys[0]
    base_validation=evaluations[baseline_key]['validation']
    for identity,item in evaluations.items():
        feasible[identity]=(identity==baseline_key or validation_feasible(base_validation,item['validation']))
    result=report['result']
    assert result['feasible_candidates']==sum(feasible[k] for k in candidate_keys)
    oracle=max(quality[k] for k in [baseline_key]+candidate_keys if feasible[k])
    assert result['oracle_feasible_quality']==oracle
    subset_best=[]
    for subset in itertools.combinations(candidate_keys,report['budget']):
        subset_best.append(max(quality[k] for k in (baseline_key,)+subset if feasible[k]))
    exact=result['random_exact']
    assert exact['subsets']==len(subset_best)
    assert abs(exact['mean_best_feasible']-sum(subset_best)/len(subset_best))<1e-12
    assert abs(exact['probability_find_oracle']-sum(v==oracle for v in subset_best)/len(subset_best))<1e-12
    for trajectory in result['trajectories'].values():
        assert len(trajectory['steps'])==report['budget']
        seen=set()
        for step in trajectory['steps']:
            identity=json.dumps(step['candidate']['genome'],sort_keys=True,ensure_ascii=False)
            assert identity in candidate_keys and identity not in seen
            seen.add(identity)
            assert step['quality']==quality[identity]
            assert step['feasible']==feasible[identity]
            assert step['estimated_cost']==costs[identity]
        selected=[baseline_key]+[json.dumps(step['candidate']['genome'],sort_keys=True,ensure_ascii=False) for step in trajectory['steps']]
        assert trajectory['best_feasible_quality']==max(quality[k] for k in selected if feasible[k])
        assert trajectory['estimated_cost']==sum(step['estimated_cost'] for step in trajectory['steps'])
    return 'PASS'


if __name__ == '__main__':
    for path in sorted((ROOT/'evaluation'/'results').glob('*/report.json')):
        payload=json.loads(path.read_text(encoding='utf-8'))
        verifier=verify_pareto if 'pair_ranking' in payload else verify_joint if 'evaluation_cache' in payload else verify
        print(path.parent.name+': '+verifier(path.parent))
    for path in sorted((ROOT/'evaluation'/'results').glob('*/acquisition.json')):
        print(path.parent.name+': '+verify_acquisition(path))
    for path in sorted((ROOT/'evaluation'/'results').glob('*/benchmark.json')):
        print(path.parent.name+': '+verify_safeflow(path))
