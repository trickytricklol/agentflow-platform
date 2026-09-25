# 自进化工作流方法调研与落地

## 与当前项目最相似的方法

| 方法 | 核心机制 | 与本项目关系 | 本轮决策 |
|---|---|---|---|
| [GEPA](https://arxiv.org/abs/2507.19457) / [官方代码](https://github.com/gepa-ai/gepa) | 完整轨迹反思、实例级 Pareto 档案、minibatch 变异、互补候选 merge | 最接近“从执行失败持续进化工作流” | 实现受限版 Pareto、互补选择、ASI 合并、审计和门控 |
| [MIPRO](https://arxiv.org/abs/2406.11695) / [DSPy](https://github.com/stanfordnlp/dspy) | 联合搜索 instruction 与 few-shot demonstrations，随机小批量评估和 surrogate | 当前只固定回放四个示例，尚未联合优化示例集合 | 下一阶段把 demo IDs 纳入 genome |
| [AFlow](https://arxiv.org/abs/2410.10762) / [官方代码](https://github.com/FoundationAgents/AFlow) | 代码表示工作流，MCTS 搜索 Generate/Review/Ensemble 等 operator | 当前只搜索 direct/decompose/review 三种模板 | 借鉴树搜索经验回传，但继续使用白名单 DSL，不执行生成代码 |
| [GPTSwarm](https://arxiv.org/abs/2402.16823) / [代码](https://github.com/metauto-ai/GPTSwarm) | 节点 Prompt 优化与可学习边连接 | 当前“文本+拓扑”向量已证明比纯文本更容易找到训练最优 | 后续扩展为边开关/节点 operator 的离散搜索 |
| [ADAS](https://arxiv.org/abs/2408.08435) / [代码](https://github.com/ShengranHu/ADAS) | 元 Agent 基于历史档案发明新 Agent，并做自我修正 | 与主从 Agent 自生成故事高度相关 | 采用档案与二次审计；拒绝无沙箱任意代码执行 |
| [TextGrad](https://arxiv.org/abs/2406.07496) / [代码](https://github.com/zou-group/textgrad) | 将执行反馈作为 textual gradient 反向更新复合系统组件 | 可增强节点级 credit assignment | 本轮将合并草案再做策略一致性审计 |

## 本轮实现

新增的算法不是完整复现 GEPA，而是适配本项目安全边界的机制移植：

1. 从真实训练执行结果构造候选 × 实例得分矩阵。
2. 支持 exact instance frontier 和 format/route/priority 的 case-objective hybrid frontier。
3. 根据父代正确集合的 union gain 排序互补组合。
4. 只向 4B 反思模型提供训练轨迹，生成受限 `topology + prompt`，禁止代码。
5. 对草案执行第二轮不可变策略审计。
6. 先在父代分歧 mini-batch 门控，通过后才跑完整训练和验证。
7. 只有验证严格提升才能发布；否则部署版本保持原基线。

## 实验发现

- seed29 候选池存在逐实例支配其他候选的单一成员，Pareto 前沿坍缩为 1，系统跳过 merge。
- seed17 hybrid frontier 保留 5 个候选。审计后某个 child 在 4 条 mini-batch 上达到 100%，但完整训练只有 50%，验证未超过 58.3% 基线，测试为 50%。发布门槛正确拒绝该候选。
- 结论不是“GEPA 无效”，而是当前 12 条训练样本、二值业务奖励与 4B 本地反思模型不足以让 merge 稳定泛化。mini-batch 适合节约评估成本，不适合直接决定发布。

## 下一步优先级

1. 已实现 MIPRO 式 instruction × demo IDs 联合搜索；下一步把 topology 一并纳入、增加独立任务复验。
2. 用 route/priority/format 分项反馈指导 mutation，但最终奖励继续使用严格全对。
3. 增加多个独立任务和候选池；不在已经看过的确认集上继续调参。
4. 引入 AFlow 式 operator tree，仅允许白名单节点和边变换；每次变换必须通过 DAG 校验、预算和验证门槛。
5. 在更大开发集上比较当前 GP/EI、Pareto merge、随机搜索和固定 few-shot，并报告等 Token 预算。

## 联合搜索追加结果

固定候选池由四个去除旧示例的 instruction 与空/覆盖/失败优先/随机 demo sets 组合而成；随机与 GP/EI 各评估六个候选，验证只检查训练排名最高的两个。

- seed17：单次验证让 random 与 GP/EI 都通过；旧测试分别为 58.3% 和 58.3%，低于 70.8% 基线，但确认样本为 62.5% 和 66.7%，高于 41.7% 基线。
- seed29：random 单次验证通过，旧测试 66.7%，确认样本 70.8%；GP/EI 保留基线。
- 三次重复验证加业务切片门控后，仅 seed17 random 保持发布；seed17 GP/EI 因 `priority:P2` 退化被拒，seed29 random 同样被拒。

该结果说明联合 demo 搜索比 Pareto merge 更有希望，但单次 12 条验证会误发布。生产故事应强调风险门控和可回滚，而不是只报确认集最高 70.8%。

## 2026-09 轮：ASI 归因反馈与多样性感知采集

对照 2025–2026 自进化方向复查代码后，本轮只做两处**默认关闭、可 A/B** 的增量，不改写既有实验路径与结论：

1. **Actionable Side Information（GEPA，arXiv:2507.19457；AgentEvolver 逐步归因，arXiv:2511.10395）**：
   严格奖励仍是 route+priority 全对，但新增 `diagnose_output` 把一次失败拆成
   `format / route / priority` 三子项，并给出实际值 vs 期望。`FeedbackMutator(..., asi=True)`
   把这份逐子项 `faults` 喂给变异模型，并要求"只修坏的子项、不要重写/回退父代已答对的子项"。
   此前 `component_score_vector` 已经能算三子项分，但反馈环节只告诉变异模型"错了"，
   这是把已有归因信号接到反思器上的闭环。`asi=False` 时请求体与指令与历史完全一致。
2. **Diversity-aware acquisition（EvoTool：blame-aware mutation + diversity-aware selection）**：
   `GaussianProcessOptimizer(..., diversity_weight=w, xi=xi)`。`w>0` 时把剩余候选的 EI 与
   嵌入空间新颖度（到已观测提示的平均距离）各自 min-max 归一化后线性标量化，缓解本仓库多次
   观察到的"候选池 / Pareto 前沿坍缩到 1、GP 只在近邻重复采样"。`w=0` 时逐候选选择与历史 EI 完全相同。
   `xi` 是经典 EI 探索边际，默认 0。

验证：`backend/tests/test_asi_diversity.py` 新增 8 个用例（归因定位、未改坏的 schema/解析、
`grade` 旧行为逐字兼容、asi 开关请求体差异、纯新颖度选最远未触达点、参数合法性）。全套 70 passed。
真实 Ollama A/B（qwen3:1.7b 执行臂 + nomic 嵌入）在独立输出目录跑，不覆盖既有证据。

### 首轮 A/B 实测（seed17，1.7B，48 条自建工单）

脚本 `examples/ab_asi_diversity.py`，同一切分/同一 seed/同一执行臂，只隔离两个变量：
legacy（asi=False, diversity_weight=0）vs ASI+diverse（asi=True, diversity_weight=0.3）。

- baseline train 0.583；legacy 臂两个候选 train 0.500/0.333，ASI 臂两个候选 train 0.667/0.667
  —— 逐子项归因反馈确实把训练集候选质量抬上去了（+16~33 个点）。
- 发布门：legacy 臂在单次验证 0.500>0.417 时 `released=True`；ASI 臂选中验证 0.583 与其自身
  基线 0.583 持平，按"严格提升"判据 `released=False`。
- held-out 测试集（24 条，未参与变异/选版）：baseline 0.458，legacy 0.417，ASI+diverse 0.417。

结论（不夸大）：逐子项归因与多样性采集在 12 条训练样本上稳定地抬升训练侧候选分，但没有迁移到
held-out 测试；单次验证的 legacy "发布"在测试上反而回落，正是 `risk_aware_release` 重复验证门要拦的
假阳性。这与仓库既有判断一致——瓶颈是样本量与模型容量，不是反馈信号形式。下一步应先扩开发集，
再用重复验证门复核这两个机制，而不是在 12 条样本上继续调参。

下一步候选（仍未做，按杠杆排序）：
- 用重复验证观测估计 GP 观测噪声，替换固定 `noise=0.05`；
- 推理期按工单嵌入动态检索 few-shot（MIPRO/KNN-ICL），替代静态四示例；
- best-of-N 自洽解码作为可选臂，与单次 greedy 等 token 预算对比。
