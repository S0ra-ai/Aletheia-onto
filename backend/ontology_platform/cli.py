"""The `aletheia` command line: the shortest path from install to a first verdict.

ROADMAP stage F. The gap this closes is not convenience. A framework whose first
successful run requires reading a README, writing a bootstrap script and guessing a
connection string has a first-day abandonment problem -- which is exactly the failure
ADR-0001 records for the "pure library" distribution shape.

```
aletheia init            # create the platform database
aletheia connect <uri>   # register a legacy system and scan its metadata
aletheia model <id>      # generate an ontology draft from that metadata
aletheia assess <obj> <id>   # produce a verdict, with its reasons
aletheia demo            # all of the above against a built-in sample system
aletheia serve           # run the HTTP API
aletheia doctor          # report what is configured and what is missing
```

## Design decisions

**No subcommand mutates a published ontology.** Publishing is a reviewed governance
action with a release gate; a CLI flag that bypassed it would make the gate advisory.
`aletheia publish` therefore refuses without `--force` and reports what the gate found.

**Every command prints what it did to which database.** A CLI that silently defaults to
a database in a temp directory produces the worst kind of confusion -- work that appears
to succeed and then cannot be found.

**`serve` fails with an actionable message when FastAPI is absent** rather than an
ImportError traceback, because the web layer is an optional extra and a missing extra is
a configuration problem, not a bug.

Stability: the command surface is experimental until 1.0 (ADR-0007).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

PROGRAM = "aletheia"


def _print(payload: Any) -> None:
    """Emit a result as JSON.

    JSON rather than a formatted table: the first thing anyone does with a CLI in a B2B
    integration is pipe it into something else, and a table would have to be reparsed.
    """
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _fail(message: str) -> int:
    print(f"{PROGRAM}: {message}", file=sys.stderr)
    return 1


def _silent(command: Any, args: argparse.Namespace) -> int:
    """Run a subcommand without letting it print.

    Used so a composite command emits exactly one JSON document. Suppressing output is
    better than asking the caller to split a stream of concatenated documents, which is
    fiddly enough that everyone gets it slightly wrong.
    """
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        return int(command(args))


def _platform_db(args: argparse.Namespace) -> Any:
    from .database import DEFAULT_PLATFORM_DB

    return Path(args.platform_db) if args.platform_db else DEFAULT_PLATFORM_DB


def cmd_init(args: argparse.Namespace) -> int:
    """Create the platform database and the bootstrap administrator."""
    from .auth import ensure_bootstrap_admin
    from .database import connect, initialize_platform_db

    platform_db = _platform_db(args)
    initialize_platform_db(platform_db)
    # The optional feature schemas are created here too, so a CLI-initialised database
    # is not missing tables that only the HTTP server's startup would have created.
    with connect(platform_db) as conn:
        _init_optional_schemas(conn)
    credentials = ensure_bootstrap_admin(platform_db)
    _print(
        {
            "platformDb": str(platform_db),
            "bootstrapAdmin": credentials,
            "note": "首次登录后请立即修改该密码；它只在本次初始化时输出一次。",
        }
    )
    return 0


def _init_optional_schemas(conn: Any) -> None:
    """Create every feature schema the HTTP startup would create.

    Enumerated rather than discovered, because a schema silently missing from a
    CLI-initialised database shows up much later as "this feature returns nothing".
    """
    from .agent_roles import init_agent_role_schema
    from .aggregation import init_aggregate_schema
    from .auth import init_auth_schema
    from .conversations import init_conversation_schema
    from .events import init_event_schema
    from .knowledge_documents import init_knowledge_schema
    from .temporal import init_temporal_schema
    from .workflow_permission import init_workflow_and_permission_schema

    for initialise in (
        init_workflow_and_permission_schema,
        init_auth_schema,
        init_agent_role_schema,
        init_knowledge_schema,
        init_aggregate_schema,
        init_conversation_schema,
        init_event_schema,
        init_temporal_schema,
    ):
        initialise(conn)


def cmd_connect(args: argparse.Namespace) -> int:
    """Register a legacy system and scan its metadata."""
    from .metadata import register_data_source, scan_data_source

    platform_db = _platform_db(args)
    source = register_data_source(
        platform_db,
        args.name,
        args.type,
        args.uri,
        domain=args.domain,
    )
    scan = scan_data_source(platform_db, source.id)
    _print(
        {
            "platformDb": str(platform_db),
            "dataSourceId": source.id,
            "name": source.name,
            "scanned": scan,
            "next": f"{PROGRAM} model {source.id}",
        }
    )
    return 0


def cmd_model(args: argparse.Namespace) -> int:
    """Generate an ontology draft from a scanned data source."""
    from .ontology import generate_ontology_draft

    platform_db = _platform_db(args)
    draft = generate_ontology_draft(
        platform_db,
        args.data_source_id,
        name=args.name or None,
        domain=args.domain or None,
        blueprint_id=args.blueprint or None,
    )
    ontology = draft.get("ontology") or draft
    _print(
        {
            "platformDb": str(platform_db),
            "ontologyId": ontology.get("id"),
            "objects": [item["code"] for item in draft.get("objects", [])],
            "ruleCount": len(draft.get("rules", [])),
            "status": ontology.get("status"),
            "note": "草案中的映射为 pending，需审核后才能发布。",
        }
    )
    return 0


def cmd_assess(args: argparse.Namespace) -> int:
    """Produce a verdict for one instance."""
    from .semantic_kernel import assess_instance

    platform_db = _platform_db(args)
    result = assess_instance(
        platform_db, args.ontology_id, args.object_code, args.instance_id, as_of=args.as_of or None
    )
    if args.verbose:
        _print(result)
        return 0
    # The default view is the verdict and the rules that failed. The full evidence is
    # in the decision record; printing all of it by default would bury the answer.
    failed = [rule for rule in result.get("ruleResults", []) if not rule.get("passed")]
    _print(
        {
            "decision": result.get("decision", {}).get("status"),
            # Echoed so a past-tense verdict cannot be mistaken for one about now.
            "asOf": result.get("semanticKernel", {}).get("asOf") or None,
            "recommendation": result.get("decision", {}).get("recommendation"),
            "failedRules": [
                {
                    "code": rule.get("ruleCode"),
                    "severity": rule.get("severity"),
                    "reason": rule.get("naturalLanguage") or rule.get("explanation"),
                    "inheritedFrom": rule.get("inheritedFrom") or None,
                    "evaluationError": rule.get("evaluationError") or None,
                }
                for rule in failed
            ],
            "ruleCount": len(result.get("ruleResults", [])),
        }
    )
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    """Publish an ontology version, subject to the release gate."""
    from .governance import publish_ontology

    platform_db = _platform_db(args)
    try:
        result = publish_ontology(platform_db, args.ontology_id, args.actor, force=args.force)
    except ValueError as error:
        # The gate's findings are the useful output here, not a traceback.
        return _fail(f"发布被拒绝：{error}\n如确认要覆盖门禁，请显式传 --force（会写入审计）。")
    _print(result)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Run the whole loop against a built-in sample system."""
    from .metadata import register_data_source, register_source_api, scan_data_source
    from .ontology import generate_ontology_draft
    from .sample_data import DEFAULT_SAMPLE_DB, create_contract_sample_db
    from .semantic_kernel import assess_instance
    from .vocabulary import default_object_code_for_ontology

    platform_db = _platform_db(args)
    if not args.quiet:
        cmd_init(args)
    else:
        # The demo prints one document per step by default, which is what a person
        # wants. A caller parsing the output wants exactly one, so `--quiet` suppresses
        # the init report rather than making the consumer split the stream.
        _silent(cmd_init, args)
    sample_path = create_contract_sample_db(Path(args.sample_db) if args.sample_db else DEFAULT_SAMPLE_DB)
    source = register_data_source(
        platform_db,
        "合同管理样例系统",
        "sqlite",
        str(sample_path),
        domain="合同管理",
        system_category="database+api",
    )
    register_source_api(
        platform_db,
        source.id,
        "submit_contract",
        "提交合同审批",
        "POST",
        "/contracts/{id}/submit",
        "contract.submit_for_approval",
    )
    scan_data_source(platform_db, source.id)
    draft = generate_ontology_draft(platform_db, source.id)
    ontology_id = (draft.get("ontology") or draft)["id"]
    # The object code comes from the blueprint lexicon (ADR-0003), so it is discovered
    # rather than assumed -- hardcoding "contract" would break on a renamed blueprint.
    object_code = default_object_code_for_ontology(platform_db, ontology_id)
    verdict = assess_instance(platform_db, ontology_id, object_code, "1")
    _print(
        {
            "platformDb": str(platform_db),
            "sampleDb": str(sample_path),
            "ontologyId": ontology_id,
            "objectCode": object_code,
            "decision": verdict.get("decision", {}).get("status"),
            "next": f"{PROGRAM} serve  # 打开 http://127.0.0.1:8000/docs",
        }
    )
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Run the HTTP API."""
    try:
        import uvicorn
    except ImportError:
        # A missing optional extra is a configuration problem, so it gets an
        # instruction rather than a traceback.
        return _fail("HTTP 层需要 web extra，请先安装：pip install 'aletheia-onto[web]'")
    uvicorn.run("ontology_platform.api:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Report what is configured and what is missing.

    Written for the case where something does not work: it names the platform database
    in use, which optional extras are installed, and which registered extension points
    are active -- the three things that account for most "it does nothing" reports.
    """
    from .adapters import supported_source_types
    from .automation import supported_executor_schemes
    from .database import get_platform_config
    from .generic_sql_adapter import describe_bundled_sql_sources, register_bundled_sql_sources
    from .instance_resolver import supported_resolver_kinds
    from .rule_sandbox import allowed_rule_function_names
    from .schema import dialect_of
    from .sql_dialects import known_dialects

    platform_db = _platform_db(args)
    config = get_platform_config()
    extras = {}
    for extra, module in (("web", "fastapi"), ("postgresql", "psycopg"), ("mysql", "pymysql"), ("documents", "docx")):
        try:
            __import__(module)
            extras[extra] = "installed"
        except ImportError:
            extras[extra] = "missing"

    # Activating first means the report reflects what a deployment can actually reach, not
    # merely what the catalogue lists.
    register_bundled_sql_sources(replace=True)
    report: dict[str, Any] = {
        "version": _version(),
        "platformDb": str(platform_db),
        "platformDbType": config.db_type,
        "extras": extras,
        "sourceTypes": list(supported_source_types()),
        # Declared but inactive SQL sources, with the driver each needs. "Why is Oracle not
        # in the list" is the most common question here, so it is answered rather than
        # requiring someone to read the source.
        "declaredSqlSources": [
            {
                "sourceType": item["sourceType"],
                "driver": item["driverModule"],
                "available": item["driverAvailable"],
                "hint": "" if item["driverAvailable"] else item["installHint"],
            }
            for item in describe_bundled_sql_sources()
        ],
        "sqlDialects": list(known_dialects()),
        "writebackSchemes": list(supported_executor_schemes()),
        "resolverKinds": list(supported_resolver_kinds()),
        "ruleFunctions": sorted(allowed_rule_function_names()),
    }
    try:
        from .database import connect

        with connect(platform_db) as conn:
            report["dialect"] = dialect_of(conn)
            report["initialised"] = True
    except Exception as error:
        report["initialised"] = False
        report["error"] = str(error)
        report["hint"] = f"平台库尚未初始化，请先运行 {PROGRAM} init"
    _print(report)
    return 0


