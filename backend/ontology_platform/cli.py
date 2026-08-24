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
aletheia verify          # run a conformance suite against an extension you registered
aletheia preflight       # refuse to deploy on production-unsafe configuration
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
    from .axioms import init_axiom_schema
    from .conversations import init_conversation_schema
    from .entity_resolution import init_entity_resolution_schema
    from .events import init_event_schema
    from .knowledge_documents import init_knowledge_schema
    from .quotas import init_quota_schema
    from .sso import init_sso_schema
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
        init_entity_resolution_schema,
        init_axiom_schema,
        init_quota_schema,
        init_sso_schema,
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


def cmd_export(args: argparse.Namespace) -> int:
    """Write an ontology out in platform or standard vocabulary.

    On the CLI rather than only over HTTP because the consumer of a standard export is
    usually a pipeline: hand the file to a SHACL validator, load it into a triple store,
    diff it against the previous version. Requiring a running server and a token to
    obtain a file makes that pipeline harder than it needs to be.
    """
    from .ontology import export_ontology_asset
    from .standard_vocabulary import STANDARD_EXPORT_FORMATS, export_standard_asset

    platform_db = _platform_db(args)
    try:
        if args.format in STANDARD_EXPORT_FORMATS:
            asset = export_standard_asset(platform_db, args.ontology_id, args.format)
        else:
            asset = export_ontology_asset(platform_db, args.ontology_id, args.format)
    except ValueError as error:
        return _fail(str(error))

    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(asset["content"], encoding="utf-8")
        _print({"format": args.format, "written": str(target), "mediaType": asset["mediaType"]})
    else:
        # To stdout, so the file can be piped into a validator without a temporary path.
        print(asset["content"], end="")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """Build an audit report for a period.

    On the CLI because a compliance report is usually produced on a schedule and filed,
    not read in a browser. Exiting non-zero when blocker-level findings exist makes it
    usable as a periodic check rather than only as a document.
    """
    from .audit_reports import AuditPeriodError, build_audit_report

    try:
        report = build_audit_report(_platform_db(args), start=args.start, end=args.end, ontology_id=args.ontology_id)
    except AuditPeriodError as error:
        return _fail(str(error))

    _print(report)
    # A report nobody reads is the normal outcome, so the exit code carries the verdict:
    # blocker findings mean something in the period cannot be signed off as-is.
    blockers = [item for item in report["findings"] if item["severity"] == "blocker"]
    return 1 if blockers else 0


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

    # Binding to anything other than loopback means the service is reachable from the
    # network, so the preflight blockers become exploitable rather than theoretical. Run it
    # by default and refuse -- nobody remembers to run a separate command, and the one time
    # it matters is the deployment where `ONTOLOGY_AUTH_DISABLED` was left on.
    exposed = args.host not in ("127.0.0.1", "localhost", "::1")
    if exposed and not args.skip_preflight:
        from .deployment import check_deployment

        report = check_deployment(platform_db=_platform_db(args), worker_count=1)
        if not report.ready:
            print(report.summary(), file=sys.stderr)
            return _fail(
                f"监听地址 {args.host} 可从网络访问，但部署前自检未通过。"
                "修复上述阻断项，或显式传 --skip-preflight（不建议）。"
            )
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


def cmd_verify(args: argparse.Namespace) -> int:
    """Run a conformance suite against a registered extension.

    The point of shipping this as a command rather than only as a library: an integrator
    verifying a plugin should not have to write a test harness first, and requiring pytest
    to validate a plugin is a barrier for exactly the person who most needs the check.
    """
    from .conformance import (
        check_data_source_adapter,
        check_embedding_model,
        check_retrieval_backend,
        describe_suites,
    )

    if args.list or not args.suite:
        _print({"suites": describe_suites(), "note": f"用法: {PROGRAM} verify <suite> [--source-type X | --name Y]"})
        return 0

    suite = args.suite
    if suite == "data_source_adapter":
        if not args.source_type or not args.uri:
            return _fail("data_source_adapter 契约需要 --source-type 与 --uri（契约是行为性的，必须连上真实数据源）")
        from .adapters import get_adapter

        report = check_data_source_adapter(
            get_adapter(args.source_type), args.uri, subject=args.source_type, expected_table=args.table
        )
    elif suite == "retrieval_backend":
        from .retrieval import get_retrieval_backend

        name = args.name or ""
        report = check_retrieval_backend(get_retrieval_backend(name), subject=name or "default")
    elif suite == "embedding_model":
        from .retrieval import get_embedding_model

        name = args.name or ""
        report = check_embedding_model(get_embedding_model(name), subject=name or "default")
    else:
        return _fail(
            f"{suite} 契约需要一个活的被测对象，无法从命令行构造。"
            f"请在代码中调用 ontology_platform.conformance.check_{suite}()，见 docs/extending.md。"
        )

    _print(report.as_dict())
    # Non-zero on failure so this works as a CI gate without extra scripting.
    return 0 if report.conformant else 1


