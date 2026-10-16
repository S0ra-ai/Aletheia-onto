"""Verdicts: producing one, explaining it, and acting on it.

The five `/semantic` routes answer "what does this mean for this instance"; `/agent` is the
conversational front end onto the same kernel; `/automation` is what happens after a verdict
says an operation may proceed. One module because they are one pipeline -- a reader following
a refusal from the console ends up in `assess_instance`, then in `execute_operation`, and
having those in three files would put the gate and the thing it gates apart.

Every route here is protected by the middleware in `api.py`, not by anything in this file.
That is the point of the split: authorization is decided in one table (`access_policy.py`) and
enforced in one middleware, so a route added to this module is protected by default rather
than by remembering to annotate it.

Stability: internal. Routers are an implementation detail of the HTTP layer; the routes they
serve are the public surface.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..agent import agent_chat, get_agent_roles
from ..agent_roles import delete_agent_role, upsert_agent_role
from ..auth import Principal
from ..automation import execute_operation, preflight_operation
from ..database import connect
from ..http_runtime import current_principal, enforce_quota, platform_db
from ..natural_language import query_natural_language
from ..object_service import ObjectAccessError, get_object_instance, list_object_instances
from ..ontology import explain_instance, resolve_ontology_for_object
from ..semantic_kernel import assess_decision_consistency, assess_instance
from ..temporal import TemporalError

router = APIRouter()


# Request models for these routes only. They lived in `api.py` beside thirty others; a model
# belongs next to the route that reads it, and each of these has exactly one.
class OperationPreflightCreate(BaseModel):
    ontologyId: int
    dataSourceId: int
    instanceId: str
    objectCode: Optional[str] = None


class DecisionConsistencyCreate(BaseModel):
    ontologyId: int
    instanceIds: list[str] = Field(default_factory=list)
    limit: int = 50


class NaturalLanguageQueryCreate(BaseModel):
    question: str
    ontologyId: Optional[int] = None
    dataSourceId: Optional[int] = None
    objectCode: Optional[str] = None
    instanceId: Optional[str] = None
    history: list[dict[str, str]] = Field(default_factory=list)
    useModel: bool = True


class OperationExecuteCreate(OperationPreflightCreate):
    payload: dict[str, object] = Field(default_factory=dict)
    dryRun: bool = True
    timeoutSeconds: float = 10


class AgentChatCreate(BaseModel):
    message: str
    # Unset means "let the platform pick a role from the onboarded domains".
    roleId: Optional[str] = None
    dataSourceId: Optional[int] = None
    objectCode: Optional[str] = None
    history: list[dict[str, str]] = Field(default_factory=list)
    sessionId: Optional[str] = None


@router.get("/semantic/objects/{object_code}/instances/{instance_id}/explain")
def explain_object_instance(
    object_code: str, instance_id: str, ontologyId: Optional[int] = None, asOf: str = ""
) -> dict[str, object]:
    """Explain an instance, optionally as of a past instant.

    `asOf` exists because a verdict can be produced for a past moment: explaining only the
    present would leave the reader of an old verdict unable to check it, which is the one
    question an explanation exists to answer.
    """
    try:
        resolved = ontologyId if ontologyId is not None else resolve_ontology_for_object(platform_db(), object_code)
        return explain_instance(platform_db(), resolved, object_code, instance_id, as_of=asOf or None)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/semantic/objects/{object_code}/instances")
def list_semantic_object_instances(
    object_code: str,
    ontologyId: Optional[int] = None,
    limit: Optional[int] = None,
    offset: int = 0,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Browse a business object through its configured instance resolver."""
    try:
        resolved = ontologyId if ontologyId is not None else resolve_ontology_for_object(platform_db(), object_code)
        return list_object_instances(
            platform_db(),
            resolved,
            object_code,
            role_code=principal.role_code,
            limit=limit,
            offset=offset,
        )
    except ObjectAccessError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/semantic/objects/{object_code}/instances/{instance_id}")
