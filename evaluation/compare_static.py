"""Strong few-shot baseline; uses TRAIN examples only, evaluates a frozen run."""
import json
import random
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'/'src'))
from agentflow.optimization.evolution import RewardSpec, WorkflowEvaluator
from agentflow.providers import OpenAICompatibleProvider


def main():
    folder=Path(sys.argv[1])
    target=folder/'static-fewshot.json'
    if target.exists():
        raise ValueError('refusing to overwrite baseline evidence')
    report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    dataset=json.loads((ROOT/'evaluation'/'triage_v1.json').read_text(encoding='utf-8'))
    train=dataset['train'][:]
    random.Random(report['seed']).shuffle(train)
    examples=[{'ticket':r[1],'answer':{'route':r[2],'priority':r[3]}} for r in train[:4]]
    prompt=report['baseline']['prompt']+'\nReference training cases:\n'+json.dumps(examples)
    cases=[{'id':r[0],'text':r[1],'expected':{'route':r[2],'priority':r[3]}} for r in dataset['test']]
    evaluator=WorkflowEvaluator(OpenAICompatibleProvider('http://127.0.0.1:11434/v1','local-ollama',120),report['model'],dataset['policy'],RewardSpec.parse(report['reward']))
    result=evaluator.evaluate(prompt,cases,report['seed'])
    target.write_text(json.dumps({'training_ids':[r[0] for r in train[:4]],'prompt':prompt,'result':result},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Static few-shot success:',result['success'])


if __name__=='__main__':
    main()
