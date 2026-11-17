# 工作流优化

工作流优化引擎在不改变模型权重的前提下，持续改进工作流本身。可优化的对象包括节点指令、训练示例与受限拓扑结构。

## 优化对象

候选由三部分基因组成：

```text
genome = (topology, instruction, example_ids, tool_config)
```

| 维度 | 取值 |
|---|---|
| `topology` | `direct`（单节点决策）、`decompose`（路由/优先级双专家 + 汇总）、`review`（初判 + 复核） |
| `instruction` | 基线指令或由失败反馈生成的候选指令 |
| `example_ids` | 训练集中的示例组合，可为空 |
| `tool_config` | 工具节点配置（保持白名单约束） |

拓扑搜索只在预定义模板内进行，候选必须先通过 DAG 校验才允许执行；引擎不会执行模型生成的代码。

## 奖励

奖励采用严格业务口径：模型输出必须是仅含 `route`、`priority` 两个字符串字段的 JSON，两个字段全部正确才得 1 分，其余为 0 分。

```python
from agentflow.optimization.evolution import RewardSpec, grade

spec = RewardSpec(metric="exact_json", success_weight=1.0, token_penalty=0.0)
score, valid = grade('{"route": "account", "priority": "P1"}', {"route": "account", "priority": "P1"})
```

奖励配置只接受白名单字段，`success_weight` 必须为 1，`token_penalty` 限制在 `[0, 1]`。自然语言目标只映射为这份配置，不执行生成的代码。

## 闭环

```text
① 评估    当前版本在训练集上逐条执行，记录输出、Token、延迟
② 归因    逐子项诊断失败（route / priority / 格式），生成可执行反馈
③ 变异    失败反思生成候选指令；示例回放补充训练案例；拓扑模板交叉组合
④ 选样    神经嵌入 + RBF 高斯过程 + Expected Improvement，在预算内挑选候选
⑤ 验证    候选在独立验证集执行，比较整体指标与业务切片
⑥ 发布    通过发布门则生成新版本与回滚 DSL；否则保留当前版本
```

### 失败归因

`diagnose_output()` 把严格的全对/全错奖励拆成可执行反馈：哪个字段错、模型实际输出、策略期望值。变异器据此只修改出错部分，避免为了修 `route` 而重写正确的 `priority`。

### 候选变异

`FeedbackMutator` 将训练失败轨迹、业务规则与归因结果交给变异模型，生成候选指令。每个候选保存父版本、失败样本 ID 与反思原文，形成可追溯的候选谱系。

### 有限预算选样

`GaussianProcessOptimizer` 使用 RBF 核与观测噪声计算后验均值与方差，再按 Expected Improvement 选择下一个候选。采集时可按 `diversity_weight` 叠加新颖度，避免候选高度同质。

```python
from agentflow.optimization.bayesian import GaussianProcessOptimizer
from agentflow.optimization.embeddings import OllamaEmbeddingProvider

embedding = OllamaEmbeddingProvider("nomic-embed-text")
optimizer = GaussianProcessOptimizer(embedding, diversity_weight=0.2)
```

### 混合表示与安全约束

`SafeFlow` 将文本、拓扑与示例集编码为混合向量：

```text
phi(x) = [sqrt(w_text) * E(prompt), sqrt(w_topology) * onehot(topology), sqrt(w_example) * multihot(example_ids)]
```

默认权重 `w_text=0.55`、`w_topology=0.25`、`w_example=0.20`。采集函数同时考虑质量、可发布性与推理成本：

```text
a(x) = EI_quality(x) * P(feasible(x)) / estimated_cost(x)^alpha
```

- `P(feasible)` 由另一个 GP 估计，标签来自“验证整体提升且 route/priority 切片不退化”。
- 可行性模型至少观察到两个候选、且正负标签同时出现后才参与采集，避免单一标签造成过度自信。
- 成本由节点调用数与 Prompt 长度预估，默认指数 `alpha=0.5`。

### 结构搜索

`StructuralEvaluator` 执行候选拓扑对应的真实 DAG，并分别记录每个模型节点的输出与用量。`structural_release()` 与 `risk_aware_release()` 负责比较基线与候选：

- 候选在验证集上必须严格提升。
- 三次匹配种子的重复验证中，每次都不得退化。
- `route` 与 `priority` 的每个业务切片都不得退化。
- 任一条件不满足则拒绝发布，保留原版本。

### Pareto 合并与联合搜索

- `pareto.py` 支持实例级与 case×objective 的 Pareto 前沿、互补父代配对与合并候选；合并结果仍需完整训练与验证才能发布。
- 示例集模块生成空示例、标签覆盖、失败优先与随机四类示例集，与指令组合成联合候选池；随机基线与 GP/EI 使用相同评估预算。

## 运行

启动 Ollama 并准备模型：

```bash
ollama serve
ollama pull qwen3:1.7b
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

指令与示例优化：

```bash
python examples/evolve_workflow.py --embedding nomic --failure-replay --output runs/my-run
python evaluation/analyze_evolution.py runs/my-run
python evaluation/compare_static.py runs/my-run
```

拓扑与结构优化：

```bash
python examples/evolve_structure.py --teacher-model qwen3:4b --seed 17 --output runs/my-structure
python evaluation/analyze_structure.py runs/my-structure
python evaluation/confirm_frozen.py runs/my-structure
```

安全约束与联合搜索：

```bash
python evaluation/benchmark_acquisition.py runs/my-structure --output runs/acquisition.json --budget 4
python examples/evolve_pareto_merge.py runs/acquisition.json --output runs/my-pareto --frontier hybrid
python examples/evolve_joint_instruction_examples.py runs/acquisition.json --output runs/my-joint --budget 6
python evaluation/audit_release_stability.py runs/my-joint
```

每次运行使用新的输出目录；产物包含：

| 文件 | 内容 |
|---|---|
| `report.json` | 候选谱系、逐条输出、Token/延迟、验证与发布决策 |
| `confirmation.json` | 冻结版本的确认结果与文件哈希 |
| `release.json` | 发布/拒绝原因与回滚 DSL |
| `analysis.md` | 可读汇总 |

## 发布与回滚

发布产物保存两套 DSL：

- **新版本 DSL**：通过发布门的候选工作流。
- **回滚 DSL**：发布前的基线工作流。

运行失败、确认退化或人工回滚时，直接以回滚 DSL 覆盖当前版本，不需要重新生成候选。发布门只读取训练集与验证集，测试集与确认集不参与候选选择。

## 配置项

| 参数 | 默认 | 说明 |
|---|---|---|
| `--seed` | `17` | 数据切分与采样种子 |
| `--rounds` | `2` | 搜索轮数 |
| `--budget` | `4` / `6` | 每轮候选评估预算 |
| `--embedding` | `tfidf` | `tfidf` 或 `nomic` |
| `--teacher-model` | `qwen3:1.7b` | 变异模型 |
| `--frontier` | `hybrid` | Pareto 前沿模式 |
