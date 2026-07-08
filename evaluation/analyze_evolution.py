"""Render evidence from saved experiments; no model calls or score editing."""
import argparse
import json
import math
from pathlib import Path


def wilson(k,n):
    z=1.96
    center=(k/n+z*z/(2*n))/(1+z*z/n)
    half=z*math.sqrt(k/n*(1-k/n)/n+z*z/(4*n*n))/(1+z*z/n)
    return [center-half,center+half]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory')
    args=parser.parse_args()
    directory=Path(args.directory)
    report=json.loads((directory/'report.json').read_text(encoding='utf-8'))
    rows=report['test_rows']
    baseline={r['id']:r for r in rows['baseline']}
    lines=['# 工作流自进化实验报告','',
           '场景：模拟企业工单路由。相同模型、相同业务规则；测试集不参与进化或选版。',
           '', '模型：`'+report['model']+'`；Embedding：`'+report['embedding']+'`；种子：'+str(report['seed']),
           '', '| 方法 | 严格任务成功 | 95% Wilson 区间 | 相对基线 | 格式合法率 |',
           '|---|---:|---:|---:|---:|']
    base_rate=sum(r['correct'] for r in baseline.values())/len(baseline)
    for name,items in rows.items():
        k=sum(r['correct'] for r in items); n=len(items); lo,hi=wilson(k,n)
        lines.append('| {} | {}/{} ({:.1%}) | {:.1%}–{:.1%} | {:+.1f} pp | {:.1%} |'.format(name,k,n,k/n,lo,hi,(k/n-base_rate)*100,sum(r['valid_json'] for r in items)/n))
    if (directory/'static-fewshot.json').exists():
        fixed=json.loads((directory/'static-fewshot.json').read_text(encoding='utf-8'))['result']['rows']
        k=sum(r['correct'] for r in fixed); n=len(fixed); lo,hi=wilson(k,n)
        lines.append('| static few-shot | {}/{} ({:.1%}) | {:.1%}–{:.1%} | {:+.1f} pp | {:.1%} |'.format(k,n,k/n,lo,hi,(k/n-base_rate)*100,sum(r['valid_json'] for r in fixed)/n))
    lines+=['','## 算法决策与开销','',
            '每个搜索臂最多评估 4 个新候选，每个候选执行 12 条训练工作流。每轮生成 3 个候选，仅挑选 2 个评估。验证集用于选版；测试集只做最终评估。',
            '', '| 方法 | 优化及验证 Token（含共享基线分摊全额） | 验证发布门槛 | 测试胜/负/平 | 双侧配对符号检验 p |',
            '|---|---:|---|---:|---:|']
    for arm,data in report['arms'].items():
        cost=report['goal_tokens']+report['baseline']['train']['tokens']+report['baseline']['validation']['tokens']
        cost+=sum(m.get('input_tokens',0)+m.get('output_tokens',0) for m in data['mutations'])
        cost+=sum(c['train']['tokens'] for c in data['curve'])+sum(c['validation']['tokens'] for c in data['validation_candidates'])
        wins=sum(r['correct'] and not baseline[r['id']]['correct'] for r in rows[arm])
        losses=sum(not r['correct'] and baseline[r['id']]['correct'] for r in rows[arm])
        discord=wins+losses
        # Exact two-sided sign test on discordant pairs, independent tasks assumed.
        p=min(1,2*sum(math.factorial(discord)/(math.factorial(i)*math.factorial(discord-i)) for i in range(min(wins,losses)+1))/2**discord) if discord else 1
        lines.append('| {} | {} | {} | {}/{}/{} | {:.4f} |'.format(arm,cost,data['release']['released'],wins,losses,len(baseline)-discord,p))
        lines+=[]
        (directory/(arm+'-workflow.json')).write_text(json.dumps(data['release'],ensure_ascii=False,indent=2),encoding='utf-8')
    lines+=['','## 解释边界','',
            '- 这是固定业务规则下的模拟数据，24 条测试样本不足以证明生产泛化。',
            '- baseline 是有完整业务规则的固定指令；优化收益不包含换模型或给优化臂额外规则。',
            '- 随机搜索也使用失败反馈；其胜出意味着反思可能有效，但 EI 未体现增益。',
            '- Token 包含优化器、候选执行与验证；不把优化阶段开销隐藏为免费。',
            '- 测试延迟为逐样本交错墙钟时间，只用于诊断，不作硬件无关性能结论。',
            '- 词法/神经向量、不同种子须分别报告；不能只挑最好的一次。',
            '', '## 逐条失败', '']
    for name,items in rows.items():
        lines.append('- '+name+'：'+', '.join(r['id'] for r in items if not r['correct']))
    (directory/'analysis.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines))


if __name__=='__main__':
    main()
