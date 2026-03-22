# Kuboard 产品方案

## 1. 项目定位

Kuboard 的定位不是“单集群可视化工具”，而是“面向企业平台团队的 Kubernetes 多集群统一控制平面”。它需要同时满足以下三类诉求：

- 平台管理员：统一导入、纳管、审计多个 Kubernetes 集群
- 运维与 SRE：高效查看、排障、编辑、发布原生 Kubernetes 资源
- 开发与项目成员：在被授权的范围内，自助访问自己有权限的集群与命名空间资源

它应具备三个核心特征：

- 多集群统一视图：同一界面管理多个集群、多个云、多个环境
- 严格 Kubernetes 原生：资源语义、字段校验、权限判断、冲突处理尽量与原生 API 对齐
- 面向团队协作：多用户登录、RBAC、审计、权限可见性、操作留痕

## 2. 产品目标

### 2.1 业务目标

- 降低平台团队对多集群日常运维的认知成本
- 让开发、测试、运维在统一入口里完成资源浏览、编辑、排障
- 避免自定义抽象覆盖 Kubernetes 原生语义，减少学习成本和误操作
- 为后续 GitOps、策略治理、告警、插件生态预留扩展空间

### 2.2 产品目标

- 通过导入 kubeconfig 纳管任意兼容 Kubernetes API 的集群
- 提供通用资源浏览器，覆盖内置资源和 CRD
- 支持 YAML 编辑、表单编辑、Apply、Patch、Delete、Scale、Logs、Exec、Events、Watch
- 基于 Kubernetes Role / ClusterRole 实现多用户访问控制
- 前端界面现代化、亮眼但不过度装饰，适配桌面与中小屏

### 2.3 非目标

- V1 不直接承担集群创建和基础设施编排能力
- V1 不做完整 DevOps 平台，不把 CI/CD、制品库、Service Mesh 一次性塞进去
- V1 不做强绑定某一云厂商的专有资源运维台

## 3. 典型用户与权限模型

### 3.1 用户角色

- 平台超级管理员：导入集群、配置认证、维护系统级策略
- 平台管理员：管理租户、项目、用户组、集群接入策略
- 项目管理员：管理特定集群/命名空间下的成员访问和常用资源
- 开发者：浏览、编辑、发布自己有权限的应用资源
- 审计员：只读查看资源与操作日志

### 3.2 权限设计原则

- Kuboard 内部只负责登录、组织关系、界面能力控制与审计
- 集群资源访问的最终授权，优先交给 Kubernetes RBAC 决策
- Kuboard 前端显示什么按钮，后端是否放行某个请求，都要以 Kubernetes 权限探测结果为准
- 用户对资源的可见范围和可操作范围，必须能解释为“映射后的 Kubernetes Subject 是否拥有该权限”

## 4. 核心功能蓝图

### 4.1 集群接入与管理

- 通过 kubeconfig 导入集群
- 自动解析 clusters / users / contexts
- 检测 API Server 可达性、证书、版本、可用 API Group、OpenAPI、授权能力
- 展示集群健康状态、连接状态、版本、标签、环境属性
- 支持集群分组，如生产、预发、测试、边缘、区域

### 4.2 通用资源管理

- 资源树浏览：按 Cluster / Namespace / API Group / Kind 组织
- 通用列表页：支持搜索、标签过滤、字段列配置、批量只读操作
- 详情页：Metadata、Spec、Status、Events、关联资源、OwnerReferences
- YAML 编辑器：语法高亮、Schema 提示、Diff、Dry-run、Server-side Apply
- 表单编辑器：对常见资源提供结构化编辑，对 CRD 提供自动表单或 JSON Schema 渲染
- Watch 实时刷新：支持列表与详情实时变更流
- 关键治理资源优先适配：Role、RoleBinding、ClusterRole、ClusterRoleBinding、NetworkPolicy、ResourceQuota、LimitRange

### 4.3 工作负载与排障

- Deployment / StatefulSet / DaemonSet / Job / CronJob 快捷视图
- Pod 生命周期、容器状态、日志查看、事件查看
- Exec / Attach / Terminal
- 滚动重启、Scale、副本调整、镜像更新
- 常见问题诊断入口，如 CrashLoopBackOff、镜像拉取失败、调度失败

### 4.4 多用户与权限

- 支持本地账号、OIDC、LDAP 等登录方式
- 支持用户组、团队、项目空间
- 将 Kuboard 用户或用户组映射为 Kubernetes 用户名/组
- 基于 Kubernetes RBAC 进行资源级鉴权
- 操作前权限预校验，页面按权限动态收敛

### 4.5 审计与治理

