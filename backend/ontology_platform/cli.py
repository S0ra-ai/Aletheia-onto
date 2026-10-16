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
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

PROGRAM = "aletheia"

# The language the tool speaks about itself, resolved once per invocation from `--lang` or
# `ONTOLOGY_LANG`. Module state rather than a parameter threaded through thirty call sites: every
# one of them is printing to the same two streams, and a CLI invocation has exactly one language.
_LANGUAGE = "zh"


def _t(key: str, **params: Any) -> str:
    """One of this tool's own sentences, in the language this invocation is using.

    What it does *not* cover is the JSON these commands print: that is the API's output, whose
    shape and vocabulary are the contract a pipeline parses. It stays Chinese exactly as the
    English console's fallback does, and for the same reason -- see `cli_messages`.
    """
    from .cli_messages import translate

    return translate(key, _LANGUAGE, **params)


def program_name() -> str:
    """What to call this CLI in the hints it prints.

    A scaffolded project wraps this CLI so its extensions load, and its README says in as
    many words that the bare `aletheia` command does *not* load them. Printing
    `aletheia model 1` at the end of that project's own `connect` sends the reader to the one
    command the project told them not to use.

    The wrapper declares it, through a module attribute or the environment. Guessing from
    `sys.argv[0]` was the first attempt and it was wrong: under `pytest` every message came
    out prefixed `python -m pytest:`, which the CLI tests caught. A process can look like
    anything; the one thing that knows what it is, is the code that started it.
    """
    import os
    import sys

    declared = os.environ.get("ONTOLOGY_PROGRAM_NAME") or ""
    if not declared:
        main_module = sys.modules.get("__main__")
        declared = getattr(main_module, "PROGRAM_NAME", "") if main_module else ""
    return declared or PROGRAM


def _with_init_hint(message: str) -> str:
    """Say what to do when the platform database has not been initialised.

    Every command that touches the platform DB before `init` reports the storage engine's own
    sentence -- `no such table: data_source` -- which names an internal table and none of the
    command the reader has to run. `doctor` had this hint and nothing else did.
    """
    if "no such table" in message:
        return f"{message}\n{_t('platform_db_uninitialized', program=program_name())}"
    return message


def _print(payload: Any) -> None:
    """Emit a result as JSON.

    JSON rather than a formatted table: the first thing anyone does with a CLI in a B2B
    integration is pipe it into something else, and a table would have to be reparsed.
    """
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _fail(message: str) -> int:
    print(f"{program_name()}: {message}", file=sys.stderr)
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
            "note": _t("init_password_once"),
        }
    )
    return 0


def _init_optional_schemas(conn: Any) -> None:
    """Bring the database up to date: feature schemas, then pending migrations.

    Delegates to `bootstrap` rather than listing the schemas here. The list used to exist
    in two places -- this function and the HTTP startup -- and a schema missing from one
    produces a database where a feature returns empty results rather than an error, which
    reads as a data problem for a long time before anyone suspects a missing table.
    """
    from .bootstrap import prepare_database

    applied = prepare_database(conn)
    for entry in applied:
        if entry["status"] == "applied":
            _log_migration(entry)


def _log_migration(entry: dict[str, Any]) -> None:
    """Report an applied migration on stderr.

    On stderr rather than stdout because `init` and `demo --quiet` promise exactly one JSON
    document on stdout, and a caller parsing that stream must not have to filter progress
    lines out of it.
    """
    print(f"[migration] {entry['version']} {entry.get('description', '')}", file=sys.stderr)


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
            "next": f"{program_name()} model {source.id}",
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
            "note": _t("model_mappings_pending"),
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
    from .governance import ReleaseGateBlocked

    try:
        result = publish_ontology(platform_db, args.ontology_id, args.actor, force=args.force)
    except ReleaseGateBlocked as error:
        # Only here is force the answer. Offering it for a missing ontology -- as this used
        # to -- points the reader at a flag that cannot help them.
        return _fail(_t("publish_refused", reason=error) + "\n" + _t("publish_force_hint"))
    except ValueError as error:
        # The refusal's own wording is the useful output here, not a traceback.
        return _fail(_t("publish_refused", reason=error))
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


