# 框架成熟度

> 第三方要把它当作**框架**而不是**产品**来用，需要哪些东西——以及最后一节：
> 现在还缺什么。

返回 [中文 README](../README.zh-CN.md) · [能力矩阵](capabilities.zh-CN.md) · [已知限制](limitations.zh-CN.md)

## 这一页为什么存在

这里的其他每一份文档说的都是平台**能做什么**。这一页问的是另一个问题，
也是评估者真正带着的问题：**我能不能在它上面做东西，而不用 fork 它？**
这就是一个项目与一个框架的区别，而它不能被一张功能表回答——
一个功能齐全的产品，如果在改你需要的行为时必须去改别人的代码，它仍然不合格。

这一页对照的形态，是一个成熟的企业级开源框架：从包索引安装与升级、对着它生成项目骨架、
通过声明式扩展点扩展它、自己验证自己的实现、在治理之下运维它。
下面每一行都点名提供该能力的工件，以及把它钉住的那条检查——
因为**没人验证的能力只是一个主张**，而那些会变成主张的行，在
[还没有的部分](#还没有的部分)里。

**这一页自己也在被检查。** `tests/test_framework_readiness.py` 解析这些表，
一旦被引用的文件、测试或 CLI 命令不再存在就失败。一项悄悄消失的能力会带走它那一行，
而不是留下一句承诺。

## 采用

| 能力 | 住在哪里 | 由什么钉住 |
|---|---|---|
| 从包索引安装；升级不需要 fork | `pyproject.toml` | `tests/test_packaging.py` |
| 内核安装时**零**第三方依赖 | `pyproject.toml` | `tests/test_packaging.py` |
| 生成一个**依赖**平台的项目骨架，而不是复制它 | `backend/ontology_platform/scaffold.py` | `tests/test_scaffold.py` |
| 为**你自己的**本体生成带类型的模型——关系被类型化为它指向的对象 | `backend/ontology_platform/codegen.py` | `tests/test_codegen.py` |
| 控制台自己的响应类型由观测到的载荷描述，而不是手写 | `frontend/src/types/generated.ts` | `tests/test_generated_types.py` |
| 七个界面的行类型是那些声明的别名，而不是它们的副本 | `frontend/src/types/index.ts` | `tests/test_generated_types.py` |
| 一条从零到第一份判定、新人能照着走的路径 | `docs/quickstart.md` | `tests/test_documentation_links.py` |

## 扩展

| 能力 | 住在哪里 | 由什么钉住 |
|---|---|---|
| 注册数据源适配器，不碰平台代码 | `backend/ontology_platform/registry.py` | `tests/test_extension_registry.py` |
| 注册规则函数、路由策略、写回执行器 | `backend/ontology_platform/registry.py` | `tests/test_extension_registry.py` |
| **在交付之前验证你自己的实现**，不需要 pytest，也不需要这个仓库 | `backend/ontology_platform/conformance.py` | `tests/test_conformance_suites.py` |
| 一份模型提供方契约，它的失败路径必须由实现方提供一个实例来走 | `backend/ontology_platform/conformance.py` | `tests/test_conformance_suites.py` |
| 凭据无法借模型端点自己的错误文本漏进日志 | `backend/ontology_platform/model_client.py` | `tests/test_conformance_suites.py` |
| 平台自己的实现，跑的是第三方拿到的那同一份契约 | `backend/ontology_platform/conformance.py` | `tests/test_conformance_suites.py` |
| 一个不再被扩展的扩展点会大声失败，而不是静默失败 | `backend/ontology_platform/registry.py` | `tests/test_module_boundaries.py` |

## 建模

| 能力 | 住在哪里 | 由什么钉住 |
|---|---|---|
| 一个封闭的元模型——实体类型、数据属性、对象属性、公理、规则 | `backend/ontology_platform/ontology.py` | `tests/test_axioms.py` |
| 跨对象聚合，以及带单位的派生属性 | `backend/ontology_platform/aggregation.py` | `tests/test_cross_object_aggregation.py` |
| 属性级的时态有效性，以及回溯到某一刻的判定 | `backend/ontology_platform/temporal.py` | `tests/test_temporal_validity.py` |
| 导出别的工具能**解释**、而不只是能读的 OWL／RDFS 与 SHACL | `backend/ontology_platform/standard_vocabulary.py` | `tests/test_standard_vocabulary.py` |
| 每一份判定都带着约束它的规则、它的证据，以及一条持久化的决策记录 | `backend/ontology_platform/decisions.py` | `tests/test_answer_regression.py` |

## 治理

| 能力 | 住在哪里 | 由什么钉住 |
|---|---|---|
| 基于角色的访问，带对象级数据权限，且失败即拒绝 | `backend/ontology_platform/workflow_permission.py` | `tests/test_api_authentication.py` |
| 多租户隔离——一条忘了租户过滤的查询也越不过去 | `backend/ontology_platform/tenancy.py` | `tests/test_multi_tenancy.py` |
| 租户无法自己调高的配额 | `backend/ontology_platform/quotas.py` | `tests/test_tenant_quotas.py` |
| 每个业务对象一台状态机，守卫失败即拒绝 | `backend/ontology_platform/workflow_permission.py` | `tests/test_type_hierarchy_and_events.py` |
| 审计留痕，以及每一行上那个已认证的主体 | `backend/ontology_platform/auth.py` | `tests/test_audit_reports.py` |
| `--force` 跳不过的发布门禁 | `backend/ontology_platform/governance.py` | `tests/test_rule_engine_safety.py` |
| 控制台能用读者自己的语言说出的拒绝 | `backend/ontology_platform/error_codes.py` | `tests/test_error_codes.py` |

## 运维

| 能力 | 住在哪里 | 由什么钉住 |
|---|---|---|
| 一个会**拒绝**不安全配置的预检 | `backend/ontology_platform/deployment.py` | `tests/test_deployment_preflight.py` |
| `serve` 在配置不安全时拒绝绑定网络地址 | `backend/ontology_platform/cli.py` | `tests/test_deployment_preflight.py` |
| 以非 root 运行的容器产物 | `deploy/` | `tests/test_deployment_preflight.py` |
| 备份，以及一次保留退路的恢复 | `backend/ontology_platform/backup.py` | `tests/test_backup.py` |
| 完全可以不进库的密钥 | `backend/ontology_platform/credentials.py` | `tests/test_credential_protection.py` |
| 随客户数据增长的列表接受分页 | `backend/ontology_platform/pagination.py` | `tests/test_list_pagination.py` |
| 两张只追加的表按**游标**分页，于是读的中途插入的行不会被跳过 | `backend/ontology_platform/pagination.py` | `tests/test_list_pagination.py` |
| 调用方给的 limit 取不走整张表 | `backend/ontology_platform/config.py` | `tests/test_query_limit_clamping.py` |
| 双语控制台，靠用两种语言各读一遍来检查 | `frontend/src/i18n/locale.tsx` | `tests/test_ui_messages.py` |
| 双语 CLI，它的 `--help` 跟随它自己的解析器读到的那个标志 | `backend/ontology_platform/cli_messages.py` | `tests/test_cli_language.py` |
| 单元格在进程内被渲染并读取，于是空列会让单元测试失败，而不只是浏览器扫描 | `frontend/src/components/TableColumns.test.tsx` | `tests/test_frontend_type_agreement.py` |
| 一列横杠也算空——那个曾经掩盖了字段改名的兜底 | `scripts/ui_smoke.py` | `tests/test_ui_smoke_guards.py` |
| 每一条这样的豁免都写明理由，而过期的一条会让 CI 失败 | `scripts/ui_smoke.py` | `scripts/check_smoke_allowance.py` |

## 还没有的部分

上面那些行是**存在并且被检查**的能力。下面这些，是拿它跟一个成熟框架比较的评估者会去找、
却找不到的东西——写出来是为了让这个比较诚实，而不是好看。
每一条都有理由；没有一条对项目本身是意外。

| 缺口 | 它对第三方意味着什么 |
|---|---|
| **不是每一种响应类型都能生成，而这条界线是手工划的。** `generated.ts` 描述的是**线上格式**；对于客户端会做归一化的端点（`/permissions/policies`、`/tools`、`/data-sources/{id}/tables`），界面用的类型是归一化之后的形状，硬套生成声明等于删掉当初修掉空列缺陷所依赖的归一化函数。七个类型是生成声明的别名，其余是手写的。 | 在**归一化过的**端点上改字段名，由 `normalise.test.ts` 与生成文件分别发现，而不是由一个同时覆盖两者的机制发现。 |
| **组件测试覆盖七屏十三张表，不是所有页面。** `src/components/TableColumns.test.tsx` 渲染映射队列、规则列表、本体、数据源、权限的角色／策略／工具／待审执行四张表、治理的审计／调用／判定三张表，以及工作流列表和它的状态转换表，断言每一格都有内容；其余页面由浏览器扫描覆盖。 | 在没人写测试的页面上，空列仍然只能靠有人去跑一次浏览器扫描来发现。 |
| **仍有未翻译的拒绝语**，但少得多：101 条单句中文拒绝语里有 73 条带着控制台能翻译的码，面向扩展作者的那一批又在上面加了 108 条参数化的。剩下那些只在平台自己被装错时才触发。 | 当失败来自平台自己的组装时，英文控制台仍可能显示一句中文。 |
| **API 自己的句子在英文模式下仍是中文**——CLI 与控制台都是，它们对不认识的码回落到服务端那句。 | 故意的：载荷的形状与词汇是流水线解析的契约，翻译它会让同一个响应向不同调用方说不同的话。 |
