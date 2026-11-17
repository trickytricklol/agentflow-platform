# 安全策略

## 报告安全问题

请通过仓库的私有安全报告渠道联系维护者，不要在公开 Issue 中粘贴 Token、凭证、用户数据或可利用细节。报告应包含受影响版本、复现条件、影响范围和最小复现步骤。

## 部署安全要求

- 生产环境必须设置 `AGENTFLOW_AUTH_ENABLED=1`，并通过 `AGENTFLOW_API_TOKEN` 注入强随机 Token；服务在缺少 Token 时拒绝启动。
- 在反向代理或负载均衡器终止 TLS，不要把明文 HTTP 暴露到公网。
- 将 `AGENTFLOW_CORS_ORIGINS` 收敛到控制台实际域名，不要在生产保留 `*`。
- 为 `AGENTFLOW_DATA_DIR` 使用持久化卷，并限制文件系统权限到运行用户。
- 通过 `AGENTFLOW_MAX_BODY_BYTES` 限制请求体大小；在网关层同时配置请求速率与连接超时。
- 定期轮换 API Token，并审计 `audit.jsonl` 中的发布、回滚、删除与运行记录。

## 依赖与容器

容器默认以 UID `10001` 运行，根文件系统只读，启用 `no-new-privileges` 与健康检查。升级基础镜像或依赖后应重新运行完整测试与容器冒烟检查。