def cmd_preflight(args: argparse.Namespace) -> int:
    """Refuse to proceed when the environment is unsafe for production.

    Exits non-zero on a blocker so a deployment pipeline stops. A warning in a startup log
    is read once, by whoever set the service up, and never again -- which is exactly when
    "authentication is disabled" stops being cheap to fix.
    """
    from .deployment import check_deployment, describe_checks

    if args.list:
        _print({"checks": describe_checks()})
        return 0

    report = check_deployment(
        environment=args.environment,
        platform_db=_platform_db(args),
        expected_origins=tuple(item.strip() for item in args.expect_origin.split(",") if item.strip()),
        worker_count=args.workers,
    )
    _print(report.as_dict())
    if not report.ready:
        print(report.summary(), file=sys.stderr)
    return 0 if report.ready else 1


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

    export_cmd = sub.add_parser("export", help="导出本体：平台词汇（jsonld／turtle）或标准词汇（owl／shacl）")
    export_cmd.add_argument("ontology_id", type=int)
    export_cmd.add_argument(
        "--format",
        default="owl",
        choices=("jsonld", "turtle", "owl", "shacl"),
        help="owl／shacl 为 OWL/RDFS/SHACL 标准词汇，可被外部 RDF 工具解释；jsonld／turtle 为平台词汇，字段更全",
    )
    export_cmd.add_argument("--output", default="", help="输出文件路径；缺省写到标准输出")
    export_cmd.set_defaults(func=cmd_export)

    audit = sub.add_parser("audit", help="生成一段时间的审计报表（存在阻断级发现时退出码非 0）")
    audit.add_argument("--start", required=True, help="起始时刻（含），如 2026-08-01")
    audit.add_argument("--end", required=True, help="结束时刻（不含），如 2026-09-01")
    audit.add_argument("--ontology-id", type=int, default=None, help="仅统计某个本体")
    audit.set_defaults(func=cmd_audit)

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
    serve.add_argument(
        "--skip-preflight",
        action="store_true",
        help="监听非本机地址时跳过部署前自检（不建议：自检拦的正是免鉴权暴露这类问题）",
    )
    serve.set_defaults(func=cmd_serve)

    doctor = sub.add_parser("doctor", help="报告当前配置、已安装 extra 与已注册扩展点")
    doctor.set_defaults(func=cmd_doctor)

    verify = sub.add_parser("verify", help="对已注册的扩展运行一致性契约（失败时退出码非 0，可作 CI 门禁）")
    verify.add_argument("suite", nargs="?", default="", help="契约名称，留空或加 --list 查看全部")
    verify.add_argument("--list", action="store_true", help="列出全部契约及其对应扩展点")
    verify.add_argument("--source-type", default="", help="data_source_adapter 契约：被测数据源类型")
    verify.add_argument("--uri", default="", help="data_source_adapter 契约：连接串（需含至少一表一行）")
    verify.add_argument("--table", default="", help="data_source_adapter 契约：期望扫描到的表名")
    verify.add_argument("--name", default="", help="检索后端／嵌入模型契约：已注册名称，留空用默认")
    verify.set_defaults(func=cmd_verify)

    preflight = sub.add_parser("preflight", help="部署前自检：配置在生产环境是否安全（阻断项存在时退出码非 0）")
    preflight.add_argument("--list", action="store_true", help="列出全部检查项")
    preflight.add_argument("--environment", default="production", help="环境名称，仅用于报告标注")
    preflight.add_argument("--workers", type=int, default=1, help="计划启动的工作进程数（用于判断 SQLite 是否合适）")
    preflight.add_argument("--expect-origin", default="", help="逗号分隔的前端来源，校验它们确实在 CORS 允许列表中")
    preflight.set_defaults(func=cmd_preflight)

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
