# 子规格 08：可视化编排客户端

## 目标

实现画布拖拽、节点配置、连线、DSL 校验、工作流保存、发布与运行事件展示。

## 验收

- 浏览器可完成创建、校验、保存、发布和运行一次工作流。
- 校验错误能定位到节点或边。
- 运行事件按节点顺序显示。

## 实现

`frontend/index.html` 提供零依赖画布，支持：

- 添加 `start` / `llm` / `tool` / `agent` / `end` 节点。
- 拖动节点、点击建立连线、编辑节点 JSON 配置。
- 导出 DSL，校验开始节点数量与结束节点存在性。
- 保存到 `POST /workflows`，发布到 `POST /workflows/{id}/publish`。
- 通过 `POST /workflows/{id}/run/stream` 读取 SSE 事件并逐条展示。

后端在保存与发布时执行完整 DSL 校验，前端基础校验用于快速反馈。

## 配置

API 基址位于 `frontend/app.js` 顶部的 `API` 常量，默认 `http://127.0.0.1:8080`。
