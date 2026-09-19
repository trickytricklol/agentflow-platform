# 11 · SafeFlow-Evo 论文级研究规格

## 研究问题

在模型权重固定、候选评估昂贵、工作流结构离散且企业业务不允许关键切片退化的条件下，如何用有限预算联合优化 Agent 工作流的拓扑、节点指令和 demonstrations？

## 核心假设

1. 仅用 Prompt Embedding 的 surrogate 无法充分表达拓扑和 demo set 差异。
2. 文本、拓扑、demo 集合的混合表示能提高固定预算内找到优质候选的概率。
3. 把成本和业务安全作为约束纳入 acquisition，比先追求准确率、发布时再过滤更高效。
4. 重复验证和业务切片非退化约束能降低小验证集导致的误发布率。

## 算法

候选基因 `x=(topology, instructions, demo_ids, tool_config)`。第一版表示为：

`phi(x) = [sqrt(w_t) E(prompt), sqrt(w_g) onehot(topology), sqrt(w_d) normalized_multihot(demo_ids)]`

权重在测试前冻结。质量代理模型与可发布性代理模型分别使用 GP。采集函数：

`a(x) = EI_quality(x) * P(feasible(x)) / estimated_cost(x)^alpha`

其中 feasible 表示重复验证和 route/priority 业务切片门槛通过；cost 在执行前由节点调用数和 Prompt 长度估计，执行后报告真实 Token/延迟。

约束模型在至少观察到两个候选且同时出现可行/不可行标签前不参与 acquisition，避免单一基线标签造成虚假确定性。开发池冻结 `w_text=0.55, w_topology=0.25, w_demos=0.20, alpha=0.5`；后续确认池不得再修改。

## 基线

- 固定 Prompt、固定 few-shot。
- Random Search。
- 纯文本 GP/EI。
- 文本+拓扑 GP/EI。
- MIPROv2 或机制对齐实现。
- GEPA 或机制对齐实现。
- AFlow/MCTS 受限 operator 版本。
- SafeFlow-Evo 完整方法。

## 实验协议

- 至少三个公开任务、五个随机种子。
- 所有搜索算法对齐模型调用、样本评估次数及 Token 三类预算并分别报告。
- train 生成/搜索，validation 选版和可行性学习，test 只执行一次；开发完成后建立从未查看的 final confirmation。
- 报告均值、标准差、95% bootstrap CI、配对检验、候选发现 regret、Token、延迟和误发布率。
- 消融：去除 topology 特征、demo 特征、可行性概率、成本项、重复验证、切片约束。

## 安全边界

不执行模型生成代码；只允许白名单 DSL/operator。不可变业务策略优先。候选必须通过 DAG 校验、预算、重复验证、业务切片门槛，并保存回滚版本。

## 论文级验收

- 至少两项主要指标对 Random Search 和纯文本 GP 有统计显著提升；或在效果相当时显著降低 Token/误发布率。
- 至少两个公开任务复现主要趋势，不能只在自建工单集成立。
- 公开配置、固定数据版本、全部种子、失败实验、原始预测和证据校验器。
- 若没有显著优势，结论必须改为负结果或系统论文，不包装最高单次结果。
