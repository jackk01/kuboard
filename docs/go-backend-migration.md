# Go 后端重构说明

本次重构采用“并行后端、逐步切流”的方式，而不是直接删除 Django 后端。原因是当前后端承担了 IAM、SQLite 元数据、Kubernetes API 网关、审计和 Web Terminal 等多个职责，其中 Pod Exec / Terminal 属于高风险流式能力，适合最后迁移。

## 目录

- `backend/`：现有 Django 后端，继续作为稳定回退实现。
- `backend-go/`：新增 Go 后端，复用前端 `/api/v1/...` 协议和现有 SQLite 表。

## 已迁移模块

- 系统健康检查与 Redis/SQLite readiness。
- Token 认证，兼容 DRF `authtoken_token`。
- Django PBKDF2 密码校验与新用户密码生成。
- Fernet 兼容加解密，复用已有 kubeconfig 密文。
- 用户、用户组、RBAC 映射、审计事件和流式会话索引。
- 集群导入、kubeconfig 校验、健康检查、Discovery 和能力同步。
- Kubernetes 资源列表、详情、新建、Server-Side Apply、删除、Watch、Logs 与 Events。

## 未完成模块

- Pod Exec 命令执行。
- Web Terminal 输入/输出/resize 的 WebSocket/SPDY 流式通道。
- 完整 SelfSubjectRulesReview / SelfSubjectAccessReview 权限矩阵。
- OpenAPI v3 / CRD schema 精确解析；当前 Go 后端先返回基础 inferred schema。

## API 兼容策略

Go 后端优先保持响应字段与 `frontend/src/types.ts` 对齐：

- UUID 对外返回带连字符格式，SQLite 内部仍兼容 Django `char(32)`。
- JSON 字段继续存储为 SQLite `text` + JSON 内容。
- Token 使用 `Authorization: Token <key>`。
- kubeconfig 加密兼容 Python `cryptography.fernet.Fernet` 派生方式。

## 建议切流顺序

1. 本地以 `SQLITE_PATH=../backend/db.sqlite3 go run ./cmd/kuboard` 启动 Go 后端。
2. 前端 `VITE_API_BASE_URL` 指向 Go 后端，验证登录、集群列表和资源浏览。
3. 生产环境先只切只读/低风险接口：health、me、dashboard、clusters list/detail、audit list。
4. 再切资源写入接口：create/apply/delete。
5. 最后实现并切换 exec/terminal 流式能力。