- 登录审计
- 集群导入/更新/删除审计
- 资源读写审计
- 敏感操作二次确认
- Secret 默认脱敏展示
- 支持导出审计日志到外部系统
- Exec、Terminal、批量删除、权限变更等高风险操作需要单独审计分类

### 4.6 可观测与扩展

- 首页集群概览、资源概览、异常事件概览
- 支持 Prometheus 指标接入
- 支持插件机制，为特定 CRD 或运维流程扩展 UI
- 支持保存常用筛选视图、收藏资源、最近访问

## 5. 关键业务流程

### 5.1 集群导入流程

1. 平台管理员上传 kubeconfig
2. 后端执行安全校验、结构解析、凭证有效性验证
3. 后端探测集群版本、API 发现信息、OpenAPI、权限能力
4. 后端保存加密凭证与集群元数据
5. 管理员为该集群配置访问策略、用户组映射、默认可见范围

### 5.2 用户访问资源流程

1. 用户登录 Kuboard
2. 前端获取当前用户可见集群列表
3. 前端请求资源列表或详情
4. 后端根据用户映射出的 Kubernetes Subject 发起权限探测
5. 若允许，则以后端代表该用户访问集群 API 并返回结果
6. 若拒绝，则前端隐藏对应操作或返回权限不足信息

### 5.3 资源编辑流程

1. 用户打开 YAML / 表单编辑器
2. 前端获取资源当前版本和 Schema
3. 用户提交前先做本地校验
4. 后端执行 server-side dry-run
5. 通过后再执行 Server-Side Apply 或 Patch
6. 冲突时返回字段级冲突信息，引导用户合并

## 6. 对标产品与借鉴点

本项目可以借鉴行业成熟产品，但不建议简单拼装功能，而应抽取其设计原则。

### 6.1 Headlamp

借鉴点：

- UI 针对 Kubernetes 资源浏览进行了高信息密度但不压迫的布局
- 能根据用户的集群权限自适应功能可见性
- 具备插件化扩展能力，适合后续为特定 CRD 增强体验

不直接照搬的点：

- Kuboard 需要更强的多集群中心控制平面能力和审计能力

### 6.2 Rancher

借鉴点：

- 统一管理多云、多集群，强调减少配置漂移
- 把策略、治理、扩展视作平台的一等能力
- 强调“中心控制平面”而不是简单的单集群控制台

不直接照搬的点：

- Kuboard V1 不需要承载 Rancher 那么大的平台面，先聚焦资源管理与权限治理

### 6.3 KubeSphere

借鉴点：

- Host Cluster / Member Cluster 的中心控制面思维
- 多租户、用户同步、组件可插拔思路
- 多集群下的统一资源入口与项目管理模式

不直接照搬的点：

- Kuboard 不应强绑定自己的工作空间抽象去替代原生 Kubernetes 结构

### 6.4 Kubernetes Dashboard

借鉴点：

- 保持原生资源操作体验
- 默认最小权限思路是正确的
- 向导式创建与 YAML 上传能力对初期用户很友好

不直接照搬的点：

- Dashboard 更偏单集群官方 UI，Kuboard 需要补齐多集群、多用户和审计

### 6.5 Portainer

借鉴点：

- 通过平台代理统一访问后端集群的思路
- 用户粒度的 kubeconfig 导出能力，适合做“受控访问出口”

不直接照搬的点：

- Kuboard 的内核仍然要坚持 Kubernetes 原生语义，而不是泛容器平台抽象

## 7. Kuboard V1 建议范围

### 7.1 必做

- 登录认证与基础用户管理
- 通过 kubeconfig 导入多集群
- 集群概览与连接健康
- 通用资源浏览器
- YAML 编辑器
- Server-Side Apply / Patch / Delete / Scale
- Watch 实时刷新
- 基于 Kubernetes RBAC 的权限探测与 UI 收敛
- 审计日志
- 对 RBAC、NetworkPolicy、Quota 类资源提供明确的高优先级展示与编辑体验

### 7.2 建议做

- 日志查看
- Pod Exec
- 资源 Diff
- 常用工作负载快捷页
- 收藏与最近访问
- Prometheus 指标接入

### 7.3 后续演进

- 插件系统
- GitOps 联动
- 策略引擎与准入检查可视化
- 告警中心
- 受控 kubeconfig 导出
- 多集群应用分发

## 8. 重要补充事项

这些是需求里没有明确写出，但对项目成败非常关键的事项。

### 8.1 kubeconfig 导入安全

