# AgentFlow Platform

企业级多 Agent 自进化工作流编排平台。当前采用“规格先行、分阶段实现”的方式推进。

## 当前状态

- 已完成主规格与子规格拆分
- 已完成 Python 核心 DAG 模块第一版：DSL 解析、拓扑排序、循环依赖检测、串行拓扑执行
- 下一步：WorkflowEngine 状态机、节点插件体系、HTTP API 与持久化

## 目录

- `specs/00-main-spec.md`：系统主规格
- `specs/01-09-*.md`：分领域子规格
- `backend/`：后端与工作流核心引擎
- `frontend/`：可视化编排器（后续实现）
- `deploy/`：本地开发与生产部署文件（后续实现）

## 运行核心测试

```powershell
cd D:\agent-workflow-platform\backend
python -m pytest -q
```
