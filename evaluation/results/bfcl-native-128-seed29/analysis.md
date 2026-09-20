# BFCL-derived Frozen Replication · seed29

> 使用 BFCL v4 `simple_python_120..239` 的独立切分、自研 strict acceptable-value scorer；不是官方 BFCL 榜单分数。

## 冻结配置

- 开发 20、验证 40、预登记确认 60；搜索预算 4。
- 方法沿用 seed17 后冻结的随机、文本 GP/EI、失败反馈向量 warm-start + GP。
- `qwen3:1.7b` 通过 Ollama 原生 tools 执行，系统加入 `/no_think`，completion 上限 128；`qwen3:4b` 自动生成 8 个候选。
- 验证未严格提升时不运行确认集。

## 结果

| 方法 | 开发 | 验证 | 决策 |
|---|---:|---:|---|
| 固定基线 | 20/20（100%） | 37/40（92.5%） | 保留 |
| 固定随机 | 20/20（100%） | 37/40（92.5%） | 拒绝 |
| 文本 GP/EI | 20/20（100%） | 37/40（92.5%） | 拒绝 |
| 反馈 warm-start + GP | 20/20（100%） | 37/40（92.5%） | 拒绝 |

开发分数完全饱和，所有四候选子集都能命中开发最优，因此本切分无法区分 acquisition。失败反馈方法没有验证增益，发布门输出 `REJECTED_NO_VALIDATION_GAIN`；60 条确认样本保持封存。

结论是负面的：该切分不支持方法优势，同时说明后续基准需要按难度与失败类型分层，避免开发集天花板效应。

原始证据：[报告](report.json) · [发布决策](release.json)
