# ADR-0003 领域词汇不内置，运行时从本体与蓝图派生

- 状态：Accepted
- 日期：2026-08-21

## Context

平台早期为了让演示效果好看，在自己的源码里内置了业务词汇：

- `ontology.py` 的 `NAME_HINTS` 把 `contract` 映射为「合同」、
  `equipment` 映射为「设备」，共 8 条；`ATTRIBUTE_HINTS` 有 38 条字段名映射
- 实例识别、默认对象在找不到目标时回退到硬编码的 `"contract"`
- 智能体角色是写死的 `contract-expert` / `equipment-expert`
- `contract_documents.py` 有 14 个合同专用函数

效果是：接入合同或设备系统时演示很漂亮，接入任何第三个行业时，
生成的本体草案标签是原始列名，实例识别失败会莫名其妙地去找 `contract` 对象，
智能体自称合同专家。

更根本的问题：**内置词表会让平台在定位上退化为单行业产品。**
每来一个新行业就往词表里加一批词，最终变成一个词表维护项目，
而不是一个语义内核。

## Decision

平台代码零内置行业词汇。业务术语只通过两条途径进入系统：

1. **元数据扫描** —— 从遗留系统的表名、列名、注释、外键中提取
2. **行业蓝图** —— 用户可导入的词汇与规则模板包

以下能力全部改为运行时派生：

| 能力 | 派生来源 |
|---|---|
| 对象识别 | 当前本体的对象编码与标签 |
| 默认对象 | 关系度最高的对象，而非固定编码 |
| 实例识别 | 来源表的列命名约定（`*_no`、`*_code`、`id`） |
| 智能体角色 | 已接入的领域，提示词由该领域本体实时渲染 |
| 权限策略 | 本体中实际存在的业务对象 |
| 草案标签 | 已注册蓝图贡献的标签集合 |

并用**静态守卫测试**防止回归：扫描 `backend/ontology_platform/*.py` 的
可执行代码行（跳过 docstring 与注释），断言不出现
`"contract"`、`"customer"`、`"payment_plan"`、`"invoice"`、
`"work_order"`、`"equipment"` 这些曾经的硬编码回退值。
`industry_blueprints.py` 与 `sample_data.py` 豁免——那里正是词汇应该在的地方。

## Alternatives considered

**保留内置词表作为「默认蓝图」。** 拒绝理由：技术上等价于内置，
因为它仍然在平台代码里，仍然会随平台升级而变化，用户无法替换。
改成可导入的蓝图后，同样的内容存在于用户可管理的数据里。

**用大模型实时翻译列名。** 拒绝理由：未配置模型密钥时能力就消失；
且翻译结果不稳定，同一列名两次生成不同标签会破坏本体的可复现性。
蓝图是确定性的。

**只在演示数据里内置，生产路径不用。** 拒绝理由：这正是原状态，
区分不住——`sample_data.py` 的词汇通过 `NAME_HINTS` 泄漏到了生产路径。

## Consequences

正面：接入任何行业的行为一致，没有「一等公民行业」。平台可以诚实地
声称领域中立，且这个声称有测试支撑而非口头承诺。

负面：没有导入蓝图时，生成的草案标签就是列名本身（`total_amount`
而不是「合同总金额」）。用户必须导入蓝图或手工改标签才能得到好名字。
这是可接受的：难看但正确，好过漂亮但只对两个行业正确。

负面：删除了 `contract_documents.py` 的 14 个合同专用函数。
这些函数当时未被任何调用方使用，但如果未来需要合同领域的深度解析，
应该以蓝图或插件形式回来，而不是回到平台核心。

## 证据

`tests/test_domain_neutrality.py`（25 个测试）。使用宠物诊疗（veterinary
clinic）领域——平台完全不认识、也没有内置任何相关词汇的领域——验证：

- `test_unknown_domain_is_modelled_with_its_own_labels`
  建模产出「宠物主／宠物／诊疗记录」而非原始列名
- `test_default_object_is_the_most_connected_not_a_fixed_code`
  默认对象由关系度决定
- `test_questions_route_to_domain_objects_end_to_end`
  问答全链路路由到该领域对象
- `test_identifier_columns_recognise_conventions_not_industry_names`
  实例识别靠命名约定
- `test_platform_modules_contain_no_industry_vocabulary`（静态守卫）
- `test_agent_module_has_no_hardcoded_personas`（静态守卫）
