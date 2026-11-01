"""Read and write the operational CSV tables."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

TABLE_FILES = {
    "employees": "employees.csv",
    "vendors": "vendors.csv",
    "purchase_orders": "purchase_orders.csv",
    "invoices": "invoices.csv",
    "payments": "payments.csv",
    "employee_expenses": "employee_expenses.csv",
    "approval_records": "approval_records.csv",
}

DATE_COLUMNS = {
    "employees": ["hire_date"],
    "vendors": ["onboarding_date"],
    "purchase_orders": ["po_date"],
    "invoices": ["invoice_date", "due_date"],
    "payments": ["payment_date"],
    "employee_expenses": ["expense_date"],
    "approval_records": ["approval_date"],
}

TIMESTAMP_COLUMNS = {
    "invoices": ["submitted_at"],
    "employee_expenses": ["submitted_at"],
}

MONEY_COLUMNS = {
    "employees": ["approval_limit_inr"],
    "purchase_orders": ["po_amount_inr"],
    "invoices": ["unit_price_inr", "invoice_amount_inr", "tax_amount_inr", "total_amount_inr"],
    "payments": ["payment_amount_inr"],
    "employee_expenses": ["amount_inr"],
}

BOOL_COLUMNS = {
    "invoices": ["dispute_flag"],
    "employee_expenses": ["receipt_attached"],
}

PRIMARY_KEYS = {
    "employees": "employee_id",
    "vendors": "vendor_id",
    "purchase_orders": "po_id",
    "invoices": "invoice_id",
    "payments": "payment_id",
    "employee_expenses": "expense_id",
    "approval_records": "approval_id",
}


def write_table(frame: pd.DataFrame, path: Path, float_format: str = "%.2f") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, float_format=float_format)


def _as_bool(series: pd.Series) -> pd.Series:
    def convert(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return False
        return str(value).strip().lower() in {"true", "1", "yes", "y"}

    return series.map(convert)


def read_table(path: Path, table_name: str) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=True)
    for column in DATE_COLUMNS.get(table_name, []):
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.date
    for column in TIMESTAMP_COLUMNS.get(table_name, []):
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    for column in MONEY_COLUMNS.get(table_name, []):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in BOOL_COLUMNS.get(table_name, []):
        if column in frame.columns:
            frame[column] = _as_bool(frame[column])
    if table_name == "invoices" and "quantity" in frame.columns:
        frame["quantity"] = pd.to_numeric(frame["quantity"], errors="coerce")
    if table_name == "invoices" and "po_id" in frame.columns:
        frame["po_id"] = frame["po_id"].fillna("").astype(str).replace({"nan": ""})
    if table_name == "employees" and "manager_id" in frame.columns:
        frame["manager_id"] = frame["manager_id"].fillna("").astype(str).replace({"nan": ""})
    if table_name == "payments" and "invoice_id" in frame.columns:
        frame["invoice_id"] = frame["invoice_id"].fillna("").astype(str).replace({"nan": ""})
    return frame


def read_operational_tables(raw_dir: Path) -> dict[str, pd.DataFrame]:
    tables = {}
    for name, filename in TABLE_FILES.items():
        tables[name] = read_table(raw_dir / filename, name)
    return tables


def split_duplicate_keys(frame: pd.DataFrame, key: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep the first row for each key and return the extra copies separately.

    Excluded rows are written by the caller. They are not deleted from raw files.
    """
    duplicated = frame[key].duplicated(keep="first")
    return frame.loc[~duplicated].copy(), frame.loc[duplicated].copy()
