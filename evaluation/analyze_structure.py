"""Summarize frozen topology experiments, including cost and failed candidates."""
import json
import sys
from pathlib import Path
from analyze_evolution import wilson


def main():
    folder = Path(sys.argv[1])
    report = json.loads((folder/'report.json').read_text(encoding='utf-8'))
    lines = ['# 结构自进化实验', '',
             '执行模型：`'+report['model']+'`；变异模型：`'+report['teacher_model']+'`；种子：'+str(report['seed']),
             '', '共同候选池，四个新候选的训练评估预算；两节点拓扑具有更高调用费用。', '',
             '| 方法 | 发布拓扑 | 测试正确 | 95% Wilson | 测试 Token | 模型调用 |',
             '|---|---|---:|---:|---:|---:|']
    for name, rows in report['test_rows'].items():
        k = sum(r['correct'] for r in rows)
        n = len(rows)
        lo, hi = wilson(k,n)
        tokens = sum(r['input_tokens']+r['output_tokens'] for r in rows)
        calls = sum(len(r['trace']) for r in rows)
        lines.append('| {} | {} | {}/{} ({:.1%}) | {:.1%}–{:.1%} | {} | {} |'.format(name,report['frozen_variants'][name]['topology'],k,n,k/n,lo,hi,tokens,calls))
    lines += ['', '## 搜索轨迹与开销', '']
    shared = sum(r.get('input_tokens',0)+r.get('output_tokens',0) for r in report['mutations'])
    shared += report['baseline']['train']['tokens']+report['baseline']['validation']['tokens']
    for arm, record in report['arms'].items():
        cost = shared + sum(c['train']['tokens'] for c in record['curve']) + sum(c['validation']['tokens'] for c in record['validation_candidates'])
        lines.append('- {}：优化与验证 {} Token（共享成本全额计入每臂）；发布 {}。'.format(arm,cost,record['release']['released']))
        for i, candidate in enumerate(record['curve']):
            lines.append('  - 候选 {}：{}，训练 {:.1%}。'.format(i+1,candidate['genome']['topology'],candidate['train']['success']))
        (folder/(arm+'-workflow.json')).write_text(json.dumps(record['release'],ensure_ascii=False,indent=2),encoding='utf-8')
    lines += ['', '## 解释边界', '',
              '- 自建模拟工单、小测试集、研究过程中重复使用；仅探索性结果，不代表生产泛化。',
              '- 固定 few-shot 基线使用随机选四个训练样本，不使用测试反馈。',
              '- 不同拓扑的 Token 和模型调用不等；当前不是等 Token 预算比较。',
              '- 结构来自三种预定义模板，不声称自主生成任意 DAG。',
              '- 单个种子或胜出不足以证明 GP/EI 稳定优于随机搜索。', '']
    (folder/'analysis.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(report['test_summary'],indent=2))


if __name__ == '__main__':
    main()