def get_semantic_object_instance(
    object_code: str,
    instance_id: str,
    ontologyId: Optional[int] = None,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Fetch one business-object instance through the same permission boundary."""
    try:
        resolved = ontologyId if ontologyId is not None else resolve_ontology_for_object(platform_db(), object_code)
        return get_object_instance(
            platform_db(),
            resolved,
            object_code,
            instance_id,
            role_code=principal.role_code,
        )
    except ObjectAccessError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/semantic/objects/{object_code}/instances/{instance_id}/assess")
def assess_object_instance(
    object_code: str,
    instance_id: str,
    ontologyId: Optional[int] = None,
    asOf: str = "",
) -> dict[str, object]:
    """Assess one instance, optionally as of a past moment.

    `asOf` is what a compliance audit actually asks: was the January approval correct given
    what was known in January. Assessing against today's values answers a different
    question, so the moment is echoed in the response and stored with the decision.
    """
    try:
        resolved = ontologyId if ontologyId is not None else resolve_ontology_for_object(platform_db(), object_code)
        # Every assessment of an instance records a decision, which is what the
        # `decision_records` quota counts.
        enforce_quota("decision_records")
        return assess_instance(platform_db(), resolved, object_code, instance_id, as_of=asOf or None)
    except TemporalError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/semantic/objects/{object_code}/consistency")
def assess_object_decision_consistency(object_code: str, payload: DecisionConsistencyCreate) -> dict[str, object]:
    try:
        return assess_decision_consistency(
            platform_db(),
            payload.ontologyId,
            object_code,
            payload.instanceIds,
            payload.limit,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/semantic/natural-language/query")
def ask_semantic_kernel(
    payload: NaturalLanguageQueryCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Answer a question, filtering citations by what the caller may read.

    The role comes from the authenticated identity, never from the request body: a caller
    who could name their own role would grant themselves any document.
    """
    try:
        return query_natural_language(
            platform_db(),
            payload.question,
            payload.ontologyId,
            payload.dataSourceId,
            payload.objectCode,
            payload.instanceId,
            payload.history,
            payload.useModel,
            role_code=principal.role_code,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/agent/roles")
def list_agent_roles() -> dict[str, object]:
    return {"roles": get_agent_roles(platform_db())}


class AgentRoleUpsert(BaseModel):
    code: str
    name: str
    description: str = ""
    domain: str = ""
    systemPrompt: str = ""
    dataSourceId: Optional[int] = None


@router.post("/agent/roles")
def create_or_update_agent_role(
    payload: AgentRoleUpsert,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Persist a custom agent role for domains needing bespoke wording."""
    try:
        return upsert_agent_role(
            platform_db(),
            payload.code,
            payload.name,
            payload.description,
            payload.domain,
            payload.systemPrompt,
            payload.dataSourceId,
            actor=principal.actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/agent/roles/{code}")
def remove_agent_role(code: str, principal: Principal = Depends(current_principal)) -> dict[str, object]:
    return delete_agent_role(platform_db(), code, actor=principal.actor)


@router.post("/agent/chat")
def chat_with_agent(
    payload: AgentChatCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        # The first turn of a session creates the conversation; later turns do not.
        with connect(platform_db()) as conn:
            session_exists = (
                conn.execute("select 1 from conversation where session_id = ?", (payload.sessionId,)).fetchone()
                is not None
                if payload.sessionId
                else False
            )
        enforce_quota("conversations", requested=0 if session_exists else 1)
        return agent_chat(
            platform_db(),
            payload.message,
            payload.roleId,
            payload.dataSourceId,
            payload.objectCode,
            # None lets the stored history load; an explicit list still wins, so a
            # caller managing its own context is unaffected.
            payload.history or None,
            payload.sessionId,
            actor=principal.actor,
            # Citations are filtered by what this caller may read. Taken from the
            # authenticated identity, never from the payload's `roleId` -- that names an
            # agent persona, which is not an authorisation.
            role_code=principal.role_code,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/automation/operations/{operation_code}/preflight")
def preflight_business_operation(operation_code: str, payload: OperationPreflightCreate) -> dict[str, object]:
    try:
        return preflight_operation(
            platform_db(),
            payload.ontologyId,
            payload.dataSourceId,
            operation_code,
            payload.instanceId,
            payload.objectCode,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/automation/operations/{operation_code}/execute")
def execute_business_operation(
    operation_code: str,
    payload: OperationExecuteCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return execute_operation(
            platform_db(),
            payload.ontologyId,
            payload.dataSourceId,
            operation_code,
            payload.instanceId,
            payload.objectCode,
            payload.payload,
            principal.actor,
            payload.dryRun,
            payload.timeoutSeconds,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
