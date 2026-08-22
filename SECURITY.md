# 安全策略

## 报告漏洞

**请不要通过公开 issue 报告安全漏洞。**

请使用 GitHub 的
[Private vulnerability reporting](https://github.com/S0ra-ai/Aletheia-onto/security/advisories/new)
提交。若该入口不可用，请通过仓库所有者的 GitHub 主页联系。

报告时请尽量包含：

- 受影响的版本或提交
- 复现步骤，最好是最小复现用例
- 影响评估：能读到什么、能改到什么、需要什么前置权限

我们会在 5 个工作日内确认收到，并在评估后告知修复计划。

## 支持范围

项目尚未发布正式版本，目前只维护 `main` 分支。

## 本项目的高风险区域

报告与审计时，以下区域优先关注：

**规则表达式沙箱**（`backend/ontology_platform/semantic_kernel.py`）
规则表达式来自用户输入，在 AST 白名单沙箱中求值。
允许的节点类型见 `ALLOWED_AST_NODES`，允许的函数见 `ALLOWED_RULE_FUNCTIONS`
（`sum`／`len`／`count`／`any`／`all`），dunder 属性访问被拒绝。
**任何能突破该沙箱执行任意代码的构造都是高危漏洞。**

**认证与会话**（`backend/ontology_platform/auth.py`）
口令使用 PBKDF2-SHA256 加盐存储，令牌仅存摘要。
关注：令牌可预测性、会话固定、撤销与过期失效、改密后旧会话残留。

**能力授权**（`backend/ontology_platform/access_policy.py`）
集中式路由→能力策略表。未登记的路由默认仅管理员可访问。
关注：路径匹配能否被绕过（大小写、编码、尾斜杠、路径穿越）导致
低权限角色触达高权限端点。

**凭据脱敏**（`backend/ontology_platform/credentials.py`）
数据源连接串只隐藏密码段，API Key 仅返回首尾。
关注：任何仍会完整泄漏凭据的响应路径或日志路径。

**SQL 构造**（`backend/ontology_platform/adapters.py`、`database.py`）
平台会按用户配置的表名与列名查询遗留系统。
关注：表名或列名注入。

## 已知的安全相关限制

这些是当前设计的边界，**不是漏洞**，但部署时必须知道：

- `permission_policy.filter_expression` **现已生效**：向 `check_permission`
  传入 `instance_id` 时会在规则沙箱中求值，无法求值则拒绝访问。
  **但仍需注意**：不传 `instance_id` 时只做能力校验，返回的
  `filterApplied: False` 表示行级过滤未参与判断——调用方必须检查该字段。
- `workflow_transition.guard_expression` **现已生效**：transition 时求值，
  无法求值则阻止流转。
- `permission_policy` 现按 `(role_id, ontology_id, object_code)` 建索引。
  `ontology_id = 0` 表示通配，用于兼容既有单本体部署。
- **无多租户隔离。** 31 张表没有租户概念，一个部署实例服务一个组织。
- `ONTOLOGY_AUTH_DISABLED=1` 会关闭全部认证，使所有接口可匿名访问。
  仅限本地开发；启用时启动日志会打印警告。
- 未设置 `ONTOLOGY_ADMIN_PASSWORD` 时会生成随机管理员口令并打印在启动日志中，
  请在首次登录后修改。

## 部署建议

- 始终设置 `ONTOLOGY_ADMIN_PASSWORD`，不要依赖随机口令
- 通过 `ONTOLOGY_ALLOWED_ORIGINS` 收紧 CORS 来源，不要留默认值上生产
- 平台库连接串通过环境变量注入，不要写进代码或配置文件
- 接入遗留系统时使用只读账号，除非确实需要写回
- 生产环境不要设置 `ONTOLOGY_AUTH_DISABLED`
