# Kuboard 前端体验与 UI 设计

## 1. 设计目标

Kuboard 的前端不是传统“配置后台”的灰色面板，也不是花哨到影响效率的展示页。整体体验目标是：

- 现代、专业、亮眼，但不浮夸
- 信息密度高，但层级清晰
- 大量资源对象场景下仍然有秩序感
- 让用户快速理解自己正处于哪个集群、哪个命名空间、正在操作什么资源

## 2. 视觉方向

### 2.1 品牌气质

建议关键词：

- Cloud Native
- Precision
- Calm Energy
- Operational Confidence

### 2.2 视觉风格

推荐风格：

- 明亮主界面，不走纯白空洞风
- 用冷青色、深石墨色、少量电光绿做点缀
- 利用微渐变、轻阴影、柔和描边塑造层次
- 用空间和排版秩序体现高级感，而不是堆图标和颜色

### 2.3 字体建议

- 标题字体：`Space Grotesk`
- 正文字体：`Noto Sans SC`
- 等宽字体：`JetBrains Mono`

这样可以兼顾现代感、中文可读性和 YAML/命令展示的专业感。

## 3. 设计令牌建议

```css
:root {
  --kb-bg: #f4f7fb;
  --kb-surface: rgba(255, 255, 255, 0.82);
  --kb-surface-strong: #ffffff;
  --kb-border: rgba(15, 23, 42, 0.09);
  --kb-text: #102033;
  --kb-text-soft: #5a6b7d;
  --kb-primary: #0ea5a4;
  --kb-primary-deep: #0b7b7a;
  --kb-accent: #84cc16;
  --kb-danger: #e11d48;
  --kb-warning: #f59e0b;
  --kb-info: #2563eb;
  --kb-shadow: 0 18px 60px rgba(16, 32, 51, 0.08);
  --kb-radius-xl: 24px;
  --kb-radius-lg: 18px;
  --kb-radius-md: 12px;
}
```

## 4. 页面结构建议

### 4.1 总体布局

采用三段式桌面布局：

- 顶部全局栏：产品标识、全局搜索、告警、用户菜单
- 左侧主导航：总览、集群、资源浏览器、工作负载、审计、设置
- 主内容区：支持二级筛选条、数据卡片、列表、详情页与抽屉

### 4.2 核心布局原则

- 集群上下文必须始终显性可见
- 命名空间切换不能隐藏过深
- 资源对象列表与详情尽量在同一心智空间内切换
- 高频操作放在可预测位置，不做飘忽的交互

## 5. 核心页面设计

### 5.1 登录页

目标：

- 一眼体现这是“现代化云原生控制平面”
- 不做复杂插画，使用抽象拓扑线、网格光斑、渐变背景即可
- OIDC / LDAP / 本地登录入口清晰分组

### 5.2 首页总览

模块建议：

- 集群健康总览
- 最近异常事件
- 资源规模卡片
- 最近访问资源
- 审计动态

视觉建议：

- 顶部使用大号状态卡，强调“当前平台整体是否稳定”
- 用轻量动态图形展示资源趋势，不堆砌复杂图表

### 5.3 集群管理页

结构建议：

- 左侧为集群列表或分组树
- 右侧为集群详情与状态标签页
- 导入集群弹窗采用分步引导：上传 kubeconfig -> 安全检查 -> 连接验证 -> 权限验证 -> 完成

### 5.4 通用资源浏览器

这是最核心页面，建议采用：

- 顶部资源路径栏：Cluster / Namespace / Group / Version / Resource
- 左侧资源树
- 中间资源列表
- 右侧详情抽屉或分栏

列表能力：

- 自定义列
- 标签筛选
- 关键状态标签
- 大数据量虚拟滚动

详情能力：

- Overview
- YAML
- Events
- Related
- Managed Fields
- Permissions
- 对资源版本过期、字段冲突和只读模式给出显式提示

### 5.5 YAML 编辑器

设计重点：

- 使用 Monaco Editor
- 支持 schema 提示、语法错误标记、只读差异对比
- 提交区明确展示本次操作类型：Dry-run / Apply / Patch / Replace
- 冲突返回后，用字段级提示高亮问题区域
- Secret 默认脱敏，展示和复制敏感内容前需要二次确认