- kubeconfig 不是“纯配置文件”，可能包含 exec 类认证插件
- 对不可信 kubeconfig 必须做严格审查和限制
- 默认拒绝执行任意 `exec` 认证插件，除非管理员显式加入白名单
- 默认拒绝 `insecure-skip-tls-verify=true`，至少应高亮风险并要求确认
- kubeconfig、证书、token 必须加密存储

### 8.2 原生 API 一致性

- 不做“伪批量事务”承诺，因为 Kubernetes API 天生以单资源操作为核心
- 编辑器必须尊重 `resourceVersion`、字段管理、冲突语义
- 优先支持 Server-Side Apply、Dry-run、Field Validation

### 8.3 大规模集群性能

- 列表、Watch、Schema 获取都必须可缓存、可复用、可限流
- 大集群下要避免前端一次性渲染海量资源
- Watch 流应由服务端汇聚复用，而不是每个浏览器单独打爆 API Server

### 8.4 可观测与排障

- 平台自身必须输出结构化日志、指标、追踪与审计
- 集群接入失败、权限异常、OpenAPI 获取失败、Watch 断流都要可诊断

### 8.5 扩展性

- 资源渲染器、详情页、快捷操作、导航都要预留插件点
- 内置资源和 CRD 要走同一套基础能力，不做两套系统

### 8.6 版本兼容与升级策略

- 需要明确支持的 Kubernetes 次版本矩阵，并在集群接入时标记兼容状态
- 对不同版本 API 差异做能力探测，而不是把所有功能写死
- Kuboard 自身升级要提供数据库备份、配置备份和回滚指引

### 8.7 Secret 与二进制数据处理

- Secret 默认只展示 key、类型、大小和更新时间，不默认回显明文
- 对 `data` 和 `binaryData` 要分别支持查看、替换、下载和审计
- 涉及 Secret 编辑、下载、复制的行为要有更严格的权限和日志策略

### 8.8 长连接与危险操作治理

- Exec、Terminal、日志流、Watch 都需要连接超时、空闲回收和并发上限
- 高风险操作要支持二次确认、操作者身份留痕和可选审批扩展点
- 前端必须显式展示当前集群、命名空间与目标资源，降低误操作概率

### 8.9 SQLite 元数据边界

- SQLite 只保存 Kuboard 的系统元数据，不保存 Kubernetes 资源主数据
- 高频会话、缓存、队列、临时状态优先放 Redis，减轻 SQLite 写压力
- 审计明细建议支持外部落盘或日志系统，SQLite 更适合保存检索索引和关键摘要

### 8.10 备份与恢复

- 必须有定时备份 SQLite 数据文件、应用配置和密钥材料的机制
- 必须提供恢复演练流程，验证集群信息、用户映射、审计索引能否恢复
- 需要定义 RPO/RTO 目标，避免“看起来很轻量，恢复时却没有依据”

## 9. 成功指标

- 导入一个新集群可在 5 分钟内完成并通过健康校验
- 90% 以上常见 Kubernetes 资源可通过通用资源浏览器直接查看
- 常见发布和运维动作不需要离开 Kuboard 即可完成
- 权限不足时前后端表现一致，不出现“前端可点但后端必失败”的大量体验问题
- 单个大集群在常见列表场景下仍能稳定响应，平台自身具备可观测性和审计留痕
- SQLite 模式下系统元数据可稳定备份、恢复和升级，不因单点文件损坏导致平台不可用

## 10. 参考链接

- Kubernetes: Configure Access to Multiple Clusters  
  https://kubernetes.io/docs/tasks/access-application-cluster/configure-access-multiple-clusters/
- Kubernetes: Using RBAC Authorization  
  https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- Kubernetes: User Impersonation  
  https://kubernetes.io/docs/reference/access-authn-authz/user-impersonation/
- Kubernetes: API Concepts  
  https://kubernetes.io/docs/reference/using-api/api-concepts/
- Kubernetes: Server-Side Apply  
  https://kubernetes.io/docs/reference/using-api/server-side-apply/
- Kubernetes: kubeconfig v1  
  https://kubernetes.io/docs/reference/config-api/kubeconfig.v1/
- Kubernetes: Deploy and Access the Dashboard  
  https://kubernetes.io/docs/tasks/access-application-cluster/web-ui-dashboard/
- Headlamp  
  https://headlamp.dev/
- Rancher Multi-Cluster Management  
  https://www.rancher.com/products/cluster-management
- KubeSphere Multi-cluster  
  https://kubesphere.io/multicluster/
- KubeSphere Multi-cluster Docs  
  https://www.kubesphere.io/docs/v3.4/faq/multi-cluster-management/manage-multi-cluster/
- Portainer Kubeconfig  
  https://docs.portainer.io/sts/user/kubernetes/kubeconfig