def cmd_new(args: argparse.Namespace) -> int:
    """Generate a project skeleton.

    A generated project rather than a cloned scaffold repository. A scaffold repo is a fork:
    it stops receiving improvements the moment it is used, and the first thing a user must do
    is delete the parts that do not apply. Generated code depends on the *installed* platform
    version, so upgrading is `pip install -U aletheia-onto`.
    """
    from .scaffold import ScaffoldError, create_project, describe_extension_points

    if args.list_extensions:
        _print({"extensionPoints": describe_extension_points()})
        return 0

    if not args.name:
        return _fail(_t("new_needs_name", program=program_name()))

    target = Path(args.directory) if args.directory else Path(args.name)
    try:
        result = create_project(
            target,
            project_name=args.name,
            extensions=args.extension,
            domain=args.domain,
        )
    except ScaffoldError as error:
        return _fail(str(error))
    _print(result)
    return 0


def cmd_codegen(args: argparse.Namespace) -> int:
    """Project a published ontology into TypeScript.

    Generated from the *ontology* rather than from OpenAPI, because that is where the useful
    information is: `contract.amount` is a decimal with a unit and `contract.customer_id`
    points at a customer. A hand-written mirror types every foreign key as a number, so
    nothing stops a developer passing a contract id where a customer is expected.
    """
    from .codegen import CodegenError, generate_typescript, write_typescript

    platform_db = _platform_db(args)
    try:
        if args.output:
            result = write_typescript(platform_db, args.ontology_id, args.output, allow_draft=args.allow_draft)
            _print(result)
        else:
            # To stdout so it can be piped into a file or a formatter without a temp path.
            print(generate_typescript(platform_db, args.ontology_id, allow_draft=args.allow_draft), end="")
    except (CodegenError, ValueError) as error:
        return _fail(str(error))
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Run the whole loop against a built-in sample system.

    The scenario itself lives in `demo.py`, shared with the HTTP layer. It used to be
    written out in both places and the copies had drifted: this one assessed an instance and
    the browser's did not, so the two demos named the same thing and showed different
    results.
    """
    from .demo import run_contract_demo
    from .sample_data import DEFAULT_SAMPLE_DB

    platform_db = _platform_db(args)
    if not args.quiet:
        cmd_init(args)
    else:
        # The demo prints one document per step by default, which is what a person
        # wants. A caller parsing the output wants exactly one, so `--quiet` suppresses
        # the init report rather than making the consumer split the stream.
        _silent(cmd_init, args)

    result = run_contract_demo(platform_db, Path(args.sample_db) if args.sample_db else DEFAULT_SAMPLE_DB)
    _print(
        {
            "platformDb": str(platform_db),
            "sampleDb": str(result["samplePath"]),
            "ontologyId": result["ontologyId"],
            "objectCode": result["objectCode"],
            "decision": result["decision"],
            "next": f"{program_name()}{_t('demo_next_steps')}",
        }
    )
    return 0


def cmd_passwd(args: argparse.Namespace) -> int:
    """Reset an account's password from the console.

    The recovery path for a deployment whose bootstrap password was printed once and missed,
    and for an operator who needs to cut off a session on suspicion. Console-only by design:
    see `auth.reset_password`.
    """
    from .auth import reset_password

    password = args.password
    if not password:
        # Read from the terminal rather than the command line, so the password does not land
        # in shell history or in the process list.
        import getpass

        password = getpass.getpass(_t("passwd_for", username=args.username))
        if password != getpass.getpass(_t("passwd_again")):
            return _fail(_t("passwd_mismatch"))
    try:
        result = reset_password(_platform_db(args), args.username, password, actor=args.actor)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ValueError as error:
        return _fail(str(error))


def cmd_serve(args: argparse.Namespace) -> int:
    """Run the HTTP API."""
    try:
        import uvicorn
    except ImportError:
        # A missing optional extra is a configuration problem, so it gets an
        # instruction rather than a traceback.
        return _fail(_t("serve_needs_web_extra"))

    workers = max(1, int(args.workers))
    if args.reload and workers != 1:
        return _fail(_t("serve_reload_with_workers"))

    # Binding to anything other than loopback means the service is reachable from the
    # network, so the preflight blockers become exploitable rather than theoretical. Run it
    # by default and refuse -- nobody remembers to run a separate command, and the one time
    # it matters is the deployment where `ONTOLOGY_AUTH_DISABLED` was left on.
    exposed = args.host not in ("127.0.0.1", "localhost", "::1")
    if exposed and not args.skip_preflight:
        from .deployment import check_deployment

        report = check_deployment(platform_db=_platform_db(args), worker_count=workers, listen_host=args.host)
        if not report.ready:
            print(report.summary(), file=sys.stderr)
            return _fail(_t("serve_exposed_preflight_failed", host=args.host))

    if not args.platform_db:
        uvicorn.run(
            "ontology_platform.api:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            workers=workers,
            log_level=args.log_level,
        )
        return 0

    # With `--platform-db`, the server has to run in a **child process**.
    #
    # `database.DEFAULT_PLATFORM_DB` is a module constant resolved at import time, and `cli`
    # has already imported `database` by the time it reaches this function. So setting the
    # environment variable here and calling `uvicorn.run` in-process changes nothing: the
    # constant was fixed long before, and `api` binds the already-fixed value.
    #
    # That was the actual defect, and it failed in the worst available shape. `aletheia init
    # --platform-db X` followed by `aletheia serve --platform-db X` served a *different*
    # database, so the API returned an empty ontology list and rejected the administrator
    # password -- with nothing reporting a mismatch. "Empty results and a rejected login"
    # reads as "my data did not save", which sends the investigation to the writes rather
    # than to the path.
    #
    # A fresh process is the only way the variable can be observed, because the value is read
    # once per interpreter. Passing `--platform-db` through to a child rather than asking the
    # user to export the variable themselves: a flag that silently means something different
    # from every other command's identical flag is worse than no flag.
    from .database import PLATFORM_DB_FILE_ENV

    resolved = str(Path(args.platform_db).expanduser().resolve())
    environment = dict(os.environ)
    environment[PLATFORM_DB_FILE_ENV] = resolved
    # Announced because a silent correct default and a silent wrong default look identical
    # from outside, and this is the value that decides whether a deployment sees its own data.
    print(_t("serve_platform_db", path=resolved), file=sys.stderr)

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "ontology_platform.api:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--workers",
        str(workers),
        "--log-level",
        args.log_level,
    ]
    if args.reload:
        command.append("--reload")

    try:
        return subprocess.call(command, env=environment)
    except KeyboardInterrupt:
        # Ctrl-C reaches both processes; the child handles its own shutdown, and reporting a
        # traceback here would make a normal stop look like a crash.
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
                # Empty when the driver is installed: a hint for a problem the reader does not
                # have is noise on the one screen that answers "why is Oracle not in the list".
                "hint": "" if item["driverAvailable"] else _driver_hint(item),
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
        report["hint"] = _t("platform_db_uninitialized", program=PROGRAM)
    _print(report)
    return 0


def _driver_hint(item: dict[str, Any]) -> str:
    """Why a declared SQL driver is not available, said in the language this invocation uses.

    `doctor` is what an operator runs when something they expected is missing from the list, and
    this hint is the answer. The declaration carries the sentence *and* a code with the facts it
    names -- the same pair `advice.py` and the release gates carry -- so the sentence is composed
    here rather than printed as given. The declaration's own sentence is the fallback for a code
    this build does not know, which is also what the Chinese side gets: recomposing it there
    would be a second place for the same sentence to be phrased differently.
    """
    code = item.get("installHintCode") or ""
    facts = item.get("installHintFacts") or {}
    if _LANGUAGE == "zh" or code not in ("driver_missing_installable", "driver_missing_vendor"):
        return str(item.get("installHint") or "")
    return _t(code, **{key: str(value) for key, value in facts.items()})


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
        _print(
            {
                "suites": describe_suites(),
                "note": _t("usage", usage=f"{PROGRAM} verify <suite> [--source-type X | --name Y]"),
            }
        )
        return 0

    suite = args.suite
    if suite == "data_source_adapter":
        if not args.source_type or not args.uri:
            return _fail(_t("verify_needs_source"))
        from .adapters import get_adapter

        report = check_data_source_adapter(
            get_adapter(args.source_type), args.uri, subject=args.source_type, expected_table=args.table
        )
    elif suite == "retrieval_backend":
        from .retrieval import get_retrieval_backend

        name = args.name or ""
        report = check_retrieval_backend(get_retrieval_backend(name), subject=name or "default")
    elif suite == "model_provider":
        # Checked against the platform's own client and its intentional-failure twin, which is
        # what "the kernel passes the contract it publishes" means for this extension point --
        # the failure paths cannot be exercised against an arbitrary implementation, so the
        # contract requires one from whoever claims conformance.
        from .conformance import builtin_model_provider_pair, check_model_provider

        working, failing, secret = builtin_model_provider_pair()
        report = check_model_provider(working, failing, subject="built-in (openrouter)", secret=secret)
    elif suite == "embedding_model":
        from .retrieval import get_embedding_model

        name = args.name or ""
        report = check_embedding_model(get_embedding_model(name), subject=name or "default")
    else:
        return _fail(_t("verify_needs_live_subject", name=suite))

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
        # `serve` passes the address it is about to bind and blocks on what that makes
        # exploitable; a manual `preflight` does not know one, so it assumes loopback. Passing
        # `--listen-host` is how an operator checks before exposing rather than after --
        # otherwise the same configuration is a warning here and a refusal there, and the
        # difference looks like a bug in whichever one they ran second.
        listen_host=args.listen_host,
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
        description=_t("program_description"),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
    # Resolved once, before anything can print. `--lang` beats `ONTOLOGY_LANG`, and both are
    # read here rather than in each command so that a subcommand added tomorrow is covered
    # without knowing this exists.
    parser.add_argument("--lang", default="", help=_t("lang_help"))
    # Global, because every subcommand acts on a platform database and threading it
    # through each one separately would let two commands disagree about which.
    parser.add_argument(
        "--platform-db",
        default="",
        help=_t("platform_db_help"),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help=_t("init_help"))
    init.set_defaults(func=cmd_init)

    connect_cmd = sub.add_parser("connect", help=_t("connect_help"))
    connect_cmd.add_argument("uri", help=_t("connect_uri_help"))
    connect_cmd.add_argument("--name", default=_t("connect_name_default"), help=_t("connect_name_help"))
    connect_cmd.add_argument("--type", default="sqlite", help=_t("connect_type_help"))
    connect_cmd.add_argument("--domain", default="", help=_t("connect_domain_help"))
    connect_cmd.set_defaults(func=cmd_connect)

    model = sub.add_parser("model", help=_t("model_help"))
    model.add_argument("data_source_id", type=int)
    model.add_argument("--name", default="", help=_t("model_name_help"))
    model.add_argument("--domain", default="", help=_t("model_domain_help"))
    model.add_argument("--blueprint", default="", help=_t("model_blueprint_help"))
    model.set_defaults(func=cmd_model)

    assess = sub.add_parser("assess", help=_t("assess_help"))
    assess.add_argument("ontology_id", type=int)
    assess.add_argument("object_code")
    assess.add_argument("instance_id")
    assess.add_argument("--verbose", action="store_true", help=_t("assess_evidence_help"))
    assess.add_argument(
        "--as-of",
        default="",
        help=_t("assess_asof_help"),
    )
    assess.set_defaults(func=cmd_assess)

    publish = sub.add_parser("publish", help=_t("publish_help"))
    publish.add_argument("ontology_id", type=int)
    publish.add_argument("--actor", default="cli", help=_t("publish_actor_help"))
    publish.add_argument("--force", action="store_true", help=_t("publish_force_help"))
    publish.set_defaults(func=cmd_publish)

    export_cmd = sub.add_parser("export", help=_t("export_help"))
    export_cmd.add_argument("ontology_id", type=int)
    export_cmd.add_argument(
        "--format",
        default="owl",
        choices=("jsonld", "turtle", "owl", "shacl"),
        help=_t("export_format_help"),
    )
    export_cmd.add_argument("--output", default="", help=_t("export_output_help"))
    export_cmd.set_defaults(func=cmd_export)

    audit = sub.add_parser("audit", help=_t("audit_help"))
    audit.add_argument("--start", required=True, help=_t("audit_start_help"))
    audit.add_argument("--end", required=True, help=_t("audit_end_help"))
    audit.add_argument("--ontology-id", type=int, default=None, help=_t("audit_ontology_help"))
    audit.set_defaults(func=cmd_audit)

    new_cmd = sub.add_parser("new", help=_t("new_help"))
    new_cmd.add_argument("name", nargs="?", default="", help=_t("new_name_help"))
    new_cmd.add_argument("--directory", default="", help=_t("new_output_help"))
    new_cmd.add_argument(
        "--extension",
        action="append",
        default=[],
        help=_t("new_extension_help"),
    )
    new_cmd.add_argument("--domain", default="", help=_t("new_domain_help"))
    new_cmd.add_argument("--list-extensions", action="store_true", help=_t("new_list_help"))
    new_cmd.set_defaults(func=cmd_new)

    codegen = sub.add_parser("codegen", help=_t("codegen_help"))
    codegen.add_argument("ontology_id", type=int)
    codegen.add_argument("--output", default="", help=_t("export_output_help"))
    codegen.add_argument(
        "--allow-draft",
        action="store_true",
        help=_t("codegen_allow_draft_help"),
    )
    codegen.set_defaults(func=cmd_codegen)

    demo = sub.add_parser("demo", help=_t("demo_help"))
    demo.add_argument("--sample-db", default="", help=_t("demo_sample_db_help"))
    demo.add_argument(
        "--quiet",
        action="store_true",
        help=_t("demo_quiet_help"),
    )
    demo.set_defaults(func=cmd_demo)

    passwd = sub.add_parser("passwd", help=_t("passwd_help"))
    passwd.add_argument("--username", default="admin", help=_t("passwd_username_help"))
    passwd.add_argument("--password", default="", help=_t("passwd_password_help"))
    passwd.add_argument("--actor", default="cli", help=_t("passwd_actor_help"))
    passwd.set_defaults(func=cmd_passwd)

    serve = sub.add_parser("serve", help=_t("serve_help"))
    serve.add_argument("--host", default="127.0.0.1", help=_t("serve_host_help"))
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--workers", type=int, default=1, help=_t("serve_workers_help"))
    serve.add_argument(
        "--log-level",
        default="info",
        choices=("trace", "debug", "info", "warning", "error", "critical"),
        help=_t("serve_log_level_help"),
    )
    serve.add_argument("--reload", action="store_true", help=_t("serve_reload_help"))
    serve.add_argument(
        "--skip-preflight",
        action="store_true",
        help=_t("serve_skip_preflight_help"),
    )
    serve.set_defaults(func=cmd_serve)

    doctor = sub.add_parser("doctor", help=_t("doctor_help"))
    doctor.set_defaults(func=cmd_doctor)

    verify = sub.add_parser("verify", help=_t("verify_help"))
    verify.add_argument("suite", nargs="?", default="", help=_t("verify_name_help"))
    verify.add_argument("--list", action="store_true", help=_t("verify_list_help"))
    verify.add_argument("--source-type", default="", help=_t("verify_source_type_help"))
    verify.add_argument("--uri", default="", help=_t("verify_uri_help"))
    verify.add_argument("--table", default="", help=_t("verify_table_help"))
    verify.add_argument("--name", default="", help=_t("verify_subject_help"))
    verify.set_defaults(func=cmd_verify)

    preflight = sub.add_parser("preflight", help=_t("preflight_help"))
    preflight.add_argument("--list", action="store_true", help=_t("preflight_list_help"))
    preflight.add_argument(
        "--listen-host",
        default="",
        help=_t("preflight_listen_host_help"),
    )
    preflight.add_argument("--environment", default="production", help=_t("preflight_environment_help"))
    preflight.add_argument("--workers", type=int, default=1, help=_t("preflight_workers_help"))
    preflight.add_argument("--expect-origin", default="", help=_t("preflight_origin_help"))
    preflight.set_defaults(func=cmd_preflight)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point: resolve the language, then run the parsed command."""
    global _LANGUAGE

    # The language has to be known *before* the parser is built, because the help text is one of
    # the things being translated -- and `--lang` is parsed by that parser. So it is read out of
    # the raw arguments here, accepting both `--lang en` and `--lang=en`, and `argparse` then
    # sees it again as an ordinary flag. Reading it after parsing would leave `--help` in
    # Chinese for the reader who asked for English, which is the one invocation where the
    # language matters most.
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    explicit = ""
    for index, token in enumerate(raw_argv):
        if token.startswith("--lang="):
            explicit = token.split("=", 1)[1]
        elif token == "--lang" and index + 1 < len(raw_argv):
            explicit = raw_argv[index + 1]
    from .cli_messages import resolve_language

    _LANGUAGE = resolve_language(explicit)

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:  # pragma: no cover - interactive
        return 130
    except Exception as error:
        # A stack trace is the wrong output for an operator running a command; the
        # message is. `--verbose`-style tracebacks belong to the library's callers.
        return _fail(_with_init_hint(str(error)))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
