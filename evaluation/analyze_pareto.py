"""Render GEPA-inspired merge evidence without model calls."""
import json
import sys
from pathlib import Path


def main():
    folder=Path(sys.argv[1]); report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    lines=['# Pareto 反思合并实验','',
           '协议：`'+report['protocol']+'`','',
           'Pareto 前沿：{} 个候选；互补父代组合：{} 个；实际合并：{} 次。'.format(len(report['frontier']),len(report['pair_ranking']),len(report['attempts'])),
           '','| 合并 | 互补增益 | 拓扑 | mini-batch | 门控 | 完整训练 |','|---:|---:|---|---:|---|---:|']
    for index,item in enumerate(report['attempts'],1):
        lines.append('| {} | {} | {} | {:.1%} | {} | {} |'.format(index,item['pair']['complementary_gain'],item['child']['topology'],
            item['child_minibatch']['success'],item['accepted'],('{:.1%}'.format(item['train']['success']) if 'train' in item else '未执行')))
    lines+=['','| 冻结版本 | 测试成功率 | Token |','|---|---:|---:|']
    for name,summary in report['test_summary'].items():
        lines.append('| {} | {:.1%} | {} |'.format(name,summary['success'],summary['tokens']))
    lines+=['','发布：`{}`；原因：{}。'.format(report['release']['released'],report['release']['reason']),'',
            'mini-batch 只作低成本预筛。完整训练与独立验证仍决定是否发布；小批量改善不能作为最终收益。','']
    (folder/'analysis.md').write_text('\n'.join(lines),encoding='utf-8')
    print('\n'.join(lines))


if __name__=='__main__': main()
