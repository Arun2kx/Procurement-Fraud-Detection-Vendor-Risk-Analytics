"""Load synthetic CSV files into PostgreSQL without dropping tables.

Connection details come from the DATABASE_URL environment variable.
This module does not embed a password.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from src.utils.frames import PRIMARY_KEYS, TABLE_FILES, read_operational_tables

LOAD_ORDER = [
    "employees",
    "vendors",
    "purchase_orders",
    "invoices",
    "payments",
    "employee_expenses",
    "approval_records",
]


def database_url(config: dict) -> str:
    env_name = config["database"]["url_env"]
    url = os.environ.get(env_name, "").strip()
    if not url:
        raise RuntimeError(
            f"Set {env_name} to a SQLAlchemy PostgreSQL URL before ingestion. "
            f"Example shape: {config['database']['example_url']}"
        )
    return url


def split_sql(script: str) -> list[str]:
    """Split a script on semicolons that are outside dollar-quoted function bodies."""
    statements: list[str] = []
    current: list[str] = []
    index = 0
    dollar = None
    while index < len(script):
        if dollar is None and script.startswith("--", index):
            newline = script.find("\n", index)
            index = len(script) if newline == -1 else newline + 1
            continue
        if script.startswith("$$", index):
            current.append("$$")
            index += 2
            dollar = None if dollar else "$$"
            continue
        if dollar is None and script[index] == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            index += 1
            continue
        current.append(script[index])
        index += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def execute_sql_file(engine: Engine, path: Path) -> None:
    """Run a script through the DBAPI cursor so PostgreSQL percent signs stay literal."""
    statements = split_sql(path.read_text(encoding="utf-8"))
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        for statement in statements:
            cursor.execute(statement)
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def create_schema(engine: Engine, schema_path: Path) -> None:
    execute_sql_file(engine, schema_path)


def _prepare_frame(table_name: str, frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    for column in prepared.columns:
        if prepared[column].dtype == object:
            prepared[column] = prepared[column].apply(lambda value: None if pd.isna(value) or str(value).strip() in {"", "nan", "None", "NaT"} else value)
    if table_name == "employees" and "manager_id" in prepared.columns:
        prepared["manager_id"] = prepared["manager_id"].apply(lambda value: None if value in {None, ""} else value)
    if "quantity" in prepared.columns:
        prepared["quantity"] = prepared["quantity"].apply(lambda value: None if value is None or pd.isna(value) else int(value))
    return prepared


def _existing_rows(engine: Engine, table_name: str) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())


def load_tables(engine: Engine, tables: dict[str, pd.DataFrame], rejection_path: Path) -> pd.DataFrame:
    """Insert rows one by one so a constraint failure is logged rather than hidden."""
    rejections = []
    for table_name in LOAD_ORDER:
        if _existing_rows(engine, table_name) > 0:
            raise RuntimeError(
                f"{table_name} already contains rows. ProcureGuard will not truncate it. Use an empty database."
            )
        frame = _prepare_frame(table_name, tables[table_name])
        columns = list(frame.columns)
        statement = text(
            f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(':' + column for column in columns)})"
        )
        # One transaction per table lets DEFERRABLE manager keys see later rows.
        # A failed row rolls back only its savepoint and stays in the rejection log.
        with engine.begin() as connection:
            for record in frame.to_dict("records"):
                try:
                    with connection.begin_nested():
                        connection.execute(statement, record)
                except SQLAlchemyError as exc:
                    key = PRIMARY_KEYS[table_name]
                    rejections.append(
                        {
                            "table_name": table_name,
                            "record_id": record.get(key),
                            "reason": str(exc).splitlines()[0][:500],
                        }
                    )
    rejection_frame = pd.DataFrame(rejections)
    rejection_path.parent.mkdir(parents=True, exist_ok=True)
    if rejection_frame.empty:
        rejection_frame = pd.DataFrame(columns=["table_name", "record_id", "reason"])
    rejection_frame.to_csv(rejection_path, index=False)
    return rejection_frame


def verify_counts(engine: Engine, tables: dict[str, pd.DataFrame], rejections: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for table_name in LOAD_ORDER:
        raw_count = int(len(tables[table_name]))
        loaded = _existing_rows(engine, table_name)
        rejected = int((rejections["table_name"] == table_name).sum()) if not rejections.empty else 0
        rows.append(
            {
                "table_name": table_name,
                "raw_rows": raw_count,
                "loaded_rows": loaded,
                "rejected_rows": rejected,
                "reconciled": raw_count == loaded + rejected,
            }
        )
    result = pd.DataFrame(rows)
    if not bool(result["reconciled"].all()):
        raise RuntimeError("Ingestion counts do not reconcile to the raw files:\n" + result.to_string(index=False))
    return result


def ingest(config: dict, raw_dir: Path, schema_path: Path, rejection_path: Path) -> pd.DataFrame:
    engine = create_engine(database_url(config))
    create_schema(engine, schema_path)
    tables = read_operational_tables(raw_dir)
    rejections = load_tables(engine, tables, rejection_path)
    counts = verify_counts(engine, tables, rejections)
    engine.dispose()
    return counts


def apply_analytics_sql(config: dict, database_dir: Path) -> None:
    engine = create_engine(database_url(config))
    for path in sorted(database_dir.glob("[0-9][0-9]_*.sql")):
        if path.name.startswith("01_"):
            continue
        execute_sql_file(engine, path)
    engine.dispose()


def load_alert_log(config: dict, alerts: pd.DataFrame) -> int:
    """Load the Python alert log if the audit table is empty."""
    if alerts.empty:
        return 0
    engine = create_engine(database_url(config))
    if _existing_rows(engine, "audit_alerts_log") > 0:
        engine.dispose()
        raise RuntimeError("audit_alerts_log already contains rows. ProcureGuard will not truncate it.")
    frame = alerts.copy()
    frame["risk_score"] = pd.to_numeric(frame["risk_score"], errors="coerce")
    frame = frame.astype(object).where(pd.notna(frame), None)
    frame.to_sql("audit_alerts_log", engine, if_exists="append", index=False)
    engine.dispose()
    return int(len(frame))
