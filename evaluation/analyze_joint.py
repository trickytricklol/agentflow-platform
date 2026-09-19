"""Render joint instruction/demo search and repeated release audit."""
import json
import sys
from pathlib import Path


def main():
    folder=Path(sys.argv[1]); report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    confirmation=json.loads((folder/'confirmation.json').read_text(encoding='utf-8')) if (folder/'confirmation.json').exists() else None
    stability=json.loads((folder/'stability.json').read_text(encoding='utf-8')) if (folder/'stability.json').exists() else None
    lines=['# 指令与示例联合搜索','',
           '候选池：{}；每个搜索臂评估预算：{}；示例集合：{}。'.format(len(report['pool']),report['budget'],len(report['demo_sets'])),
           '','| 方法 | 单次验证 | 原发布 | 三次风险门控 | 旧测试 | 确认样本 |','|---|---:|---|---|---:|---:|']
    for name in ('baseline','random','gp_ei'):
        if name=='baseline':
            val=report['baseline']['validation']['success']; original='基线'; risk='基线'
        else:
            val=report['arms'][name]['winner']['validation']['success']; original=str(report['arms'][name]['release']['released'])
            decision=stability['decisions'][name] if stability else None
            risk=(str(decision['released'])+' ({:.1%} vs {:.1%})'.format(decision['candidate_mean'],decision['baseline_mean'])) if decision else '未测'
        test=report['test_summary'][name]['success']; confirm=confirmation['summary'][name]['success'] if confirmation else None
        lines.append('| {} | {:.1%} | {} | {} | {:.1%} | {} |'.format(name,val,original,risk,test,('{:.1%}'.format(confirm) if confirm is not None else '未测')))
    lines+=['','三次风险门控要求每次验证不退化、平均值严格提升，并且 route/priority 各业务切片均不退化。确认样本不参与本轮候选选择，但研究者此前已看过该集合，因此仍标记为探索性证据。','']
    (folder/'analysis.md').write_text('\n'.join(lines),encoding='utf-8')
    print('\n'.join(lines))


if __name__=='__main__': main()
