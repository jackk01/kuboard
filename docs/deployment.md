# Kuboard 部署与上线前验收

## 1. 当前部署边界

Kuboard 当前生产形态按 SQLite 的真实能力设计为：

- 单实例 `backend`
- 单实例 `worker`
- 单实例 `redis`
- 单实例 `frontend`

这不是多副本高可用架构。原因很直接：

- SQLite 不适合跨节点共享写
- Kuboard 当前元数据、审计索引和会话索引仍落在 SQLite
- 因此现阶段更合理的是单机或单节点部署，把稳定性放在第一位

## 2. 交付工件

- [docker-compose.prod.yml](/Users/longyang/Desktop/code/kuboard/docker-compose.prod.yml)
- [deploy/helm/kuboard/Chart.yaml](/Users/longyang/Desktop/code/kuboard/deploy/helm/kuboard/Chart.yaml)
- [backend/Dockerfile](/Users/longyang/Desktop/code/kuboard/backend/Dockerfile)
- [frontend/Dockerfile](/Users/longyang/Desktop/code/kuboard/frontend/Dockerfile)
- [backend/docker/entrypoint.sh](/Users/longyang/Desktop/code/kuboard/backend/docker/entrypoint.sh)
- [frontend/nginx/default.conf.template](/Users/longyang/Desktop/code/kuboard/frontend/nginx/default.conf.template)
- [scripts/release_check.sh](/Users/longyang/Desktop/code/kuboard/scripts/release_check.sh)
- [scripts/sqlite_backup.py](/Users/longyang/Desktop/code/kuboard/scripts/sqlite_backup.py)
- [scripts/sqlite_restore.py](/Users/longyang/Desktop/code/kuboard/scripts/sqlite_restore.py)
- [deploy/.env.production.example](/Users/longyang/Desktop/code/kuboard/deploy/.env.production.example)
- [.github/workflows/release-check.yml](/Users/longyang/Desktop/code/kuboard/.github/workflows/release-check.yml)

## 3. 部署步骤

1. 复制生产环境变量模板

```bash
cp deploy/.env.production.example .env
```

2. 至少修改以下变量

- `DJANGO_SECRET_KEY`
- `KUBOARD_ENCRYPTION_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `CORS_ALLOWED_ORIGINS`
- `KUBOARD_ADMIN_EMAIL`
- `KUBOARD_ADMIN_PASSWORD`

3. 启动生产服务

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

4. 查看状态

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend
```

## 3.1 Helm 部署

如果运行环境已经是 Kubernetes，可以改用 Helm chart：

```bash
helm lint deploy/helm/kuboard
helm install kuboard deploy/helm/kuboard \
  --namespace kuboard \
  --create-namespace
```

建议至少覆盖以下值：

- `backend.secretKey`
- `backend.encryptionKey`
- `backend.admin.email`
- `backend.admin.password`
- `backend.allowedHosts`
- `backend.csrfTrustedOrigins`
- `backend.corsAllowedOrigins`
- `ingress.enabled`
- `ingress.hosts`

说明：

- Chart 当前按 SQLite 模式强制单控制面副本，`backend.replicas` 必须为 `1`
- `backend` 与 `worker` 运行在同一个 `controlplane` Pod 内，共享 SQLite PVC
- `frontend`、`redis` 独立部署，便于后续替换和扩展

## 4. 健康检查与探针

Liveness：

- `GET /api/v1/health`

Readiness：

- `GET /api/v1/health/ready`

Readiness 会同时检查：

- SQLite 连接
- Redis 读写回路

## 5. 后端启动行为

[backend/docker/entrypoint.sh](/Users/longyang/Desktop/code/kuboard/backend/docker/entrypoint.sh) 启动时会自动执行：

1. `python manage.py migrate --noinput`
2. `python manage.py init_sqlite`
3. `python manage.py collectstatic --noinput`
4. 如果启用 `KUBOARD_BOOTSTRAP_ADMIN=true`，执行管理员初始化
5. 按角色启动 `uvicorn` 或 `celery worker`

## 6. SQLite 维护建议

启动时会执行 `init_sqlite`，自动设置：

- `journal_mode=WAL`
- `synchronous=NORMAL`
- `foreign_keys=ON`
- `busy_timeout=5000`
- `wal_autocheckpoint=1000`

日常备份建议：

```bash
python3 ./scripts/sqlite_backup.py ./backups
```

恢复示例：

```bash
python3 ./scripts/sqlite_restore.py ./backups/kuboard-YYYYMMDD-HHMMSS.sqlite3 ./backend/db.sqlite3 --force
```

建议在上线后至少落实：

- 每日定时备份
- 发布前手动备份
- 恢复演练
- 恢复前停止 Kuboard 服务，避免覆盖运行中的 SQLite 文件

## 7. 上线前验收清单

必须通过的自动化检查：

```bash
sh ./scripts/release_check.sh
```

如果使用 Helm 部署，还应额外确认：

- `helm lint deploy/helm/kuboard` 通过
- `helm template kuboard deploy/helm/kuboard` 可正常渲染

CI 侧当前也会自动执行：

- `scripts/release_check.sh`
- 后端与前端 Docker 镜像构建校验
- Helm chart 打包与渲染产物归档

必须人工确认的项目：

- 登录页、总览页、集群页、Explorer、审计页、设置页可正常打开
- `/api/v1/health` 返回 `ok`
- `/api/v1/health/ready` 返回 `ok`
- 默认管理员可登录
- 集群导入表单可提交
- 资源列表、详情、创建、Apply、Delete 页面交互无明显报错
- Logs / Exec / Terminal UI 可正常进入
- 审计页可看到关键动作

## 8. 当前未覆盖的上线前工作

当前还没有在真实 Kubernetes 集群上做端到端联调，因此上线前最后一段仍建议补做：

- 真实 kubeconfig 导入验证
- Discovery 和权限探测验证
- Apply / Delete / Watch / Logs / Exec / Terminal 实机验证
- 大资源列表与长日志场景验证

如果你下一步继续，我会直接进入“真实环境联调与上线问题清单收敛”。  
