"""Create an auditable release/rollback decision from frozen confirmation."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('experiment'); parser.add_argument('confirmation',nargs='?'); parser.add_argument('--output',required=True)
    args=parser.parse_args(); experiment_path=ROOT/args.experiment
    experiment=json.loads(experiment_path.read_text(encoding='utf-8')); experiment_hash=hashlib.sha256(experiment_path.read_bytes()).hexdigest()
    if args.confirmation is None:
        trajectory=experiment['result']['trajectories']['reflection_gp']; winner=trajectory['winner']
        base=experiment['result']['baseline']['validation']; child=trajectory['validation']
        if child['accuracy']>base['accuracy']: raise ValueError('confirmation required after validation gain')
        result={'experiment_sha256':experiment_hash,'candidate':winner,'released':False,
                'decision':'REJECTED_NO_VALIDATION_GAIN','deployed_variant':'baseline','rollback_variant':'baseline',
                'criteria':'strict validation gain before frozen confirmation','confirmation_status':'SEALED_NOT_RUN',
                'evidence':{'baseline':base,'candidate':child}}
        target=ROOT/args.output; target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2)); return
    confirmation_path=ROOT/args.confirmation; confirmation=json.loads(confirmation_path.read_text(encoding='utf-8'))
    confirmation_hash=hashlib.sha256(confirmation_path.read_bytes()).hexdigest()
    if confirmation['signature']['source_report_sha256']!=experiment_hash: raise ValueError('confirmation is not bound to experiment')
    base=confirmation['summary']['baseline']; child=confirmation['summary']['reflection_gp']; paired=confirmation['paired']
    released=child['accuracy']>base['accuracy'] and paired['regressed']<=paired['improved']
    result={'experiment_sha256':experiment_hash,'confirmation_sha256':confirmation_hash,
            'candidate':confirmation['signature']['winner'],'released':released,
            'decision':'RELEASED' if released else 'REJECTED_CONFIRMATION_REGRESSION',
            'deployed_variant':'reflection_gp' if released else 'baseline',
            'rollback_variant':'baseline','criteria':'strict confirmation accuracy gain and regressions <= improvements',
            'evidence':{'baseline':base,'candidate':child,'paired':paired}}
    target=ROOT/args.output; target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2))


if __name__=='__main__': main()
