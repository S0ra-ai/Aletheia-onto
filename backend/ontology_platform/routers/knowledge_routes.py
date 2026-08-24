"""Knowledge base and conversation routes: documents, citations, sessions, feedback.

The knowledge layer and the conversation layer share a module because they share one
governance rule: **a knowledge entry is not retrievable until it is confirmed and
anchored**, and an answer's citations come only from entries that passed it. Splitting
them would put the gate and the thing it gates in different files.

Two constraints are enforced by the handlers here rather than documented:

- Uploaded documents produce `pending` entries. A mis-split clause that became a
  verdict's evidence produces "looks sourced but the source is wrong", which is more
  dangerous than having no citation at all.
- Confirming an entry requires anchoring it to a business object or rule. Unanchored
  text cannot answer "why does this passage support this conclusion", so it does not
  constitute evidence.

Feedback is recorded, never applied. A correction is one party's claim, not a new rule;
becoming a rule means going through governance (ADR-0002).

Stability: internal. Routers are an implementation detail of the HTTP layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..auth import Principal
from ..conversations import (
    escalate_conversation,
    feedback_summary,
    get_conversation,
    list_conversations,
    list_feedback,
    resolve_feedback,
    set_conversation_status,
    submit_feedback,
)
from ..http_runtime import current_principal, enforce_quota, platform_db
from ..knowledge_documents import (
    extract_text_from_docx,
    ingest_document,
    list_documents,
    list_entries,
    review_knowledge_entry,
)
from ..retrieval import supported_embedding_models, supported_retrieval_backends

router = APIRouter()


# -- Request models --


class KnowledgeEntryReview(BaseModel):
    status: str
    objectCode: Optional[str] = None
    ruleCode: Optional[str] = None


class FeedbackCreate(BaseModel):
    rating: str
    comment: str = ""
    correction: str = ""
    objectCode: str = ""
    ruleCode: str = ""


class FeedbackResolve(BaseModel):
    resolution: str = "resolved"


class EscalationCreate(BaseModel):
    assignee: str = ""
    reason: str = ""


class ConversationStatusUpdate(BaseModel):
    status: str


@router.get("/ontologies/{ontology_id}/knowledge/documents")
def knowledge_documents(ontology_id: int) -> dict[str, object]:
    return {"items": list_documents(platform_db(), ontology_id)}


@router.get("/ontologies/{ontology_id}/knowledge/entries")
def knowledge_entries(
    ontology_id: int,
    documentId: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> dict[str, object]:
    return {
        "items": list_entries(platform_db(), ontology_id, document_id=documentId, status=status, limit=limit),
        "retrievalBackends": list(supported_retrieval_backends()),
        "embeddingModels": list(supported_embedding_models()),
    }


@router.post("/ontologies/{ontology_id}/knowledge/documents")
async def upload_knowledge_document(
    ontology_id: int,
    file: UploadFile = File(...),
    title: str = Form(""),
    objectCode: str = Form(""),
    ruleCode: str = Form(""),
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Ingest a policy or contract document as pending knowledge entries."""
    content = await file.read()
    name = file.filename or "document"
    try:
        # Checked before parsing and before any row is written. A quota discovered
        # afterwards has to undo a partially ingested document, and the tenant is then
        # unsure what actually landed. Document ingestion is also the write most able to
        # fill a shared platform database, which is what makes it the one worth gating.
        enforce_quota("knowledge_documents")
        if name.lower().endswith(".docx"):
            text = extract_text_from_docx(content)
        else:
            # Plain text and Markdown are accepted as-is; anything else is
            # rejected rather than silently mis-parsed.
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError("仅支持 .docx 或 UTF-8 文本文件。") from error
        return ingest_document(
            platform_db(),
            ontology_id,
            title.strip() or Path(name).stem,
            text,
            source_name=name,
            object_code=objectCode,
            rule_code=ruleCode,
            actor=principal.actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/knowledge/entries/{entry_id}/review")
def review_entry(
    entry_id: int,
    payload: KnowledgeEntryReview,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return review_knowledge_entry(
            platform_db(),
            entry_id,
            payload.status,
            object_code=payload.objectCode,
            rule_code=payload.ruleCode,
            reviewer=principal.actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/conversations")
def conversations(status: str = "", limit: int = 50) -> dict[str, object]:
    return {"items": list_conversations(platform_db(), status=status, limit=limit)}


@router.get("/conversations/{session_id}")
def conversation_detail(session_id: str) -> dict[str, object]:
    try:
        return get_conversation(platform_db(), session_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/conversations/{session_id}/escalate")
def escalate(
    session_id: str,
    payload: EscalationCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Hand a conversation to a human."""
    try:
        return escalate_conversation(
            platform_db(),
            session_id,
            assignee=payload.assignee,
            reason=payload.reason,
            actor=principal.actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch("/conversations/{session_id}/status")
def update_conversation_status(
    session_id: str,
    payload: ConversationStatusUpdate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return set_conversation_status(platform_db(), session_id, payload.status, actor=principal.actor)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/conversations/messages/{message_id}/feedback")
def create_feedback(
    message_id: int,
    payload: FeedbackCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Record a verdict on one answer.

    Corrections are stored, never auto-applied: promoting one to a rule or a
    knowledge entry goes through governance.
    """
    try:
        return submit_feedback(
            platform_db(),
            message_id,
            payload.rating,
            comment=payload.comment,
            correction=payload.correction,
            object_code=payload.objectCode,
            rule_code=payload.ruleCode,
            actor=principal.actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/feedback")
def feedback_items(status: str = "", rating: str = "", limit: int = 100) -> dict[str, object]:
    return {
        "items": list_feedback(platform_db(), status=status, rating=rating, limit=limit),
        "summary": feedback_summary(platform_db()),
    }


@router.post("/feedback/{feedback_id}/resolve")
def resolve_feedback_item(
    feedback_id: int,
    payload: FeedbackResolve,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return resolve_feedback(platform_db(), feedback_id, resolution=payload.resolution, actor=principal.actor)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
