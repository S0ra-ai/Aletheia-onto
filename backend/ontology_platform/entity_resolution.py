"""跨源实体消解：两个源里的哪两行是同一个业务实例。

ROADMAP 通用性清单上最后一项结构性空白。一个业务对象此前只能绑一个数据源，
于是这一类需求完全无法表达——而它在 B 端是常态：

    客户主数据在 CRM，合同在 ERP，两边都有「客户」，但主键不同
    设备台账在资产系统，运行数据在 SCADA，靠设备编号对应
    人员在 HR，权限在 AD，靠工号对应

## 为什么这不是「加个连接」就能解决

跨源判定必须回答一个前置问题：**CRM 的第 42 行和 ERP 的第 7 行是同一个客户吗。**

那个判断本身会进入判定链。若它不可核验，基于它的每个结论都不可解释——
「为什么这份合同被阻断」的答案会变成「因为我们认为这两行是同一个客户」，
而没人能审阅「我们认为」。

这是本模块存在的全部理由：**把匹配变成声明，而不是推断。**

## 匹配是声明的，绝不是模糊的

| 做法 | 是否采用 | 理由 |
|---|:--:|---|
| 声明「CRM.customer.tax_id ↔ ERP.client.taxpayer_no」 | ✅ | 可审阅、可导出、每次得出同一结果 |
| 字符串相似度、编辑距离、模糊匹配 | ❌ | 阈值变一点，判定结论就变；无法解释 |
| 机器学习实体链接 | ❌ | 同上，且无法说出「为什么这两行是同一个」 |
| 多键组合（税号 + 名称都相等） | ✅ | 仍是精确相等，只是条件更严 |

这与关系语义（ADR-0012）、CSV 不推断外键（ADR-0015）是同一条原则：
**结构必须是声明的**。从巧合或相似度推出的对应关系，其上的判定无法解释。

## 一对多与冲突是错误，不是需要挑一个

跨源匹配最危险的失败不是找不到，而是**找到了多个**。
若 ERP 里有两行税号相同，平台**拒绝**而不是挑第一行——
挑一行会让判定作用在一条任意选中的记录上，而结果看起来完全正常。

同理，两侧对同名字段给出不同值时（CRM 说信用额度 100 万，ERP 说 50 万），
**冲突被记录并上报**，而不是让某一侧静默胜出。规则若引用该字段，
读到的是标记为冲突的值，而 fail-closed 会把它变成「未通过 + 原因」。

## 主源决定身份

一个跨源对象有且只有一个**主源**：实例 id 来自它，`list_ids()` 列的是它的键。
否则同一个业务实例会有两个 token，而判定记录、审计行与 URL 里会各存一个。

Stability: experimental (ADR-0007)。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

from .context import PlatformDb
from .database import connect
from .instance_resolver import ResolverError, validate_identifier

logger = logging.getLogger(__name__)

# 一次跨源解析要读多少行才放弃。跨源匹配在每次判定时发生，
# 无界扫描会让每个判定退化成全表扫描。触顶会上报而非静默截断。
MAX_MATCH_CANDIDATES = 5_000

# 同名字段两侧取值不同时的处理策略。
# `conflict` 是默认：静默让某一侧胜出会让判定依据不可解释。
CONFLICT_MARK = "conflict"
PREFER_PRIMARY = "prefer_primary"
PREFER_SECONDARY = "prefer_secondary"
MERGE_STRATEGIES = (CONFLICT_MARK, PREFER_PRIMARY, PREFER_SECONDARY)


class EntityResolutionError(ValueError):
    """跨源匹配声明或求解无效时抛出。"""


def _identifier(name: str, *, what: str) -> str:
    """校验进入 SQL 文本的标识符。

    与解析器共用同一处校验，只有一个地方需要审计 SQL 标识符安全性；
    错误重新包装成本模块的类型，调用方只需处理一种异常。
    """
    try:
        return validate_identifier(name, what=what)
    except ResolverError as error:
        raise EntityResolutionError(str(error)) from error


@dataclass(frozen=True)
class MatchKey:
    """一对用于判定「同一实例」的列。

    两侧列名可以不同——这正是跨源的常态：CRM 叫 `tax_id`，ERP 叫 `taxpayer_no`。
    """

    primary_column: str
    secondary_column: str
    # 比较前是否规范化。仅做**确定性**的规范化：去空白、统一大小写。
    # 不做同义词替换、不做拼写纠正——那些会让匹配结果随词表变化。
    normalize: bool = True

    def validate(self) -> "MatchKey":
        _identifier(self.primary_column, what="主源匹配列名")
        _identifier(self.secondary_column, what="副源匹配列名")
        return self

    def normalized(self, value: Any) -> str:
        """比较用的取值形式。

        统一转字符串：跨源时同一个业务键常有不同的存储类型
        （CRM 存 varchar，ERP 存 bigint），按原类型比较会一个都匹配不上。
        """
        if value is None:
            return ""
        text = str(value)
        return " ".join(text.split()).casefold() if self.normalize else text

    def to_json(self) -> dict[str, Any]:
        return {
            "primaryColumn": self.primary_column,
            "secondaryColumn": self.secondary_column,
            "normalize": self.normalize,
        }


@dataclass
class CrossSourceLink:
    """一条跨源对应声明：主源的某个对象如何对应到副源的某张表。

    存为本体上的数据而非代码。理由与 ADR-0011 相同：只以 Python callable
    存在的匹配规则无法被审阅、无法版本化、也无法随语义资产导出——
    而它恰恰是判定链上最需要被审阅的一环。
    """

    name: str
    # 主源侧：本体中的业务对象。实例身份来自这一侧。
    primary_object_code: str
    # 副源侧：另一个数据源里的表。
    secondary_data_source_id: int
    secondary_table: str
    # 判定「同一实例」的列对。多个键为 AND：全部相等才算同一实例。
    match_keys: Sequence[MatchKey] = ()
    # 副源字段挂载前缀。为空则直接合并到记录里，同名字段按 merge_strategy 处理。
    prefix: str = ""
    merge_strategy: str = CONFLICT_MARK
    # 副源匹配到多行时是否拒绝。默认拒绝：见模块文档。
    require_unique: bool = True
    description: str = ""

    def validate(self) -> "CrossSourceLink":
        if not self.name or not self.name.isidentifier():
            raise EntityResolutionError(f"跨源对应名称必须是合法标识符: {self.name!r}")
        if not self.primary_object_code:
            raise EntityResolutionError(f"{self.name}: 必须指定主源业务对象")
        if self.secondary_data_source_id <= 0:
            raise EntityResolutionError(f"{self.name}: 必须指定副源数据源 id")
        _identifier(self.secondary_table, what="副源表名")
        if not self.match_keys:
            raise EntityResolutionError(
                f"{self.name}: 必须声明至少一个匹配列对。"
                "跨源判定会把「这两行是同一实例」写进判定链，因此它必须是声明的，不能是推断的。"
            )
        for key in self.match_keys:
            key.validate()
        strategy = (self.merge_strategy or CONFLICT_MARK).strip().lower()
        if strategy not in MERGE_STRATEGIES:
            raise EntityResolutionError(
                f"{self.name}: 不支持的冲突策略 {self.merge_strategy!r}。可选: {'、'.join(MERGE_STRATEGIES)}"
            )
        self.merge_strategy = strategy
        if self.prefix:
            _identifier(self.prefix, what="副源字段前缀")
        return self

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "primaryObjectCode": self.primary_object_code,
            "secondaryDataSourceId": self.secondary_data_source_id,
            "secondaryTable": self.secondary_table,
            "matchKeys": [key.to_json() for key in self.match_keys],
            "prefix": self.prefix,
            "mergeStrategy": self.merge_strategy,
            "requireUnique": self.require_unique,
            "description": self.description,
        }

    @classmethod
    def from_row(cls, row: Any) -> "CrossSourceLink":
        try:
            keys = json.loads(row["match_keys"] or "[]")
        except (TypeError, ValueError):
            keys = []
        return cls(
            name=row["name"],
            primary_object_code=row["primary_object_code"],
            secondary_data_source_id=int(row["secondary_data_source_id"]),
            secondary_table=row["secondary_table"],
            match_keys=tuple(
                MatchKey(
                    primary_column=str(item.get("primaryColumn") or ""),
                    secondary_column=str(item.get("secondaryColumn") or ""),
                    normalize=bool(item.get("normalize", True)),
                )
                for item in keys
                if isinstance(item, dict)
            ),
            prefix=row["prefix"] or "",
            merge_strategy=row["merge_strategy"] or CONFLICT_MARK,
            require_unique=bool(row["require_unique"]),
            description=row["description"] or "",
        )

    def describe(self) -> str:
        """可读的对应说明，用于解释判定依据。

        引用了跨源字段的判定必须能说出「同一实例」是**按什么**判定的，
        否则那个数字来自哪一行就无从追溯。
        """
        conditions = " 且 ".join(
            f"主源.{key.primary_column} = {self.secondary_table}.{key.secondary_column}" for key in self.match_keys
        )
        return f"{self.name}: {self.primary_object_code} ↔ 数据源#{self.secondary_data_source_id}.{self.secondary_table} where {conditions}"


LINK_TABLE = "cross_source_link"

LINK_SCHEMA: tuple[dict[str, str], ...] = (
    {
        "sqlite": """
        create table if not exists cross_source_link (
            id integer primary key autoincrement,
            ontology_id integer not null references ontology(id),
            name text not null,
            primary_object_code text not null,
            secondary_data_source_id integer not null references data_source(id),
            secondary_table text not null,
            match_keys text not null default '[]',
            prefix text not null default '',
            merge_strategy text not null default 'conflict',
            require_unique integer not null default 1,
            description text not null default '',
            created_at text not null default current_timestamp,
            unique(ontology_id, name)
        )""",
        "postgresql": """
        create table if not exists cross_source_link (
            id serial primary key,
            ontology_id integer not null references ontology(id),
            name text not null,
            primary_object_code text not null,
            secondary_data_source_id integer not null references data_source(id),
            secondary_table text not null,
            match_keys text not null default '[]',
            prefix text not null default '',
            merge_strategy text not null default 'conflict',
            require_unique boolean not null default true,
            description text not null default '',
            created_at timestamp not null default current_timestamp,
            unique(ontology_id, name)
        )""",
        "mysql": """
        create table if not exists cross_source_link (
            id integer primary key auto_increment,
            ontology_id integer not null,
            name varchar(255) not null,
            primary_object_code varchar(255) not null,
            secondary_data_source_id integer not null,
            secondary_table varchar(255) not null,
            match_keys text,
            prefix varchar(255) not null default '',
            merge_strategy varchar(50) not null default 'conflict',
            require_unique tinyint not null default 1,
            description text,
            created_at datetime not null default current_timestamp,
            unique key uniq_cross_source_link (ontology_id, name)
        )""",
    },
)


def _schema_bundle() -> Any:
    from .schema import SchemaBundle

    return SchemaBundle(name="entity_resolution", tables=LINK_SCHEMA, table_names=(LINK_TABLE,))


def init_entity_resolution_schema(conn: Any) -> None:
    """建表。幂等——每次启动都会执行。"""
    _schema_bundle().apply(conn)


def entity_resolution_tables_exist(conn: Any) -> bool:
    """跨源对应是否可用。

    表不存在意味着该特性未配置，必须读作「没有跨源对应」而非报错。
    走目录探测而非捕获异常：PostgreSQL 上一条失败语句会中止整个事务（ADR-0004）。
    """
    return _schema_bundle().has_tables(conn)


def declare_cross_source_link(
    platform_db: PlatformDb,
    ontology_id: int,
    link: CrossSourceLink,
    *,
    actor: str = "system",
) -> dict[str, Any]:
    """声明一条跨源对应。

    入库前校验，因此不合法的声明在此处被拒绝，而不是在某次判定中才暴露。
    已发布本体不可修改。
    """
    link.validate()
    with connect(platform_db) as conn:
        if not entity_resolution_tables_exist(conn):
            raise EntityResolutionError("跨源对应表尚未创建，请先运行 init_entity_resolution_schema()。")
        ontology = conn.execute("select status from ontology where id = ?", (ontology_id,)).fetchone()
        if ontology is None:
            raise EntityResolutionError(f"本体不存在: {ontology_id}")
        if ontology["status"] == "published":
            raise EntityResolutionError("已发布本体不可修改跨源对应，请派生新版本。")
        if (
            conn.execute(
                "select id from business_object where ontology_id = ? and code = ?",
                (ontology_id, link.primary_object_code),
            ).fetchone()
            is None
        ):
            raise EntityResolutionError(f"主源业务对象不存在: {link.primary_object_code}")
        if conn.execute("select id from data_source where id = ?", (link.secondary_data_source_id,)).fetchone() is None:
            raise EntityResolutionError(f"副源数据源不存在: {link.secondary_data_source_id}")

        payload = (
            link.primary_object_code,
            link.secondary_data_source_id,
            link.secondary_table,
            json.dumps([key.to_json() for key in link.match_keys], ensure_ascii=False),
            link.prefix,
            link.merge_strategy,
            1 if link.require_unique else 0,
            link.description,
        )
        existing = conn.execute(
            f"select id from {LINK_TABLE} where ontology_id = ? and name = ?",
            (ontology_id, link.name),
        ).fetchone()
        if existing is not None:
            conn.execute(
                f"""
                update {LINK_TABLE}
                set primary_object_code = ?, secondary_data_source_id = ?, secondary_table = ?,
                    match_keys = ?, prefix = ?, merge_strategy = ?, require_unique = ?, description = ?
                where id = ?
                """,
                (*payload, int(existing["id"])),
            )
        else:
            conn.execute(
                f"""
                insert into {LINK_TABLE}
                    (ontology_id, name, primary_object_code, secondary_data_source_id, secondary_table,
                     match_keys, prefix, merge_strategy, require_unique, description)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ontology_id, link.name, *payload),
            )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "declare_cross_source_link",
                LINK_TABLE,
                f"{link.primary_object_code}.{link.name}",
                json.dumps(link.to_json(), ensure_ascii=False),
            ),
        )
    return {**link.to_json(), "definition": link.describe()}


