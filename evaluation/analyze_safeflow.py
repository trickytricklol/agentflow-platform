"""Render a compact, comparable summary of SafeFlow-Evo benchmark artifacts."""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('reports',nargs='+')
    args=parser.parse_args()
    print('| run | feasible pool | oracle | random exact | oracle probability | method | best safe | estimated cost |')
    print('|---|---:|---:|---:|---:|---|---:|---:|')
    for name in args.reports:
        path=Path(name); report=json.loads(path.read_text(encoding='utf-8')); result=report['result']
        for method,trajectory in result['trajectories'].items():
            print(f"| {path.parent.name} | {int(result['feasible_candidates'])}/{len(report['candidates'])} "
                  f"| {result['oracle_feasible_quality']:.3f} | {result['random_exact']['mean_best_feasible']:.3f} "
                  f"| {result['random_exact']['probability_find_oracle']:.3f} | {method} "
                  f"| {trajectory['best_feasible_quality']:.3f} | {trajectory['estimated_cost']:.2f} |")


if __name__=='__main__':
    main()
