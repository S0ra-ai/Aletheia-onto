"""
合同管理系统 - 测试数据生成
"""
import hashlib
import os
from pathlib import Path
from database import get_db, init_db
from datetime import datetime, timedelta
import random

DOCUMENTS_DIR = Path(__file__).parent.parent / "documents"


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


def generate_test_data():
    """生成测试数据"""
    init_db()

    with get_db() as conn:
        # 清空现有数据
        conn.execute("DELETE FROM change_record")
        conn.execute("DELETE FROM approval_record")
        conn.execute("DELETE FROM invoice")
        conn.execute("DELETE FROM payment_plan")
        conn.execute("DELETE FROM contract")
        conn.execute("DELETE FROM customer")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('customer', 'contract', 'payment_plan', 'invoice', 'approval_record', 'change_record')")

        # ==================== 客户数据 ====================
        customers = [
            ("北京科技有限公司", "CUS-001", "张三", "13800138001", "zhangsan@bjtech.com", "北京市朝阳区建国路88号", "gold"),
            ("上海贸易有限公司", "CUS-002", "李四", "13800138002", "lisi@shtrade.com", "上海市浦东新区陆家嘴金融中心", "platinum"),
            ("深圳电子有限公司", "CUS-003", "王五", "13800138003", "wangwu@szelec.com", "深圳市南山区科技园", "normal"),
            ("广州制造有限公司", "CUS-004", "赵六", "13800138004", "zhaoliu@gzmaker.com", "广州市天河区珠江新城", "normal"),
            ("杭州软件有限公司", "CUS-005", "钱七", "13800138005", "qianqi@hzsoft.com", "杭州市西湖区文三路", "gold"),
            ("黑名单企业", "CUS-006", "孙八", "13800138006", "sunba@blacklist.com", "某地某路某号", "blacklist"),
        ]

        for name, code, contact, phone, email, address, credit in customers:
            conn.execute(
                "INSERT INTO customer (name, code, contact_person, phone, email, address, credit_level) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, code, contact, phone, email, address, credit),
            )

        # ==================== 合同数据（包含文档信息）====================
        # 映射合同编号到Word文档文件名
        document_mapping = {
            "HT-2024-001": "HT-2024-001_年度技术服务合同.docx",
            "HT-2024-002": "HT-2024-002_软件采购合同.docx",
            "HT-2024-006": "HT-2024-006_风险合同_黑名单客户.docx",
            "HT-2024-007": "HT-2024-007_逾期合同示例.docx",
            "HT-2024-008": "HT-2024-008_框架合作协议.docx",
        }

        contracts = [
            ("HT-2024-001", "年度技术服务合同", 1, 500000, "2024-01-15", "2024-01-15", "2024-12-31", "active", "service", "提供全年技术支持服务"),
            ("HT-2024-002", "软件采购合同", 2, 1200000, "2024-02-20", "2024-03-01", "2025-02-28", "active", "sales", "采购企业级软件授权"),
            ("HT-2024-003", "设备维护合同", 3, 180000, "2024-03-10", "2024-04-01", "2025-03-31", "pending", "service", "设备年度维护服务"),
            ("HT-2024-004", "原材料采购合同", 4, 850000, "2024-04-05", "2024-04-10", "2024-10-10", "completed", "purchase", "采购生产原材料"),
            ("HT-2024-005", "系统开发合同", 5, 350000, "2024-05-18", "2024-06-01", "2024-12-31", "active", "service", "定制化系统开发"),
            ("HT-2024-006", "风险合同-黑名单客户", 6, 200000, "2024-06-01", "2024-06-15", "2024-12-31", "active", "sales", "注意：此合同涉及黑名单客户"),
            ("HT-2024-007", "逾期合同示例", 1, 450000, "2024-01-20", "2024-02-01", "2024-06-30", "active", "sales", "此合同有逾期付款情况"),
            ("HT-2024-008", "框架合同", 2, 2000000, "2024-07-01", "2024-07-01", "2026-06-30", "draft", "framework", "长期框架协议"),
        ]

        for contract_no, title, customer_id, amount, sign_date, start_date, end_date, status, ctype, desc in contracts:
            # 获取文档信息
            doc_file = document_mapping.get(contract_no)
            doc_path = None
            doc_size = None
            doc_hash = None
            doc_text = None
            
            if doc_file:
                full_path = DOCUMENTS_DIR / doc_file
                if full_path.exists():
                    doc_path = str(full_path)
                    doc_size = full_path.stat().st_size
                    doc_hash = calculate_file_hash(str(full_path))
                    doc_text = extract_text_from_docx(str(full_path))
            
            conn.execute(
                """INSERT INTO contract (contract_no, title, customer_id, amount, sign_date, start_date, end_date, status, type, description, created_by,
                document_file, document_path, document_size, document_hash, document_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (contract_no, title, customer_id, amount, sign_date, start_date, end_date, status, ctype, desc, "admin",
                 doc_file, doc_path, doc_size, doc_hash, doc_text),
            )

        # ==================== 付款计划数据 ====================
        payment_plans = [
            # HT-2024-001 的付款计划
            (1, 1, 150000, "2024-02-15", "paid", 150000),
            (1, 2, 150000, "2024-05-15", "paid", 150000),
            (1, 3, 100000, "2024-08-15", "pending", 0),
            (1, 4, 100000, "2024-11-15", "pending", 0),
            # HT-2024-002 的付款计划
            (2, 1, 600000, "2024-03-01", "paid", 600000),
            (2, 2, 600000, "2024-09-01", "pending", 0),
            # HT-2024-004 的付款计划（已完成）
            (4, 1, 425000, "2024-05-10", "paid", 425000),
            (4, 2, 425000, "2024-08-10", "paid", 425000),
            # HT-2024-007 的付款计划（有逾期）
            (7, 1, 150000, "2024-03-01", "paid", 150000),
            (7, 2, 150000, "2024-06-01", "overdue", 0),
            (7, 3, 150000, "2024-09-01", "pending", 0),
        ]

        for contract_id, plan_no, amount, due_date, status, paid_amount in payment_plans:
            paid_date = due_date if status == "paid" else None
            conn.execute(
                "INSERT INTO payment_plan (contract_id, plan_no, amount, due_date, status, paid_amount, paid_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (contract_id, plan_no, amount, due_date, status, paid_amount, paid_date),
            )

        # ==================== 发票数据 ====================
        invoices = [
            ("INV-20240215001", 1, 150000, 0.13, 19500, 169500, "2024-02-15", "paid"),
            ("INV-20240515001", 1, 150000, 0.13, 19500, 169500, "2024-05-15", "paid"),
            ("INV-20240301001", 2, 600000, 0.13, 78000, 678000, "2024-03-01", "paid"),
            ("INV-20240510001", 4, 425000, 0.13, 55250, 480250, "2024-05-10", "paid"),
            ("INV-20240810001", 4, 425000, 0.13, 55250, 480250, "2024-08-10", "paid"),
            ("INV-20240601001", 7, 150000, 0.13, 19500, 169500, "2024-06-01", "sent"),
        ]

        for invoice_no, contract_id, amount, tax_rate, tax_amount, total_amount, issue_date, status in invoices:
            conn.execute(
                "INSERT INTO invoice (invoice_no, contract_id, amount, tax_rate, tax_amount, total_amount, issue_date, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (invoice_no, contract_id, amount, tax_rate, tax_amount, total_amount, issue_date, status),
            )

        # ==================== 审批记录 ====================
        approvals = [
            (3, "admin", "submit", "提交审批"),
            (8, "admin", "submit", "提交审批"),
        ]

        for contract_id, approver, action, comment in approvals:
            conn.execute(
                "INSERT INTO approval_record (contract_id, approver, action, comment) VALUES (?, ?, ?, ?)",
                (contract_id, approver, action, comment),
            )

    print("测试数据生成完成！")
    print(f"  - 客户: {len(customers)} 条")
    print(f"  - 合同: {len(contracts)} 条")
    print(f"  - 付款计划: {len(payment_plans)} 条")
    print(f"  - 发票: {len(invoices)} 条")
    print(f"  - 审批记录: {len(approvals)} 条")
    print(f"  - Word文档: {len(document_mapping)} 个")


if __name__ == "__main__":
    generate_test_data()