def load_links(conn: Any, ontology_id: int, primary_object_code: str = "") -> list[CrossSourceLink]:
    """某个对象（或整个本体）的跨源对应声明。

    不合法的存量声明会被跳过并记日志：它会让引用跨源字段的规则 fail-closed，
    那是安全的方向。
    """
    if not entity_resolution_tables_exist(conn):
        return []
    clauses = ["ontology_id = ?"]
    params: list[Any] = [ontology_id]
    if primary_object_code:
        clauses.append("primary_object_code = ?")
        params.append(primary_object_code)
    rows = conn.execute(
        f"select * from {LINK_TABLE} where {' and '.join(clauses)} order by name",
        tuple(params),
    ).fetchall()
    links = []
    for row in rows:
        try:
            links.append(CrossSourceLink.from_row(row).validate())
        except EntityResolutionError as error:
            logger.warning("跨源对应 %s 不合法，已跳过: %s", row["name"], error)
    return links


def list_cross_source_links(
    platform_db: PlatformDb, ontology_id: int, primary_object_code: str = ""
) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        links = load_links(conn, ontology_id, primary_object_code)
    return [{**link.to_json(), "definition": link.describe()} for link in links]


@dataclass
class MatchResult:
    """一次跨源匹配的结果，附带足以解释判定的细节。"""

    link_name: str
    matched: bool
    definition: str
    fields: dict[str, Any] = field(default_factory=dict)
    # 同名字段两侧取值不同。记录而非静默取一侧：见模块文档。
    conflicts: dict[str, Any] = field(default_factory=dict)
    candidate_count: int = 0
    truncated: bool = False
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "linkName": self.link_name,
            "matched": self.matched,
            "definition": self.definition,
            "fields": self.fields,
            "conflicts": self.conflicts,
            "candidateCount": self.candidate_count,
            "truncated": self.truncated,
            "error": self.error,
        }


