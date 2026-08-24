"""Workflow, permission and tool routes.

Three concerns in one module because they are one concern in practice: a workflow
transition is gated by a role's permission, and a tool execution is gated by the same
role's tool authorization. Splitting them into three files would put a guard and the
thing it guards in different places.

Every route here is protected by the middleware in `api.py`, not by anything in this
file. That is the point of the split: authorization is decided in one table
(`access_policy.py`) and enforced in one middleware, so a route added to this module is
protected by default rather than by remembering to annotate it.

Stability: internal. Routers are an implementation detail of the HTTP layer; the routes
they serve are the public surface.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import Principal
from ..database import DEFAULT_PLATFORM_DB
from ..http_runtime import current_principal
from ..workflow_permission import (
    add_workflow_state,
    add_workflow_transition,
    authorize_tool,
    check_permission,
    check_tool_authorization,
    create_role,
    create_workflow,
    delete_workflow,
    enter_workflow,
    get_available_actions,
    get_instance_history,
    get_instance_state,
    get_workflow,
    get_workflow_by_object,
    list_pending_reviews,
    list_policies,
    list_roles,
    list_tools,
    list_workflows,
    register_tool,
    review_tool_execution,
    transition_instance,
    upsert_permission_policy,
)

router = APIRouter()


# -- Request models --


class WorkflowCreate(BaseModel):
    ontologyId: int
    objectCode: str
    name: str
    description: str = ""
    initialState: str = "draft"


class WorkflowStateAdd(BaseModel):
    code: str
    name: str
    description: str = ""
    isTerminal: bool = False
    color: str = "#666666"
    sortOrder: int = 0


class WorkflowTransitionAdd(BaseModel):
    fromState: str
    toState: str
    actionCode: str
    name: str
    guardExpression: str = ""
    requiresReview: bool = False
    reviewRole: str = ""
    sortOrder: int = 0


class WorkflowTransitionRun(BaseModel):
    instanceId: str
    actionCode: str
    reason: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


class WorkflowEnterInstance(BaseModel):
    objectCode: str
    instanceId: str


class RoleCreate(BaseModel):
    code: str
    name: str
    description: str = ""
    isSystem: bool = False


class PermissionPolicyUpsert(BaseModel):
    roleId: int
    objectCode: str
    canRead: bool = True
    canWrite: bool = False
    canExecute: bool = False
    canDelete: bool = False
    filterExpression: str = ""
    description: str = ""


class PermissionCheck(BaseModel):
    roleCode: str
    objectCode: str
    operation: str = "read"


class ToolRegister(BaseModel):
    code: str
    name: str
    description: str = ""
    toolType: str = "function"
    inputSchema: dict[str, object] = Field(default_factory=dict)
    riskLevel: str = "low"
    requiresReview: bool = False


class ToolAuthorize(BaseModel):
    roleId: int
    toolId: int
    allowed: bool = True
    maxCallsPerHour: int = 100


class ToolAuthCheck(BaseModel):
    roleCode: str
    toolCode: str


class ToolExecutionReview(BaseModel):
    decision: str


# -- Workflow definitions --


@router.get("/workflows")
def get_workflows(ontologyId: Optional[int] = None) -> dict[str, object]:
    return {"items": list_workflows(DEFAULT_PLATFORM_DB, ontologyId)}


@router.post("/workflows")
def create_new_workflow(payload: WorkflowCreate) -> dict[str, object]:
    try:
        return create_workflow(
            DEFAULT_PLATFORM_DB,
            payload.ontologyId,
            payload.objectCode,
            payload.name,
            payload.description,
            payload.initialState,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/workflows/{workflow_id}")
def get_workflow_detail(workflow_id: int) -> dict[str, object]:
    try:
        return get_workflow(DEFAULT_PLATFORM_DB, workflow_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/workflows/by-object/{ontology_id}/{object_code}")
def get_workflow_for_object(ontology_id: int, object_code: str) -> dict[str, object]:
    wf = get_workflow_by_object(DEFAULT_PLATFORM_DB, ontology_id, object_code)
    if wf is None:
        raise HTTPException(status_code=404, detail="该业务对象未配置工作流")
    return wf


@router.delete("/workflows/{workflow_id}")
def delete_workflow_def(workflow_id: int) -> dict[str, object]:
    delete_workflow(DEFAULT_PLATFORM_DB, workflow_id)
    return {"deleted": True}


@router.post("/workflows/{workflow_id}/states")
def add_state(workflow_id: int, payload: WorkflowStateAdd) -> dict[str, object]:
    try:
        return add_workflow_state(
            DEFAULT_PLATFORM_DB,
            workflow_id,
            payload.code,
            payload.name,
            payload.description,
            payload.isTerminal,
            payload.color,
            payload.sortOrder,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/workflows/{workflow_id}/transitions")
def add_transition(workflow_id: int, payload: WorkflowTransitionAdd) -> dict[str, object]:
    try:
        return add_workflow_transition(
            DEFAULT_PLATFORM_DB,
            workflow_id,
            payload.fromState,
            payload.toState,
            payload.actionCode,
            payload.name,
            payload.guardExpression,
            payload.requiresReview,
            payload.reviewRole,
            payload.sortOrder,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/workflows/{workflow_id}/enter")
def enter_instance_to_workflow(workflow_id: int, payload: WorkflowEnterInstance) -> dict[str, object]:
    try:
        return enter_workflow(DEFAULT_PLATFORM_DB, workflow_id, payload.objectCode, payload.instanceId)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/workflows/{workflow_id}/instances/{instance_id}")
def get_instance_workflow_state(workflow_id: int, instance_id: str) -> dict[str, object]:
    state = get_instance_state(DEFAULT_PLATFORM_DB, workflow_id, instance_id)
    if state is None:
        raise HTTPException(status_code=404, detail="实例不在工作流中")
    return state


@router.get("/workflows/{workflow_id}/instances/{instance_id}/actions")
def get_instance_available_actions(workflow_id: int, instance_id: str) -> dict[str, object]:
    actions = get_available_actions(DEFAULT_PLATFORM_DB, workflow_id, instance_id)
    return {"actions": actions}


@router.post("/workflows/{workflow_id}/transitions/run")
def run_transition(
    workflow_id: int,
    payload: WorkflowTransitionRun,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return transition_instance(
            DEFAULT_PLATFORM_DB,
            workflow_id,
            payload.instanceId,
            payload.actionCode,
            principal.actor,
            payload.reason,
            payload.metadata,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/workflows/{workflow_id}/instances/{instance_id}/history")
def get_instance_workflow_history(workflow_id: int, instance_id: str) -> dict[str, object]:
    return {"items": get_instance_history(DEFAULT_PLATFORM_DB, workflow_id, instance_id)}


# -- Roles and object permissions --


@router.get("/permissions/roles")
def get_permission_roles() -> dict[str, object]:
    return {"roles": list_roles(DEFAULT_PLATFORM_DB)}


@router.post("/permissions/roles")
def create_permission_role(payload: RoleCreate) -> dict[str, object]:
    try:
        return create_role(DEFAULT_PLATFORM_DB, payload.code, payload.name, payload.description, payload.isSystem)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/permissions/policies")
def get_permission_policies(roleId: Optional[int] = None) -> dict[str, object]:
    return {"policies": list_policies(DEFAULT_PLATFORM_DB, roleId)}


@router.post("/permissions/policies")
def upsert_policy(payload: PermissionPolicyUpsert) -> dict[str, object]:
    try:
        return upsert_permission_policy(
            DEFAULT_PLATFORM_DB,
            payload.roleId,
            payload.objectCode,
            payload.canRead,
            payload.canWrite,
            payload.canExecute,
            payload.canDelete,
            payload.filterExpression,
            payload.description,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/permissions/check")
def check_permission_endpoint(payload: PermissionCheck) -> dict[str, object]:
    return check_permission(DEFAULT_PLATFORM_DB, payload.roleCode, payload.objectCode, payload.operation)


# -- Tool registry and execution review --


@router.get("/tools")
def get_all_tools() -> dict[str, object]:
    return {"tools": list_tools(DEFAULT_PLATFORM_DB)}


@router.post("/tools")
def register_new_tool(payload: ToolRegister) -> dict[str, object]:
    try:
        return register_tool(
            DEFAULT_PLATFORM_DB,
            payload.code,
            payload.name,
            payload.description,
            payload.toolType,
            payload.inputSchema,
            payload.riskLevel,
            payload.requiresReview,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/tools/authorize")
def authorize_tool_for_role(payload: ToolAuthorize) -> dict[str, object]:
    try:
        return authorize_tool(
            DEFAULT_PLATFORM_DB,
            payload.roleId,
            payload.toolId,
            payload.allowed,
            payload.maxCallsPerHour,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/tools/check-auth")
def check_tool_auth(payload: ToolAuthCheck) -> dict[str, object]:
    return check_tool_authorization(DEFAULT_PLATFORM_DB, payload.roleCode, payload.toolCode)


@router.get("/tools/pending-reviews")
def get_pending_reviews(limit: int = 50) -> dict[str, object]:
    return {"items": list_pending_reviews(DEFAULT_PLATFORM_DB, limit)}


@router.post("/tools/logs/{log_id}/review")
def review_execution(
    log_id: int,
    payload: ToolExecutionReview,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return review_tool_execution(DEFAULT_PLATFORM_DB, log_id, principal.actor, payload.decision)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