### 5.6 审计中心

不应该只是普通表格，建议：

- 支持按人、集群、命名空间、资源、动作、结果筛选
- 高危操作使用强提示色
- 点击可查看请求摘要、响应状态、trace id

## 6. 交互规范

### 6.1 反馈机制

- 页面级骨架屏替代整页 spinner
- 行级操作用按钮 loading，不阻塞全页
- 所有危险操作使用确认弹窗，并说明影响范围
- 异步任务返回 trace id，方便问题追踪
- 对流式连接中断、权限变化、资源已被他人修改给出即时反馈

### 6.2 状态表达

建议为 Kubernetes 常见状态做统一视觉映射：

- Running / Ready：绿色
- Progressing：青色
- Warning / Pending：橙色
- Failed / CrashLoopBackOff：红色
- Unknown：灰蓝色

### 6.3 动效

动效应克制且有意义：

- 页面初次进入时卡片轻微上浮
- 左侧导航切换有平滑过渡
- 抽屉和详情面板采用 180ms 到 220ms 的短动效
- 禁止满屏炫技动画

## 7. 组件体系建议

### 7.1 基础组件

- `KbPageHeader`
- `KbClusterBadge`
- `KbNamespaceSelect`
- `KbStatusPill`
- `KbStatCard`
- `KbResourceTable`
- `KbYamlEditor`
- `KbDiffViewer`
- `KbPermissionHint`
- `KbAuditTimeline`

### 7.2 通用复合组件

- 资源列表筛选工具栏
- 集群切换器
- 多维标签筛选器
- 事件时间线
- YAML / 表单模式切换器
- 批量操作确认框

### 7.3 图标策略

- 统一使用线性图标体系
- 资源图标不必每种都不同，可采用类别化抽象
- 高风险操作配合文本说明，避免只靠颜色和图标表达

## 8. 前端工程结构建议

```text
src/
  app/
  router/
  stores/
  layouts/
  modules/
    auth/
    dashboard/
    clusters/
    explorer/
    workloads/
    audit/
    settings/
  components/
  composables/
  services/
  styles/
  utils/
```

模块职责：

- `modules/*` 按业务域组织页面与局部状态
- `services/` 负责 API 封装与 SSE/WebSocket 接入
- `components/` 沉淀跨模块复用的基础与复合组件

## 9. 状态管理建议

Pinia 中建议拆分：

- `useSessionStore`
- `useClusterStore`
- `useDiscoveryStore`
- `useExplorerStore`
- `usePermissionStore`
- `useStreamStore`
- `usePreferenceStore`

原则：

- 会话和偏好长期持久化
- 资源列表状态按路由维度隔离
- Watch 数据尽量通过 stream store 统一分发

## 10. 前端性能要求

- 资源列表 5000+ 行仍保持可操作
- 列表页默认分页或虚拟滚动
- Schema、Discovery 做本地缓存与版本控制
- 日志与事件流按需订阅，不做全局常驻连接

## 11. 可访问性与国际化

### 11.1 可访问性

- 对比度满足基础可读性
- 所有关键操作支持键盘访问
- 状态不能只靠颜色表达
- 编辑器与表单控件提供错误说明文本

### 11.2 国际化

- 从第一天就做 i18n 结构
- 中文优先，但文案键值化
- 资源名、Kind、API Group 维持原生英文，不做强行翻译

## 12. 需要特别避免的问题

- 页面过白、信息分层不够，导致像“低配后台模板”
- 用太多卡片和阴影，造成视觉噪音
- 资源操作入口分散，用户不知道去哪里编辑
- Cluster / Namespace 上下文不明显，增加误操作风险
- 只做漂亮首页，却忽视高频资源页的体验

## 13. 最终前端体验关键词

- 清晰
- 稳定
- 原生
- 专业
- 可控
- 不臃肿

## 14. 参考链接

- Headlamp  
  https://headlamp.dev/
- Kubernetes Dashboard  
  https://kubernetes.io/docs/tasks/access-application-cluster/web-ui-dashboard/
- Rancher Cluster Management  
  https://www.rancher.com/products/cluster-management
- KubeSphere Multi-cluster  
  https://kubesphere.io/multicluster/
