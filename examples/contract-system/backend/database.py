"""
合同管理系统 - 数据库模型
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "contracts.sqlite3"


SCHEMA = """
-- 客户表
CREATE TABLE IF NOT EXISTS customer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    contact_person TEXT,
    phone TEXT,
    email TEXT,
    address TEXT,
    credit_level TEXT NOT NULL DEFAULT 'normal',  -- normal/gold/platinum/blacklist
    status TEXT NOT NULL DEFAULT 'active',  -- active/inactive
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 合同表
CREATE TABLE IF NOT EXISTS contract (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_no TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    customer_id INTEGER NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'CNY',
    sign_date TEXT,
    start_date TEXT,
    end_date TEXT,
    status TEXT NOT NULL DEFAULT 'draft',  -- draft/pending/approved/active/completed/terminated
    type TEXT NOT NULL DEFAULT 'sales',  -- sales/purchase/service/framework
    description TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Word文档相关字段
    document_file TEXT,  -- 文件名
    document_path TEXT,  -- 文件存储路径
    document_size INTEGER,  -- 文件大小(字节)
    document_hash TEXT,  -- 文件MD5哈希
    document_text TEXT,  -- 提取的文本内容
    FOREIGN KEY (customer_id) REFERENCES customer(id)
);

-- 付款计划表
CREATE TABLE IF NOT EXISTS payment_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    plan_no INTEGER NOT NULL,
    amount REAL NOT NULL,
    due_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending/paid/overdue/cancelled
    paid_amount REAL DEFAULT 0,
    paid_date TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contract_id) REFERENCES contract(id)
);

-- 发票表
CREATE TABLE IF NOT EXISTS invoice (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no TEXT NOT NULL UNIQUE,
    contract_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    tax_rate REAL NOT NULL DEFAULT 0.13,
    tax_amount REAL NOT NULL DEFAULT 0,
    total_amount REAL NOT NULL,
    issue_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending/sent/paid/void
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contract_id) REFERENCES contract(id)
);

-- 合同审批记录
CREATE TABLE IF NOT EXISTS approval_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    approver TEXT NOT NULL,
    action TEXT NOT NULL,  -- submit/approve/reject/return
    comment TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contract_id) REFERENCES contract(id)
);

-- 合同变更记录
CREATE TABLE IF NOT EXISTS change_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    change_type TEXT NOT NULL,  -- amount/term/status/other
    old_value TEXT,
    new_value TEXT,
    reason TEXT,
    changed_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contract_id) REFERENCES contract(id)
);
"""


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """初始化数据库"""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
    print(f"数据库已初始化: {DB_PATH}")


@contextmanager
def get_db():
    """数据库上下文管理器"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
