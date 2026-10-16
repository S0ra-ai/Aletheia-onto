"""The CLI's own words, in two languages.

The console is bilingual and the API's sentences are not: a refusal carries a code and the facts
it is about, and the console says them in the reader's language while the CLI prints the Chinese
one. That division was documented and it left `aletheia` itself Chinese-only, which is the first
thing an adopter meets -- `aletheia demo`, `aletheia new`, `aletheia --help`.

This is the CLI's half of that division, and it is deliberately the *same* half the console
translates: **what the tool says about itself**. Help text, the sentences it composes about what
it just did, and its own errors. What it does not translate is the JSON it prints, which is the
API's output -- the payload a pipeline parses, whose shape and vocabulary are the contract. An
operator reading `aletheia assess` output in English still sees Chinese inside `recommendation`,
exactly as the English console does, and for the same reason.

    aletheia --lang en demo
    ONTOLOGY_LANG=en aletheia demo

Chinese is the default, which is what every existing invocation gets.
"""

from __future__ import annotations

import os
from typing import Any

__all__ = ["LANG_ENV", "MESSAGES", "resolve_language", "translate"]

LANG_ENV = "ONTOLOGY_LANG"

# `{name}` is substituted by `translate`. Braces are literal otherwise -- the CLI prints JSON
# examples like `{"status": "ok"}`, and a naive `.format` would eat them.
MESSAGES: dict[str, tuple[str, str]] = {
    # -- Shared --
    "platform_db_uninitialized": (
        "平台库尚未初始化，请先运行 {program} init",
        "The platform database is not initialised yet. Run {program} init first.",
    ),
    "usage": ("用法: {usage}", "Usage: {usage}"),
    "serve_platform_db": ("[serve] 平台库: {path}", "[serve] platform database: {path}"),
    # -- init --
    "init_password_once": (
        "首次登录后请立即修改该密码；它只在本次初始化时输出一次。",
        "Change that password after the first sign-in; it is printed here once and never again.",
    ),
    # -- model --
    "model_mappings_pending": (
        "草案中的映射为 pending，需审核后才能发布。",
        "The draft's mappings are pending; they have to be reviewed before it can be published.",
    ),
    # -- publish --
    "publish_refused": ("发布被拒绝：{reason}", "Publication refused: {reason}"),
    "publish_force_hint": (
        "如确认要覆盖门禁，请显式传 --force（会写入审计）。",
        "To override the gate deliberately, pass --force explicitly; it is written to the audit log.",
    ),
    # -- new --
    "new_needs_name": (
        "需要项目名：{program} new <name> [--extension datasource ...]",
        "A project name is required: {program} new <name> [--extension datasource ...]",
    ),
    # -- demo --
    "demo_next_steps": (
        " serve  # 打开 http://127.0.0.1:8000/docs",
        " serve  # then open http://127.0.0.1:8000/docs",
    ),
    # -- passwd --
    "passwd_for": ("为 {username} 设置新口令: ", "New password for {username}: "),
    "passwd_again": ("再输入一次: ", "Enter it again: "),
    "passwd_mismatch": ("两次输入的口令不一致。", "The two passwords do not match."),
    # -- serve --
    "serve_needs_web_extra": (
        "HTTP 层需要 web extra，请先安装：pip install 'aletheia-onto[web]'",
        "The HTTP layer needs the web extra: pip install 'aletheia-onto[web]'",
    ),
    "serve_reload_with_workers": (
        "--reload 不能与多个 worker 同时使用，请将 --workers 设为 1",
        "--reload cannot be combined with several workers; set --workers 1",
    ),
    "serve_exposed_preflight_failed": (
        "监听地址 {host} 可从网络访问，但部署前自检未通过。修复上述阻断项，或显式传 --skip-preflight（不建议）。",
        "The service would listen on {host}, which is reachable from the network, but the "
        "deployment preflight did not pass. Fix the blockers above, or pass --skip-preflight "
        "explicitly (not recommended).",
    ),
    # -- doctor: why a SQL driver is not available --
    "driver_missing_installable": (
        "{label} 接入需要安装 {module}：pip install {package}",
        "{label} support needs the {module} package: pip install {package}",
    ),
    "driver_missing_vendor": (
        "{label} 接入需要安装 {module}（随 {vendor} 客户端提供，不在 PyPI 上）。",
        "{label} support needs {module}, which ships with the {vendor} client rather than on PyPI.",
    ),
    # -- verify --
    "verify_needs_source": (
        "data_source_adapter 契约需要 --source-type 与 --uri（契约是行为性的，必须连上真实数据源）",
        "The data_source_adapter contract needs --source-type and --uri: it is behavioural, so it "
        "has to connect to a real source.",
    ),
    "verify_needs_live_subject": (
        "{name} 契约需要一个活的被测对象，无法从命令行构造。请在代码中调用 "
        "ontology_platform.conformance.check_{name}()，见 docs/extending.md。",
        "The {name} contract needs a live subject and cannot be built from the command line. Call "
        "ontology_platform.conformance.check_{name}() in code instead; see docs/extending.md.",
    ),
    # -- top-level --
    "program_description": (
        "Aletheia：为传统业务系统安装可核验的业务语义内核",
        "Aletheia: install a verifiable semantic kernel over a legacy business system",
    ),
    "lang_help": (
        "输出语言：zh 或 en（也可用 ONTOLOGY_LANG 设置）",
        "Output language: zh or en (ONTOLOGY_LANG works too)",
    ),
    # -- Arguments --
    "platform_db_help": (
        "平台库路径（默认：源码 checkout 下为 ./data，已安装包为 ~/.aletheia，可用 ONTOLOGY_DATA_DIR 覆盖目录）",
        "Path to the platform database (default: ./data in a source checkout, ~/.aletheia for an "
        "installed package; ONTOLOGY_DATA_DIR overrides the directory)",
    ),
    "init_help": ("初始化平台库并创建引导管理员", "Create the platform database and a bootstrap administrator"),
    "connect_help": ("登记传统业务系统并扫描元数据", "Register a legacy system and scan its metadata"),
    "connect_uri_help": (
        "连接串，如 sqlite:///path.db 或 postgresql://...",
        "Connection string, e.g. sqlite:///path.db or postgresql://...",
    ),
    "connect_name_help": ("系统名称", "Name of the system"),
    "connect_name_default": ("传统业务系统", "Legacy system"),
    "connect_type_help": (
        "数据源类型：sqlite/postgresql/mysql 或已注册类型",
        "Source type: sqlite/postgresql/mysql, or any registered type",
    ),
    "connect_domain_help": ("业务域，用于推断行业蓝图", "Business domain, used to infer an industry blueprint"),
    "model_help": ("从已扫描的数据源生成本体草案", "Generate an ontology draft from a scanned data source"),
    "model_name_help": ("本体名称", "Ontology name"),
    "model_domain_help": ("业务域", "Business domain"),
    "model_blueprint_help": ("指定行业蓝图 id", "Pin a specific industry blueprint id"),
    "assess_help": ("对一个实例产出判定", "Produce a verdict for one instance"),
    "assess_evidence_help": (
        "输出完整证据而非仅判定与未通过规则",
        "Emit the full evidence rather than just the verdict and the failed rules",
    ),
    "assess_asof_help": (
        "按该时间点的历史值判定（YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS），用于回答「当时是否合规」",
        "Judge against the values as they were at that instant (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS), "
        "which is how you answer “was this compliant then”",
    ),
    "publish_help": ("发布本体版本（受发布门禁约束）", "Publish an ontology version, subject to the release gates"),
    "publish_actor_help": ("记入审计的操作者", "Operator recorded in the audit log"),
    "publish_force_help": (
        "覆盖发布门禁，未通过项数会写入审计",
        "Override the release gates; the number of failures is written to the audit log",
    ),
    "export_help": (
        "导出本体：平台词汇（jsonld／turtle）或标准词汇（owl／shacl）",
        "Export the ontology: platform vocabulary (jsonld/turtle) or standard vocabulary (owl/shacl)",
    ),
    "export_format_help": (
        "owl／shacl 为 OWL/RDFS/SHACL 标准词汇，可被外部 RDF 工具解释；jsonld／turtle 为平台词汇，字段更全",
        "owl/shacl are the OWL/RDFS/SHACL standard vocabularies, interpretable by external RDF "
        "tools; jsonld/turtle are this platform's own and carry more fields",
    ),
    "export_output_help": ("输出文件路径；缺省写到标准输出", "Output file path; writes to standard output by default"),
    "audit_help": (
        "生成一段时间的审计报表（存在阻断级发现时退出码非 0）",
        "Build an audit report for a period (exits non-zero when there are blocking findings)",
    ),
    "audit_start_help": ("起始时刻（含），如 2026-08-01", "Start instant, inclusive, e.g. 2026-08-01"),
    "audit_end_help": ("结束时刻（不含），如 2026-09-01", "End instant, exclusive, e.g. 2026-09-01"),
    "audit_ontology_help": ("仅统计某个本体", "Restrict to one ontology"),
    "new_help": (
        "生成一个项目骨架（依赖平台，不是 fork）",
        "Generate a project skeleton that depends on the platform rather than forking it",
    ),
    "new_name_help": ("项目名，同时作为 Python 包名", "Project name, which is also the Python package name"),
    "new_output_help": ("输出目录，缺省与项目名同名", "Output directory; defaults to the project name"),
    "new_domain_help": ("业务域，写入示例配置", "Business domain, written into the example configuration"),
    "new_extension_help": (
        "要生成的扩展点，可重复。用 --list-extensions 查看可选项",
        "Extension point to generate; repeatable. Use --list-extensions to see the options",
    ),
    "new_list_help": (
        "列出可选扩展点及各自适用场景",
        "List the available extension points and when each is the right one",
    ),
    "codegen_help": (
        "由已发布本体生成 TypeScript 类型与客户端",
        "Generate TypeScript types and a client from a published ontology",
    ),
    "codegen_allow_draft_help": (
        "允许从草案生成（仅供本地迭代：草案的对象与属性会在映射审核期间变动）",
        "Allow generating from a draft (local iteration only: a draft's objects and attributes "
        "change while its mappings are under review)",
    ),
    "demo_help": ("用内置样例系统跑通完整闭环", "Run the whole loop against the bundled sample system"),
    "demo_sample_db_help": ("样例业务库输出路径", "Where to write the sample business database"),
    "demo_quiet_help": (
        "只输出最终结果文档（便于脚本解析；初始化产生的引导口令仍会写入日志）",
        "Emit only the final result document, for scripts; a bootstrap password is still written to the log",
    ),
    "passwd_help": (
        "重置某个账号的口令（引导口令只打印一次，这是找回路径）",
        "Reset an account's password; the bootstrap password is printed once, and this is the way back",
    ),
    "passwd_username_help": ("要重置的账号，默认 admin", "Account to reset; defaults to admin"),
    "passwd_password_help": (
        "新口令；缺省则交互式输入，避免进入 shell 历史",
        "New password; prompted for when omitted, which keeps it out of your shell history",
    ),
    "passwd_actor_help": ("写入审计的操作者标识", "Operator identity written to the audit log"),
    "serve_help": ("启动 HTTP 服务", "Start the HTTP service"),
    "serve_host_help": ("监听地址，默认仅本机", "Address to listen on; loopback by default"),
    "serve_workers_help": (
        "工作进程数；SQLite 生产部署应保持 1",
        "Worker processes; a production SQLite deployment should keep this at 1",
    ),
    "serve_log_level_help": ("Uvicorn 日志级别", "Uvicorn log level"),
    "serve_reload_help": ("开发模式自动重载", "Reload automatically, for development"),
    "serve_skip_preflight_help": (
        "监听非本机地址时跳过部署前自检（不建议：自检拦的正是免鉴权暴露这类问题）",
        "Skip the deployment preflight when listening beyond loopback (not recommended: the "
        "preflight is what stops an unauthenticated exposure)",
    ),
    "doctor_help": (
        "报告当前配置、已安装 extra 与已注册扩展点",
        "Report the current configuration, installed extras and registered extension points",
    ),
    "verify_help": (
        "对已注册的扩展运行一致性契约（失败时退出码非 0，可作 CI 门禁）",
        "Run the conformance contracts against registered extensions; a non-zero exit makes it a CI gate",
    ),
    "verify_name_help": (
        "契约名称，留空或加 --list 查看全部",
        "Contract name; leave empty or use --list to see them all",
    ),
    "verify_list_help": ("列出全部契约及其对应扩展点", "List every contract and the extension point it belongs to"),
    "verify_source_type_help": (
        "data_source_adapter 契约：被测数据源类型",
        "data_source_adapter contract: the source type under test",
    ),
    "verify_uri_help": (
        "data_source_adapter 契约：连接串（需含至少一表一行）",
        "data_source_adapter contract: connection string, with at least one table and one row",
    ),
    "verify_table_help": (
        "data_source_adapter 契约：期望扫描到的表名",
        "data_source_adapter contract: a table name the scan should find",
    ),
    "verify_subject_help": (
        "检索后端／嵌入模型契约：已注册名称，留空用默认",
        "Retrieval backend / embedding model contract: a registered name; empty uses the default",
    ),
    "preflight_help": (
        "部署前自检：配置在生产环境是否安全（阻断项存在时退出码非 0）",
        "Deployment preflight: is this configuration safe to expose (non-zero exit when there are blockers)",
    ),
    "preflight_list_help": ("列出全部检查项", "List every check"),
    "preflight_environment_help": ("环境名称，仅用于报告标注", "Environment name, used only to label the report"),
    "preflight_workers_help": (
        "计划启动的工作进程数（用于判断 SQLite 是否合适）",
        "Planned worker count, used to judge whether SQLite is suitable",
    ),
    "preflight_listen_host_help": (
        "服务将要绑定的地址；留空按只监听回环处理（指定它才能得到与真正暴露时相同的严格程度）",
        "The address the service will bind; empty assumes loopback. Passing it is how a check run "
        "before exposing gets the same strictness as the exposure itself.",
    ),
    "preflight_origin_help": (
        "逗号分隔的前端来源，校验它们确实在 CORS 允许列表中",
        "Comma-separated frontend origins to check against the CORS allow-list",
    ),
}


def resolve_language(explicit: str = "") -> str:
    """`zh` or `en`: the flag, then the environment, then Chinese.

    Chinese stays the default rather than following the locale, for the same reason the console
    defaults to it: this is what every existing invocation gets, and a tool that changed language
    under an operator because their shell happened to export `LANG` would be a surprise in the
    middle of a deployment script.
    """
    for candidate in (explicit, os.environ.get(LANG_ENV, "")):
        value = (candidate or "").strip().lower()
        if value in ("zh", "en"):
            return value
    return "zh"


def translate(key: str, language: str, **params: Any) -> str:
    """One sentence, in one language.

    A key with no entry returns itself in brackets, visible on purpose -- the same choice the
    console makes for a missing dictionary key, and for the same reason: a blank would hide the
    gap, and this is the surface an adopter reads first.
    """
    entry = MESSAGES.get(key)
    if entry is None:
        return f"⟦{key}⟧"
    text = entry[0] if language == "zh" else entry[1]
    for name, value in params.items():
        text = text.replace("{" + name + "}", str(value))
    return text