class ConflictingValue:
    """两侧取值不同的字段。

    刻意**不是** str 或 float 的子类：跨源冲突不该能参与比较。
    规则引用它时会抛 TypeError，而 fail-closed 把它变成「未通过 + 原因」——
    这正是应有的结果，因为没人能说清该用哪一侧的值（ADR-0002）。
    """

    __slots__ = ("column", "primary", "secondary")

    def __init__(self, column: str, primary: Any, secondary: Any):
        self.column = column
        self.primary = primary
        self.secondary = secondary

    def __repr__(self) -> str:
        return f"<跨源冲突 {self.column}: 主源={self.primary!r} 副源={self.secondary!r}>"

    def _refuse(self, *_args: Any) -> Any:
        raise TypeError(
            f"字段 {self.column} 在两个数据源中取值不同（主源={self.primary!r}，副源={self.secondary!r}），"
            "无法参与比较。请在跨源对应中声明冲突策略，或修正源数据。"
        )

    # 任何比较都拒绝，而不是选一侧。选一侧会让判定悄悄基于一个没人确认过的值。
    __eq__ = _refuse
    __ne__ = _refuse
    __lt__ = _refuse
    __le__ = _refuse
    __gt__ = _refuse
    __ge__ = _refuse
    __hash__ = None  # type: ignore[assignment]


