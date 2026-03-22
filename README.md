# Kuboard

Kuboard 是一款面向企业与平台团队的 Kubernetes 多集群管理面板，采用前后端分离架构，前端基于 Vue 3，后端基于 Python Django。当前方案默认使用 SQLite 作为系统元数据存储，配合 Redis 承担缓存、会话和队列能力。它的目标不是再造一套“只支持少数资源”的管理台，而是做一个严格遵循 Kubernetes API 规范、可扩展、可审计、适合团队协作的统一控制平面。

当前仓库已经完成一版可运行 MVP，并补齐了部署、打包和上线前验收所需的基础工件：

- `backend/`：Django + DRF + Celery + SQLite + Redis 控制平面
- `frontend/`：Vue 3 + Vite + Pinia + Vue Router 控制台
- `docker-compose.yml`：本地开发 Redis
- `docker-compose.prod.yml`：单机生产部署编排
- `deploy/helm/kuboard/`：单节点 Kubernetes / Helm 部署 chart
- `scripts/release_check.sh`：发布前回归脚本
- `scripts/sqlite_backup.py`：SQLite 备份脚本
- `scripts/sqlite_restore.py`：SQLite 恢复脚本
- `.github/workflows/release-check.yml`：CI 回归、镜像构建与 Helm 打包

说明：

- 架构设计文档里推荐 Django 5.x，但当前初始化代码为了适配本机镜像源，实际落地为 Django 4.2 LTS
- 代码层已经尽量保持向 Django 5.x 平滑升级的兼容写法

## 文档索引

- [产品方案](./docs/product-solution.md)
- [系统架构](./docs/architecture.md)
- [前端体验与 UI 设计](./docs/frontend-design.md)
- [实施路线图](./docs/roadmap.md)
- [部署与上线前验收](./docs/deployment.md)

## 设计原则

1. 严格遵循 Kubernetes API 规范，优先使用原生能力而不是“魔改”语义。
2. 所有集群访问统一收口到后端控制平面，前端不直连集群。
3. 资源浏览、编辑、Apply、Watch、权限判断都要兼容内置资源与 CRD。
4. 多用户访问优先基于 Kubernetes RBAC 与用户身份映射，而不是在 Kuboard 内部重新发明一套脱节权限体系。
5. 优先保证性能、可观测性、可审计性和可靠性，再叠加高级能力。
6. 系统元数据尽量轻量存储，本地状态少而精，资源真相始终以 Kubernetes 集群为准。

## 当前产出范围

- 明确产品定位、用户角色、功能边界与 V1 范围
- 完成前后端分离的多集群控制台 MVP
- 支持集群导入、Discovery、资源查看/新建/编辑/删除
- 支持 Watch、Pod Logs、Pod Exec、Web Terminal
- 支持基于 Kubernetes RBAC 的权限探测和 impersonation 映射
- 支持本地用户、用户组、审计日志、Schema 预览和基础表单编辑
- 补充 SQLite 模式下的生产部署、备份、并发与恢复边界

## 工程结构

- `backend/`：后端服务
- `backend/apps/iam`：用户、登录、Token 认证、用户组
- `backend/apps/clusters`：集群导入、kubeconfig 校验、加密存储、健康状态
- `backend/apps/audit`：审计模型与接口
- `backend/apps/rbac_bridge`：用户到 Kubernetes Subject 的映射模型
- `backend/apps/k8s_gateway`：Kubernetes 统一资源访问层
- `backend/apps/streams`：Logs / Exec / Terminal 会话管理
- `backend/apps/system_settings`：健康检查、仪表盘摘要、系统配置
- `frontend/`：控制台前端

## 快速开始

1. 启动 Redis

```bash
docker compose up -d redis
```

2. 初始化后端环境

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py bootstrap_kuboard
```

3. 启动后端

```bash
cd backend
.venv/bin/python manage.py runserver
```

4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

默认管理员账号：

- 邮箱：`admin@kuboard.local`
- 密码：`admin123456`

## 生产部署

这版生产方案按 SQLite 的真实边界设计为“单实例后端 + 单实例 Celery Worker + Redis + 前端 Nginx”。

1. 准备生产环境变量

```bash
cp deploy/.env.production.example .env
```

2. 按实际域名、密钥和管理员密码修改 `.env`

3. 启动生产编排

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

4. 检查健康状态

```bash
curl http://127.0.0.1:8080/api/v1/health
curl http://127.0.0.1:8080/api/v1/health/ready
```

说明：

- 前端默认对外暴露在 `8080`
- API 通过前端 Nginx 反向代理到后端
- SQLite 数据默认存放在 Docker volume `sqlite-data`
- 后端启动时会自动执行 `migrate`、`init_sqlite`、`collectstatic`
- 如果 `KUBOARD_BOOTSTRAP_ADMIN=true`，还会自动初始化管理员

## Helm 部署

如果你的运行环境本身就是 Kubernetes，也可以直接使用 Helm chart 做“单节点 SQLite 模式”部署：

```bash
helm lint deploy/helm/kuboard
helm install kuboard deploy/helm/kuboard \
  --namespace kuboard \
  --create-namespace
```

说明：

- 该 chart 按 SQLite 边界固定为单控制面副本，`backend.replicas` 不允许大于 `1`
- `frontend`、`redis` 与 `controlplane` 分离部署
- `controlplane` Pod 内同时运行 `backend` 和 `worker`，共享同一块 SQLite PVC
- 上线前请先用 `values.yaml` 或 `--set` 替换默认域名、密钥和管理员密码

## 发布前验收

运行统一检查脚本：

```bash
sh ./scripts/release_check.sh
```

它会依次执行：

- Django 测试
- `manage.py check`
- 前端类型检查
- 前端生产构建
- `docker-compose.prod.yml` 配置校验（如果本机安装了 Docker）
- Helm chart `lint` 与模板渲染校验（如果本机安装了 Helm）

SQLite 备份：

```bash
python3 ./scripts/sqlite_backup.py
```

SQLite 恢复：

```bash
python3 ./scripts/sqlite_restore.py ./backups/kuboard-YYYYMMDD-HHMMSS.sqlite3 /path/to/db.sqlite3 --force
```

恢复前请先停止 Kuboard 进程或容器，避免覆盖运行中的数据库文件。

## 研究依据

本方案在 2026-03-21 完成初版整理，参考了 Kubernetes 官方文档以及同类产品公开资料，重点包括：

- Kubernetes 官方文档中的 kubeconfig、多集群访问、RBAC、API Concepts、Server-Side Apply、Impersonation、Dashboard
- Headlamp 的可扩展 UI 与基于 RBAC 的适配思路
- Rancher 的统一多集群控制平面思路
- KubeSphere 的中心控制平面与多租户、多集群模型
- Portainer 的平台代理与受控 kubeconfig 思路