def _version() -> str:
    from . import __version__

    return __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Aletheia：为传统业务系统安装可核验的业务语义内核",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
    # Global, because every subcommand acts on a platform database and threading it
    # through each one separately would let two commands disagree about which.
    parser.add_argument(
        "--platform-db",
        default="",
        help="平台库路径（默认：源码 checkout 下为 ./data，已安装包为 ~/.aletheia，可用 ONTOLOGY_DATA_DIR 覆盖目录）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="初始化平台库并创建引导管理员")
    init.set_defaults(func=cmd_init)

    connect_cmd = sub.add_parser("connect", help="登记传统业务系统并扫描元数据")
    connect_cmd.add_argument("uri", help="连接串，如 sqlite:///path.db 或 postgresql://...")
    connect_cmd.add_argument("--name", default="传统业务系统", help="系统名称")
    connect_cmd.add_argument("--type", default="sqlite", help="数据源类型：sqlite/postgresql/mysql 或已注册类型")
    connect_cmd.add_argument("--domain", default="", help="业务域，用于推断行业蓝图")
    connect_cmd.set_defaults(func=cmd_connect)

    model = sub.add_parser("model", help="从已扫描的数据源生成本体草案")
    model.add_argument("data_source_id", type=int)
    model.add_argument("--name", default="", help="本体名称")
    model.add_argument("--domain", default="", help="业务域")
    model.add_argument("--blueprint", default="", help="指定行业蓝图 id")
    model.set_defaults(func=cmd_model)

    assess = sub.add_parser("assess", help="对一个实例产出判定")
    assess.add_argument("ontology_id", type=int)
    assess.add_argument("object_code")
    assess.add_argument("instance_id")
    assess.add_argument("--verbose", action="store_true", help="输出完整证据而非仅判定与未通过规则")
    assess.add_argument(
        "--as-of",
        default="",
        help="按该时间点的历史值判定（YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS），用于回答「当时是否合规」",
    )
    assess.set_defaults(func=cmd_assess)

    publish = sub.add_parser("publish", help="发布本体版本（受发布门禁约束）")
    publish.add_argument("ontology_id", type=int)
    publish.add_argument("--actor", default="cli", help="记入审计的操作者")
    publish.add_argument("--force", action="store_true", help="覆盖发布门禁，未通过项数会写入审计")
    publish.set_defaults(func=cmd_publish)

    demo = sub.add_parser("demo", help="用内置样例系统跑通完整闭环")
    demo.add_argument("--sample-db", default="", help="样例业务库输出路径")
    demo.add_argument(
        "--quiet",
        action="store_true",
        help="只输出最终结果文档（便于脚本解析；初始化产生的引导口令仍会写入日志）",
    )
    demo.set_defaults(func=cmd_demo)

    serve = sub.add_parser("serve", help="启动 HTTP 服务")
    serve.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true", help="开发模式自动重载")
    serve.set_defaults(func=cmd_serve)

    doctor = sub.add_parser("doctor", help="报告当前配置、已安装 extra 与已注册扩展点")
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:  # pragma: no cover - interactive
        return 130
    except Exception as error:
        # A stack trace is the wrong output for an operator running a command; the
        # message is. `--verbose`-style tracebacks belong to the library's callers.
        return _fail(str(error))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