def resolve_cross_source(
    link: CrossSourceLink,
    primary_record: dict[str, Any],
    secondary_runtime: Any,
) -> MatchResult:
    """按声明把主源记录对应到副源的一行。

    通过适配器逐行读取并在内存中匹配，而不是下推 join——跨源本来就无法下推，
    两侧可能是不同的数据库产品，甚至一侧是 CSV 或 REST。
    """
    definition = link.describe()
    # 主源缺任一匹配键时，「同一实例」这个判断无从成立。
    # 报错而非匹配全部行：后者会静默地把一个实例对应到任意一行。
    missing = [key.primary_column for key in link.match_keys if primary_record.get(key.primary_column) is None]
    if missing:
        return MatchResult(
            link_name=link.name,
            matched=False,
            definition=definition,
            error=f"主源记录缺少匹配键取值: {'、'.join(missing)}，无法判定是否为同一实例",
        )

    first = link.match_keys[0]
    try:
        rows = secondary_runtime.fetch_related_many(
            link.secondary_table, first.secondary_column, primary_record[first.primary_column]
        )
    except Exception as error:
        return MatchResult(
            link_name=link.name,
            matched=False,
            definition=definition,
            error=f"读取副源失败: {error}",
        )

    truncated = len(rows) > MAX_MATCH_CANDIDATES
    if truncated:
        logger.warning("跨源对应 %s 候选行超过 %s，已截断", link.name, MAX_MATCH_CANDIDATES)
        rows = rows[:MAX_MATCH_CANDIDATES]

    # 首个键已由数据源过滤，其余键在内存里逐一比对（AND 语义）。
    matches = [
        row
        for row in rows
        if all(
            key.normalized(row.get(key.secondary_column)) == key.normalized(primary_record.get(key.primary_column))
            for key in link.match_keys
        )
    ]

    if not matches:
        return MatchResult(
            link_name=link.name,
            matched=False,
            definition=definition,
            candidate_count=len(rows),
            truncated=truncated,
        )
    if len(matches) > 1 and link.require_unique:
        # 最危险的失败：找到多个。挑第一行会让判定作用在任意选中的记录上，
        # 而结果看起来完全正常。
        return MatchResult(
            link_name=link.name,
            matched=False,
            definition=definition,
            candidate_count=len(matches),
            truncated=truncated,
            error=(
                f"副源中有 {len(matches)} 行同时满足匹配条件，无法确定是同一实例。"
                "请补充匹配键使其唯一，或在源数据中消除重复。"
            ),
        )

    secondary = matches[0]
    fields, conflicts = _merge(link, primary_record, secondary)
    return MatchResult(
        link_name=link.name,
        matched=True,
        definition=definition,
        fields=fields,
        conflicts=conflicts,
        candidate_count=len(matches),
        truncated=truncated,
    )


