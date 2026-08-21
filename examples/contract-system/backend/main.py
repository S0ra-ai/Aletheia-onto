"""
合同管理系统 - FastAPI 后端
"""
import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from database import get_db, init_db

app = FastAPI(title="合同管理系统", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 文档存储目录
DOCUMENTS_DIR = Path(__file__).parent.parent / "documents"
DOCUMENTS_DIR.mkdir(exist_ok=True)


@app.get("/")
def root():
    return {"status": "ok", "name": "合同管理系统"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ==================== 数据模型 ====================

class CustomerCreate(BaseModel):
    name: str
    code: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    credit_level: str = "normal"


class ContractCreate(BaseModel):
    contract_no: str
    title: str
    customer_id: int
    amount: float
    currency: str = "CNY"
    sign_date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    type: str = "sales"
    description: Optional[str] = None
    created_by: Optional[str] = None


class PaymentPlanCreate(BaseModel):
    contract_id: int
    plan_no: int
    amount: float
    due_date: str


class InvoiceCreate(BaseModel):
    contract_id: int
    amount: float
    tax_rate: float = 0.13
    issue_date: str


# ==================== 客户 API ====================

@app.get("/api/customers")
def list_customers():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM customer ORDER BY id DESC").fetchall()
        return {"items": [dict(row) for row in rows]}


@app.post("/api/customers")
def create_customer(payload: CustomerCreate):
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO customer (name, code, contact_person, phone, email, address, credit_level) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (payload.name, payload.code, payload.contact_person, payload.phone, payload.email, payload.address, payload.credit_level),
            )
            return {"success": True, "message": "客户创建成功"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/customers/{customer_id}")
def get_customer(customer_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM customer WHERE id = ?", (customer_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="客户不存在")
        return dict(row)


@app.put("/api/customers/{customer_id}")
def update_customer(customer_id: int, payload: CustomerCreate):
    with get_db() as conn:
        conn.execute(
            "UPDATE customer SET name=?, code=?, contact_person=?, phone=?, email=?, address=?, credit_level=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (payload.name, payload.code, payload.contact_person, payload.phone, payload.email, payload.address, payload.credit_level, customer_id),
        )
        return {"success": True, "message": "客户更新成功"}


# ==================== 合同 API ====================

@app.get("/api/contracts")
def list_contracts(status: Optional[str] = None, customer_id: Optional[int] = None):
    with get_db() as conn:
        query = """
            SELECT c.*, cu.name as customer_name, cu.credit_level
            FROM contract c
            LEFT JOIN customer cu ON c.customer_id = cu.id
            WHERE 1=1
        """
        params = []
        if status:
            query += " AND c.status = ?"
            params.append(status)
        if customer_id:
            query += " AND c.customer_id = ?"
            params.append(customer_id)
        query += " ORDER BY c.id DESC"
        rows = conn.execute(query, params).fetchall()
        return {"items": [dict(row) for row in rows]}


@app.post("/api/contracts")
def create_contract(payload: ContractCreate):
    with get_db() as conn:
        try:
            conn.execute(
                """INSERT INTO contract (contract_no, title, customer_id, amount, currency, sign_date, start_date, end_date, type, description, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (payload.contract_no, payload.title, payload.customer_id, payload.amount, payload.currency,
                 payload.sign_date, payload.start_date, payload.end_date, payload.type, payload.description, payload.created_by),
            )
            return {"success": True, "message": "合同创建成功"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/contracts/{contract_id}")
def get_contract(contract_id: int):
    with get_db() as conn:
        row = conn.execute(
            """SELECT c.*, cu.name as customer_name, cu.credit_level
            FROM contract c
            LEFT JOIN customer cu ON c.customer_id = cu.id
            WHERE c.id = ?""",
            (contract_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="合同不存在")

        # 获取付款计划
        payments = conn.execute(
            "SELECT * FROM payment_plan WHERE contract_id = ? ORDER BY plan_no",
            (contract_id,),
        ).fetchall()

        # 获取发票
        invoices = conn.execute(
            "SELECT * FROM invoice WHERE contract_id = ? ORDER BY id DESC",
            (contract_id,),
        ).fetchall()

        # 获取审批记录
        approvals = conn.execute(
            "SELECT * FROM approval_record WHERE contract_id = ? ORDER BY id DESC",
            (contract_id,),
        ).fetchall()

        return {
            **dict(row),
            "payment_plans": [dict(p) for p in payments],
            "invoices": [dict(i) for i in invoices],
            "approval_records": [dict(a) for a in approvals],
        }


@app.put("/api/contracts/{contract_id}")
def update_contract(contract_id: int, payload: ContractCreate):
    with get_db() as conn:
        conn.execute(
            """UPDATE contract SET contract_no=?, title=?, customer_id=?, amount=?, currency=?,
            sign_date=?, start_date=?, end_date=?, type=?, description=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?""",
            (payload.contract_no, payload.title, payload.customer_id, payload.amount, payload.currency,
             payload.sign_date, payload.start_date, payload.end_date, payload.type, payload.description, contract_id),
        )
        return {"success": True, "message": "合同更新成功"}


@app.post("/api/contracts/{contract_id}/status")
def update_contract_status(contract_id: int, status: str, comment: Optional[str] = None):
    valid_transitions = {
        "draft": ["pending"],
        "pending": ["approved", "rejected"],
        "approved": ["active"],
        "active": ["completed", "terminated"],
    }
    with get_db() as conn:
        current = conn.execute("SELECT status FROM contract WHERE id = ?", (contract_id,)).fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="合同不存在")

        current_status = current["status"]
        if status not in valid_transitions.get(current_status, []):
            raise HTTPException(status_code=400, detail=f"不允许从 {current_status} 转换到 {status}")

        conn.execute("UPDATE contract SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, contract_id))

        # 记录审批
        action = "submit" if status == "pending" else "approve" if status == "approved" else "reject" if status == "rejected" else "complete"
        conn.execute(
            "INSERT INTO approval_record (contract_id, approver, action, comment) VALUES (?, ?, ?, ?)",
            (contract_id, "system", action, comment or f"状态变更为 {status}"),
        )
        return {"success": True, "message": f"合同状态已更新为 {status}"}


@app.post("/api/contracts/{contract_id}/submit")
def submit_contract(contract_id: int, comment: Optional[str] = None):
    """提交合同审批，供本体平台自动化预检通过后调用。"""
    return update_contract_status(contract_id, "pending", comment or "本体语义内核预检通过，自动提交审批")


# ==================== 付款计划 API ====================

@app.get("/api/contracts/{contract_id}/payments")
def list_payments(contract_id: int):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM payment_plan WHERE contract_id = ? ORDER BY plan_no", (contract_id,)).fetchall()
        return {"items": [dict(row) for row in rows]}


@app.post("/api/payments")
def create_payment(payload: PaymentPlanCreate):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO payment_plan (contract_id, plan_no, amount, due_date) VALUES (?, ?, ?, ?)",
            (payload.contract_id, payload.plan_no, payload.amount, payload.due_date),
        )
        return {"success": True, "message": "付款计划创建成功"}


@app.post("/api/payments/{payment_id}/pay")
def mark_payment_paid(payment_id: int, paid_amount: float):
    with get_db() as conn:
        conn.execute(
            "UPDATE payment_plan SET status='paid', paid_amount=?, paid_date=CURRENT_TIMESTAMP WHERE id=?",
            (paid_amount, payment_id),
        )
        return {"success": True, "message": "付款已记录"}


# ==================== 发票 API ====================

@app.get("/api/contracts/{contract_id}/invoices")
def list_invoices(contract_id: int):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM invoice WHERE contract_id = ? ORDER BY id DESC", (contract_id,)).fetchall()
        return {"items": [dict(row) for row in rows]}


@app.post("/api/invoices")
def create_invoice(payload: InvoiceCreate):
    with get_db() as conn:
        tax_amount = payload.amount * payload.tax_rate
        total_amount = payload.amount + tax_amount
        invoice_no = f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        conn.execute(
            "INSERT INTO invoice (invoice_no, contract_id, amount, tax_rate, tax_amount, total_amount, issue_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (invoice_no, payload.contract_id, payload.amount, payload.tax_rate, tax_amount, total_amount, payload.issue_date),
        )
        return {"success": True, "message": "发票创建成功", "invoice_no": invoice_no}


# ==================== 统计 API ====================

@app.get("/api/dashboard/stats")
def get_dashboard_stats():
    with get_db() as conn:
        total_customers = conn.execute("SELECT COUNT(*) as cnt FROM customer").fetchone()["cnt"]
        total_contracts = conn.execute("SELECT COUNT(*) as cnt FROM contract").fetchone()["cnt"]
        active_contracts = conn.execute("SELECT COUNT(*) as cnt FROM contract WHERE status='active'").fetchone()["cnt"]
        total_amount = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM contract WHERE status != 'terminated'").fetchone()["total"]
        pending_payments = conn.execute("SELECT COALESCE(SUM(amount - paid_amount), 0) as total FROM payment_plan WHERE status != 'paid'").fetchone()["total"]
        overdue_payments = conn.execute("SELECT COUNT(*) as cnt FROM payment_plan WHERE status='overdue'").fetchone()["cnt"]

        return {
            "total_customers": total_customers,
            "total_contracts": total_contracts,
            "active_contracts": active_contracts,
            "total_amount": total_amount,
            "pending_payments": pending_payments,
            "overdue_payments": overdue_payments,
        }


@app.get("/api/contracts/recent")
def get_recent_contracts(limit: int = 5):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT c.id, c.contract_no, c.title, c.amount, c.status, cu.name as customer_name
            FROM contract c LEFT JOIN customer cu ON c.customer_id = cu.id
            ORDER BY c.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return {"items": [dict(row) for row in rows]}


@app.get("/api/openapi-for-ontology.json")
def ontology_openapi_spec():
    """面向本体平台接入的业务 API 描述，包含语义动作扩展。"""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "合同管理系统业务 API",
            "version": "1.0.0",
            "description": "用于本体改造研发平台接入测试的合同管理业务系统。合同正文以 Word 文档存储。",
        },
        "paths": {
            "/api/contracts/{id}/status": {
                "post": {
                    "operationId": "update_contract_status",
                    "summary": "更新合同状态",
                    "x-semantic-action": "contract.update_status",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}},
                        {"name": "status", "in": "query", "required": True, "schema": {"type": "string", "enum": ["pending"]}},
                        {"name": "comment", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "状态更新成功"}},
                }
            },
            "/api/contracts/{id}/submit": {
                "post": {
                    "operationId": "submit_contract",
                    "summary": "提交合同审批",
                    "x-semantic-action": "contract.submit_for_approval",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}},
                        {"name": "comment", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "合同已提交审批"}},
                }
            },
            "/api/payments/{payment_id}/pay": {
                "post": {
                    "operationId": "confirm_payment",
                    "summary": "确认收款",
                    "x-semantic-action": "payment_plan.confirm_payment",
                    "parameters": [
                        {"name": "payment_id", "in": "path", "required": True, "schema": {"type": "integer"}},
                        {"name": "paid_amount", "in": "query", "required": True, "schema": {"type": "number"}},
                    ],
                    "responses": {"200": {"description": "付款已记录"}},
                }
            },
            "/api/contracts/{id}/document/download": {
                "get": {
                    "operationId": "download_contract_word",
                    "summary": "下载合同 Word 文档",
                    "x-semantic-action": "contract.download_word_document",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}},
                    ],
                    "responses": {
                        "200": {
                            "description": "Word 合同文件",
                            "content": {
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {}
                            },
                        }
                    },
                }
            },
        },
    }


# ==================== 文档 API ====================

def extract_text_from_docx(file_path: str) -> str:
    """从Word文档中提取文本"""
    try:
        from docx import Document
        doc = Document(file_path)
        text_parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)
        return "\n".join(text_parts)
    except Exception as e:
        return f"文本提取失败: {str(e)}"


def calculate_file_hash(file_path: str) -> str:
    """计算文件MD5哈希"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


@app.post("/api/contracts/{contract_id}/upload")
async def upload_contract_document(contract_id: int, file: UploadFile = File(...)):
    """上传合同Word文档"""
    # 验证文件类型
    if not file.filename.endswith(('.docx', '.doc')):
        raise HTTPException(status_code=400, detail="只支持Word文档(.docx/.doc)")
    
    with get_db() as conn:
        # 检查合同是否存在
        contract = conn.execute("SELECT id, contract_no FROM contract WHERE id = ?", (contract_id,)).fetchone()
        if not contract:
            raise HTTPException(status_code=404, detail="合同不存在")
        
        # 保存文件
        file_path = DOCUMENTS_DIR / f"{contract['contract_no']}_{file.filename}"
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        # 提取文本
        text_content = extract_text_from_docx(str(file_path))
        
        # 计算哈希
        file_hash = calculate_file_hash(str(file_path))
        
        # 更新合同记录
        conn.execute(
            """UPDATE contract SET 
            document_file=?, document_path=?, document_size=?, document_hash=?, document_text=?,
            updated_at=CURRENT_TIMESTAMP
            WHERE id=?""",
            (file.filename, str(file_path), len(content), file_hash, text_content, contract_id),
        )
        
        return {
            "success": True,
            "message": "文档上传成功",
            "file_name": file.filename,
            "file_size": len(content),
            "text_length": len(text_content),
        }


@app.get("/api/contracts/{contract_id}/document")
def get_contract_document(contract_id: int):
    """获取合同文档"""
    with get_db() as conn:
        contract = conn.execute(
            "SELECT document_file, document_path, document_size, document_hash FROM contract WHERE id = ?",
            (contract_id,),
        ).fetchone()
        
        if not contract or not contract["document_path"]:
            raise HTTPException(status_code=404, detail="合同文档不存在")
        
        if not os.path.exists(contract["document_path"]):
            raise HTTPException(status_code=404, detail="文档文件已被删除")
        
        return {
            "file_name": contract["document_file"],
            "file_size": contract["document_size"],
            "file_hash": contract["document_hash"],
            "download_url": f"/api/contracts/{contract_id}/document/download",
        }


@app.get("/api/contracts/{contract_id}/document/download")
def download_contract_document(contract_id: int):
    """下载合同文档"""
    with get_db() as conn:
        contract = conn.execute(
            "SELECT document_file, document_path FROM contract WHERE id = ?",
            (contract_id,),
        ).fetchone()
        
        if not contract or not contract["document_path"]:
            raise HTTPException(status_code=404, detail="合同文档不存在")
        
        if not os.path.exists(contract["document_path"]):
            raise HTTPException(status_code=404, detail="文档文件已被删除")
        
        return FileResponse(
            contract["document_path"],
            filename=contract["document_file"],
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


@app.get("/api/contracts/{contract_id}/document/text")
def get_contract_document_text(contract_id: int):
    """获取合同文档文本内容"""
    with get_db() as conn:
        contract = conn.execute(
            "SELECT document_text, document_file FROM contract WHERE id = ?",
            (contract_id,),
        ).fetchone()
        
        if not contract:
            raise HTTPException(status_code=404, detail="合同不存在")
        
        if not contract["document_text"]:
            # 尝试重新提取
            if contract.get("document_file"):
                file_path = DOCUMENTS_DIR / contract["document_file"]
                if os.path.exists(file_path):
                    text = extract_text_from_docx(str(file_path))
                    conn.execute(
                        "UPDATE contract SET document_text=? WHERE id=?",
                        (text, contract_id),
                    )
                    return {"text": text, "file_name": contract["document_file"]}
            raise HTTPException(status_code=404, detail="文档文本不存在")
        
        return {"text": contract["document_text"], "file_name": contract["document_file"]}


if __name__ == "__main__":
    import uvicorn
    init_db()
    uvicorn.run(app, host="0.0.0.0", port=8001)
