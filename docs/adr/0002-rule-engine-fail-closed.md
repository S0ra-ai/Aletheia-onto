# ADR-0002 规则引擎采用 fail-closed 语义

- 状态：Accepted
- 日期：2026-08-21

## Context

业务规则是写在数据库里的表达式，例如 `total_amount != null and total_amount > 0`，
在求值时绑定到某个业务实例的字段上。表达式引用的字段名来自遗留系统的列名。

遗留系统会变。列被改名、类型从 `varchar` 改成 `int`、字段被拆表搬走——
这些都会让原本能求值的表达式开始抛异常。

原实现捕获异常后把该规则记为「通过」（准确说：`passed=True` 保持不变，
异常只写进解释文本）。于是出现这样一条因果链：

1. DBA 把 `sign_date` 改名为 `signed_date`
2. 阻断级规则 `active_contract_signed` 开始抛异常
3. 该规则被记为通过
4. 操作预检放行
5. 自动化继续对未经核验的数据执行写回

而「检测结构漂移」恰恰是本项目对外声称的能力之一。上述链条意味着
漂移发生时，系统不但没有拦住，反而比正常情况更宽松。

## Decision

表达式无法求值时判为**未通过**，而不是跳过或视为通过。

- 阻断级（`blocking`）规则求值失败 → 决策状态 `blocked`
- 提示级（`warning`／`info`）规则求值失败 → 决策状态 `review`
- `inference_result` 的证据中记录 `skipped: true` 与 `evaluationError`，
  使「因为求值失败而未通过」与「因为业务条件不满足而未通过」可区分
- 解释文本明确说明这是求值失败，提示复核规则表达式或来源字段映射，
  而不是让操作员去改业务数据

配套措施：写入规则时静态校验表达式（`validate_rule_expression`），
不可执行的规则直接拒绝写入。没有这一步，fail-closed 会把一个笔误
变成该对象所有实例的永久阻断。生成的规则草案走同一道校验。

## Alternatives considered

**保持跳过语义，但记录告警。** 拒绝理由：告警会被忽略。判定结论是给
业务系统消费的，`allowed=true` 就是放行，旁边有没有告警不改变自动化行为。

**求值失败时抛异常，让整个研判失败。** 拒绝理由：一条坏规则会让该对象
完全无法研判，把局部问题放大成全局不可用。判为未通过既保守又保持可用。

**按严重级别区分：阻断级失败算未通过，提示级失败算通过。** 拒绝理由：
提示级规则的存在意义是提请人工复核；求值失败时正是最需要人看一眼的时候。

## Consequences

正面：结构漂移不再能静默放宽管控。误报方向是安全的——宁可拦住一次
本该放行的操作，不可放过一次本该拦住的。

负面：漂移发生时会出现一批「假阻断」，需要运维介入修表达式。
这是有意的取舍：让失败可见且必须处理，而不是可忽略。

已知未覆盖：`business_rule.depends_on` 字段存在但求值时不使用，
规则之间没有依赖关系，只按 `priority` 排序。因此一条规则求值失败
不会影响依赖它的其他规则——目前这些依赖关系本身就没有生效。

## 证据

`tests/test_rule_engine_safety.py`（17 个测试，11 个测试函数 + 参数化用例）：

- `test_unevaluable_rule_does_not_silently_pass` —— 阻断级求值失败 → `blocked`
- `test_unevaluable_warning_rule_routes_to_review` —— 提示级求值失败 → `review`
- `test_unparseable_rule_is_rejected_at_write_time`
- `test_sandbox_escaping_rule_is_rejected_at_write_time`
- `test_rule_expressions_cannot_reach_internal_attributes`（参数化）
- `test_rule_expressions_only_allow_whitelisted_functions`（参数化）
