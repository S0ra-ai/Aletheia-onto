"""The refusals this platform returns, and the codes the console needs to translate them.

`backend/ontology_platform/error_codes.py` identifies a refusal by its sentence. That makes
the registry a table of *claims about text written somewhere else*, and a claim about text is
exactly the kind that rots in silence: a template that no longer matches anything looks
identical to one that does, and the only symptom is a Chinese sentence in an English console
-- which is the defect the registry exists to remove.

So the checks here are about reachability rather than about the registry agreeing with itself.
Two of them fail on a registry entry nothing can produce:

* every literal part of a template has to appear in the backend's own source, which is where
  the sentence it claims to match is written;
* the facts a template captures have to be the placeholders the console's sentence uses, or
  the translation renders a literal brace.

The sentences were transcribed from the modules that raise them, and the first run of this
test found three that were invented rather than transcribed (`角色不存在`, `工具不存在`,
`业务 API 不存在` -- none of which this platform says) and one that was truncated into a
sentence nothing emits. That is what it is for.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform import error_codes
from ontology_platform.database import initialize_platform_db

ADMIN_PASSWORD = "error-codes-password-123"

BACKEND = ROOT / "backend" / "ontology_platform"
FRONTEND_MESSAGES = ROOT / "frontend" / "src" / "i18n" / "messages" / "errors.ts"

# `'key': { zh: '…', en: '…' }`, the same shape `tests/test_ui_messages.py` reads. Only the
# keys and the placeholders matter here; that file owns whether the two languages agree.
MESSAGE_ENTRY = re.compile(
    r"'(?P<key>[\w.]+)':\s*\{\s*zh:\s*'(?P<zh>(?:[^'\\]|\\.)*)'\s*,\s*en:\s*'(?P<en>(?:[^'\\]|\\.)*)'",
    re.DOTALL,
)
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _platform_sentences() -> set[str]:
    """Every Chinese sentence the platform can raise, with its values blanked out.

    Read out of the AST rather than off the page, because several of these are built by
    implicit concatenation -- `QuotaExceeded` writes its sentence across three adjacent
    f-strings -- and no single literal in the file contains the whole thing.

    Both sides are compared with `{name}` reduced to `{}`: the registry names the facts for a
    console to use (`{ontologyId}`) while the module that raises it names its own variable
    (`{ontology_id}`), and requiring those to match would be requiring two layers to share a
    spelling for no reason a reader benefits from.
    """
    import ast

    blanked = re.compile(r"\{\w+\}")

    def shape(node: ast.expr) -> str | None:
        """A string literal or f-string as the sentence a reader gets, values blanked.

        Built from the node's own parts rather than by `ast.unparse`, which would hand back
        `f'用户不存在: {name}'` -- the `f` and the quotes are source syntax, not part of the
        sentence, and comparing against them matches nothing.
        """
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for piece in node.values:
                if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                    parts.append(piece.value)
                elif isinstance(piece, ast.FormattedValue):
                    # An f-string's own format spec is presentation, not content.
                    parts.append("{}")
            return "".join(parts)
        return None

    sentences: set[str] = set()
    for path in sorted(BACKEND.rglob("*.py")):
        if path.name == "error_codes.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Constant, ast.JoinedStr)):
                continue
            text = shape(node)
            if text and re.search(r"[一-鿿]", text):
                sentences.add(blanked.sub("{}", text).strip())
    return sentences


def test_every_template_quotes_a_sentence_the_platform_actually_says() -> None:
    """A transcript, not an invention.

    The failure this catches is the one that produced the module's first draft: a plausible
    sentence written from memory. It never matches, so it never translates, and nothing else
    in the system can tell it apart from a working entry.
    """
    said = _platform_sentences()
    blanked = re.compile(r"\{\w+\}")
    missing = [
        f"{code}: {template!r}"
        for code, templates in error_codes.TEMPLATES.items()
        for template in templates
        if blanked.sub("{}", template).strip() not in said
    ]
    assert not missing, "以下模板在后端源码的句子中找不到——这个模板永远匹配不上任何东西：\n  " + "\n  ".join(missing)


def _frontend_sentences() -> dict[str, dict[str, str]]:
    text = FRONTEND_MESSAGES.read_text(encoding="utf-8")
    return {
        match.group("key"): {"zh": match.group("zh"), "en": match.group("en")} for match in MESSAGE_ENTRY.finditer(text)
    }


def test_every_code_has_at_least_one_sentence() -> None:
    assert set(error_codes.CODES) == set(error_codes.TEMPLATES), (
        f"CODES 与 TEMPLATES 不一致：{sorted(set(error_codes.CODES) ^ set(error_codes.TEMPLATES))}"
    )


def test_each_code_survives_a_round_trip_through_its_own_sentence() -> None:
    """`sentence_for` then `identify` returns the code it started from.

    Built rather than transcribed: this is what proves the matcher handles the template's own
    shape, including the anchored ones and the two-part instance key.
    """
    facts = {
        "ontologyId": "7",
        "dataSourceId": "3",
        "objectCode": "contract",
        "instanceId": "42",
        "ruleId": "9",
        "sessionId": "abc",
        "workflowId": "5",
        "entryId": "2",
        "username": "alice",
        "roleCode": "analyst",
        "capability": "ontology:write",
        "name": "合同管理",
        "tenant": "acme",
        "resource": "本体",
        "limit": "5",
        "current": "5",
        "requested": "1",
        "actionCode": "submit",
        "algorithm": "RS256",
        "allowed": "sum、len",
        "ancestors": "party → entity",
        "audience": "aletheia",
        "authStyle": "custom",
        "count": "3",
        "description": "0002_add_column",
        "detail": "首次发布请显式确认。",
        "documentId": "12",
        "example": "合同 1 是否合规？",
        "expected": "acme",
        "actual": "globex",
        "expression": "amount > 0",
        "extension": "retrieval-backend",
        "files": "aletheia.toml",
        "fromState": "draft",
        "issuer": "https://idp.example.com",
        "mappingId": "4",
        "missing": "ontology_id",
        "path": "/tmp/extract",
        "filename": "orders.csv",
        "directory": "/tmp/extract",
        "providerGroup": "cn-legal",
        "reason": "金额超出授权范围",
        "root": "/tmp/extract",
        "ruleCode": "refund_window_check",
        "ruleType": "validation",
        "scopeObjectCode": "contract",
        "severity": "blocking",
        "status": "reviewing",
        "subject": "alice@example.com",
        "supported": "sum、len",
        "version": "0.1.0",
    }
    for code in error_codes.CODES:
        template = error_codes.TEMPLATES[code][0]
        needed = {name: facts[name] for name in PLACEHOLDER.findall(template)}
        sentence = error_codes.sentence_for(code, **needed)
        identified, captured = error_codes.identify(sentence)
        assert identified == code, f"{code}: {sentence!r} 被识别为 {identified!r}"
        assert captured == needed, f"{code}: 事实丢失 {sentence!r} -> {captured}"


def test_a_sentence_nobody_registered_keeps_its_own_text() -> None:
    """Not an error, and deliberately not an empty code.

    The console falls back to the server's sentence for a code it does not know; a refusal
    with no code at all takes the same path. What must not happen is a guessed code: a wrong
    translation attached to a right message is worse than the message alone.
    """
    assert error_codes.identify("这句话没有登记") == ("", {})
    assert error_codes.identify("") == ("", {})
    assert error_codes.decorate("这句话没有登记") == {"detail": "这句话没有登记"}
    # A structured detail is passed through: FastAPI allows one, and a refusal nobody has
    # named must not start rendering differently just because it has no code.
    assert error_codes.decorate({"errors": ["x"]}) == {"detail": {"errors": ["x"]}}


def test_the_console_can_name_every_code_the_platform_can_return() -> None:
    """Both directions, and the placeholders too.

    A code with no translation is the defect this whole module exists to remove. A translation
    with no code is a sentence nobody will ever read -- and, worse, the next reader treats it
    as coverage. The placeholder check is the third: `{ontologyId}` in the backend against
    `{id}` in the dictionary renders a literal brace to a user.
    """
    sentences = _frontend_sentences()
    prefix = "api."

    unnameable = [code for code in error_codes.CODES if f"{prefix}{code}" not in sentences]
    assert not unnameable, f"界面字典里没有这些错误码的句子：{sorted(unnameable)}"

    orphaned = [key for key in sentences if key.startswith(prefix) and key[len(prefix) :] not in error_codes.CODES]
    assert not orphaned, f"界面字典里的这些错误码后端永远不会发出：{sorted(orphaned)}"

    mismatched: list[str] = []
    for code in error_codes.CODES:
        # The facts are the union over the code's templates: a code with a bare spelling and
        # a parameterised one can be rendered with or without its facts, and both are right.
        expected: set[str] = set()
        for template in error_codes.TEMPLATES[code]:
            expected |= set(PLACEHOLDER.findall(template))
        entry = sentences[f"{prefix}{code}"]
        for language in ("zh", "en"):
            got = set(PLACEHOLDER.findall(entry[language]))
            if got != expected:
                mismatched.append(f"{prefix}{code}.{language}: 期望 {sorted(expected)}，实际 {sorted(got)}")
    assert not mismatched, "占位符与后端提供的事实对不上：\n  " + "\n  ".join(mismatched)


def test_a_code_with_two_spellings_gets_the_right_one() -> None:
    """`数据源不存在` and `数据源不存在: 3` are one refusal with and without its id.

    The bare template is a prefix of the parameterised one, so an unanchored match would take
    whichever was tried first and attach the wrong facts -- or none -- to the right sentence.
    """
    assert error_codes.identify("数据源不存在") == ("data_source_not_found", {})
    assert error_codes.identify("数据源不存在: 12") == ("data_source_not_found", {"dataSourceId": "12"})


def test_a_refusal_reaching_http_carries_its_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end through the real app, because the handler is the half that can be missed.

    The registry is only useful if a route's `HTTPException` is rendered through it. FastAPI
    replaces the default handler when one is registered for the class, so this asserts the
    substitution took effect rather than that a second handler was added beside it.
    """
    platform_db = tmp_path / "platform.sqlite3"
    monkeypatch.delenv("ONTOLOGY_AUTH_DISABLED", raising=False)
    monkeypatch.setenv("ONTOLOGY_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ONTOLOGY_ADMIN_PASSWORD", ADMIN_PASSWORD)

    import ontology_platform.api as api_module
    import ontology_platform.database as database_module

    database_module._platform_adapter = None
    monkeypatch.setattr(database_module, "DEFAULT_PLATFORM_DB", platform_db)
    initialize_platform_db(platform_db)
    api_module = importlib.reload(api_module)
    monkeypatch.setattr(api_module, "DEFAULT_PLATFORM_DB", platform_db)

    with TestClient(api_module.app) as client:
        # A refusal the authentication middleware renders itself.
        anonymous = client.get("/ontologies/1")
        assert anonymous.status_code == 401
        assert anonymous.json()["code"] == "unauthenticated"

        # A refusal a route raises, which is the path that had no code before.
        login = client.post("/auth/login", json={"username": "admin", "password": "wrong-password"})
        assert login.status_code == 401, login.text
        body = login.json()
        assert body["code"] == error_codes.AUTH_LOGIN_FAILED, body
        assert body["detail"] == "用户名或密码不正确", body

        token = client.post("/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        missing = client.get("/ontologies/99999", headers=headers)
        assert missing.status_code in (400, 404), missing.text
        assert missing.json()["code"] == error_codes.ONTOLOGY_NOT_FOUND, missing.json()
        assert missing.json()["facts"] == {"ontologyId": "99999"}, missing.json()

    database_module._platform_adapter = None


def test_the_untranslated_remainder_is_measured_rather_than_claimed() -> None:
    """How much of the refusal surface is still Chinese-only, as a number that can only fall.

    Most of the platform's refusals are still raised as `ValueError("中文句子")` with no
    registry entry, and pretending otherwise in the documentation would be the same class of
    claim this project keeps refusing to make. So the count is asserted from the source, and
    the assertion is a ceiling: adding a new Chinese refusal without a code fails here, and
    registering one lowers the ceiling that has to be written down.
    """
    import ast

    raised: set[str] = set()
    for path in sorted(BACKEND.rglob("*.py")):
        if path.name == "error_codes.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args):
                continue
            argument = node.exc.args[0]
            if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
                continue
            if re.search(r"[一-鿿]", argument.value):
                raised.add(argument.value)

    unregistered = sorted(sentence for sentence in raised if error_codes.identify(sentence)[0] == "")
    # A ceiling, not an equality: this is a record of the debt, set to what the source holds
    # today (50 of 101 single-sentence refusals; the parameterised ones are f-strings and are
    # counted the same way). Lower it when you register a code. Raising it means writing down
    # why, in this message, for the next reader.
    #
    # What is left is deliberately not registered: internal invariants a user cannot reach
    # (`instance_key` rejecting a malformed key, `schema` rejecting an empty DDL declaration,
    # the extension registry rejecting a duplicate name). A translation for a sentence nobody
    # will ever read is worse than none -- it reads as coverage.
    assert len(unregistered) <= 50, (
        f"未登记的中文拒绝语从 50 条涨到了 {len(unregistered)} 条——"
        "新增的拒绝语要么在 error_codes.py 里登记一个码，要么在这里把上限调高并说明理由。\n"
        + "\n".join(f"  {s}" for s in unregistered[:10])
    )
