"""Read-only consistency checks on saved model outputs; incomplete runs are identified."""
import json
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'/'src'))
from agentflow.optimization.evolution import grade


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
            assert record['selected']['validation']['reward']>report['baseline']['validation']['reward']
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


if __name__ == '__main__':
    for path in sorted((ROOT/'evaluation'/'results').glob('*/report.json')):
        print(path.parent.name+': '+verify(path.parent))