def _merge(
    link: CrossSourceLink, primary_record: dict[str, Any], secondary: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """把副源字段并入上下文，并按策略处理同名冲突。"""
    fields: dict[str, Any] = {}
    conflicts: dict[str, Any] = {}
    for column, value in secondary.items():
        name = f"{link.prefix}_{column}" if link.prefix else column
        if link.prefix or column not in primary_record:
            fields[name] = value
            continue
        # 同名且无前缀：两侧都对这个字段有话说。
        if primary_record[column] == value:
            continue
        if link.merge_strategy == PREFER_PRIMARY:
            conflicts[column] = {"primary": primary_record[column], "secondary": value, "used": "primary"}
            continue
        if link.merge_strategy == PREFER_SECONDARY:
            fields[column] = value
            conflicts[column] = {"primary": primary_record[column], "secondary": value, "used": "secondary"}
            continue
        # 默认：标记冲突。规则引用它会抛 TypeError，由 fail-closed 转为
        # 「未通过 + 原因」——因为没人能说清该用哪一侧。
        fields[column] = ConflictingValue(column, primary_record[column], value)
        conflicts[column] = {"primary": primary_record[column], "secondary": value, "used": "none"}
    return fields, conflicts


def resolve_all(
    conn: Any,
    ontology_id: int,
    object_code: str,
    primary_record: dict[str, Any],
    runtime_for: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """解析某对象的全部跨源对应，返回 (待并入上下文的字段, 每条对应的结果)。

    `runtime_for(data_source_id)` 由调用方提供，因此本模块不需要知道适配器如何创建——
    那是内核的职责，而把它放进来会造成循环依赖。

    匹配失败的对应**不向上下文注入任何字段**：注入 None 会让
    `secondary.amount > 0` 求值为假，与真实的业务违规无法区分。缺席则触发
    NameError，由 fail-closed 转为「未通过 + 原因」（ADR-0002）。
    """
    links = load_links(conn, ontology_id, object_code)
    if not links:
        return {}, {}
    merged: dict[str, Any] = {}
    results: dict[str, Any] = {}
    for link in links:
        try:
            runtime_context = runtime_for(link.secondary_data_source_id)
        except Exception as error:
            results[link.name] = MatchResult(
                link_name=link.name,
                matched=False,
                definition=link.describe(),
                error=f"无法连接副源数据源 #{link.secondary_data_source_id}: {error}",
            ).as_dict()
            continue
        with runtime_context as secondary_runtime:
            result = resolve_cross_source(link, primary_record, secondary_runtime)
        results[link.name] = result.as_dict()
        if result.matched:
            merged.update(result.fields)
    return merged, results


def describe_cross_source(platform_db: PlatformDb, ontology_id: int) -> dict[str, Any]:
    """本体的全部跨源对应，供审阅与图谱视图使用。"""
    links = list_cross_source_links(platform_db, ontology_id)
    return {
        "links": links,
        "note": (
            "跨源匹配是声明的，不是推断的：相似度或机器学习实体链接会让判定结论随阈值变化，"
            "且无法解释「为什么这两行是同一个」。"
        ),
    }
