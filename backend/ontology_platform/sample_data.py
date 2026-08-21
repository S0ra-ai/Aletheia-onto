from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_SAMPLE_DB = Path("data") / "legacy_contracts.sqlite3"
DEFAULT_EQUIPMENT_SAMPLE_DB = Path("data") / "legacy_equipment.sqlite3"


def create_contract_sample_db(db_path: Path | str = DEFAULT_SAMPLE_DB) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        path.unlink()

    with sqlite3.connect(path) as conn:
        conn.execute("pragma foreign_keys = on")
        conn.executescript(
            """
            create table customer (
                id integer primary key,
                customer_name text not null,
                credit_status text not null,
                industry text,
                created_at text not null
            );

            create table contract (
                id integer primary key,
                contract_no text not null unique,
                customer_id integer not null references customer(id),
                title text not null,
                amount real not null,
                status text not null,
                signed_date text,
                effective_date text,
                end_date text
            );

            create table payment_plan (
                id integer primary key,
                contract_id integer not null references contract(id),
                plan_no text not null,
                due_date text not null,
                planned_amount real not null,
                paid_amount real not null default 0,
                paid_date text,
                status text not null
            );

            create table invoice (
                id integer primary key,
                contract_id integer not null references contract(id),
                invoice_no text not null unique,
                invoice_amount real not null,
                issued_date text not null,
                status text not null
            );
            """
        )
        conn.executemany(
            "insert into customer values (?, ?, ?, ?, ?)",
            [
                (1, "华东能源集团", "normal", "energy", "2025-01-10"),
                (2, "北辰制造有限公司", "watch", "manufacturing", "2025-02-18"),
                (3, "远海贸易公司", "blacklist", "trade", "2025-03-22"),
            ],
        )
        conn.executemany(
            "insert into contract values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    1,
                    "HT-2026-001",
                    1,
                    "能源设备年度维保合同",
                    1200000,
                    "effective",
                    "2026-01-05",
                    "2026-01-10",
                    "2026-12-31",
                ),
                (2, "HT-2026-002", 2, "产线升级项目合同", 800000, "approval", None, None, "2026-10-31"),
                (3, "HT-2026-003", 3, "贸易服务框架合同", 300000, "draft", None, None, "2026-09-30"),
            ],
        )
        conn.executemany(
            "insert into payment_plan values (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (1, 1, "PAY-001-1", "2026-03-31", 400000, 400000, "2026-03-20", "paid"),
                (2, 1, "PAY-001-2", "2026-06-30", 400000, 0, None, "overdue"),
                (3, 1, "PAY-001-3", "2026-12-31", 400000, 0, None, "pending"),
                (4, 2, "PAY-002-1", "2026-05-31", 800000, 0, None, "pending"),
            ],
        )
        conn.executemany(
            "insert into invoice values (?, ?, ?, ?, ?, ?)",
            [
                (1, 1, "INV-2026-001", 400000, "2026-03-15", "issued"),
                (2, 1, "INV-2026-002", 400000, "2026-06-15", "issued"),
            ],
        )

    return path


def create_equipment_sample_db(db_path: Path | str = DEFAULT_EQUIPMENT_SAMPLE_DB) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        path.unlink()

    with sqlite3.connect(path) as conn:
        conn.execute("pragma foreign_keys = on")
        conn.executescript(
            """
            create table equipment (
                id integer primary key,
                equipment_code text not null unique,
                equipment_name text not null,
                location text not null,
                criticality text not null,
                status text not null
            );

            create table work_order (
                id integer primary key,
                work_order_no text not null unique,
                equipment_id integer not null references equipment(id),
                fault_description text not null,
                reported_at text not null,
                closed_at text,
                status text not null
            );

            create table inspection_record (
                id integer primary key,
                equipment_id integer not null references equipment(id),
                inspection_date text not null,
                result text not null,
                status text not null
            );

            create table spare_part (
                id integer primary key,
                part_code text not null unique,
                part_name text not null,
                stock_quantity integer not null,
                minimum_quantity integer not null,
                status text not null
            );
            """
        )
        conn.executemany(
            "insert into equipment values (?, ?, ?, ?, ?, ?)",
            [
                (1, "EQ-001", "一号空压机", "A 车间", "high", "running"),
                (2, "EQ-002", "二号输送线", "B 车间", "medium", "maintenance"),
            ],
        )
        conn.executemany(
            "insert into work_order values (?, ?, ?, ?, ?, ?, ?)",
            [
                (1, "WO-2026-001", 1, "运行温度异常升高", "2026-07-01 09:30:00", None, "open"),
                (2, "WO-2026-002", 2, "例行保养", "2026-06-20 14:00:00", "2026-06-21 10:00:00", "closed"),
            ],
        )
        conn.executemany(
            "insert into inspection_record values (?, ?, ?, ?, ?)",
            [
                (1, 1, "2026-07-01", "temperature_high", "abnormal"),
                (2, 2, "2026-07-01", "normal", "closed"),
            ],
        )
        conn.executemany(
            "insert into spare_part values (?, ?, ?, ?, ?, ?)",
            [
                (1, "SP-001", "滤芯", 12, 5, "available"),
                (2, "SP-002", "轴承", 2, 6, "low_stock"),
            ],
        )

    return path
