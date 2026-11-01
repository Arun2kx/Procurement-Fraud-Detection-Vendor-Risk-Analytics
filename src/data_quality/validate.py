"""Validate operational tables without deleting or repairing rows."""

from __future__ import annotations

import pandas as pd

from src.utils.frames import PRIMARY_KEYS

EMPLOYEE_STATUSES = {"Active", "Inactive"}
VENDOR_STATUSES = {"Active", "Suspended", "Inactive"}
PO_STATUSES = {"Approved", "Closed", "Pending", "Rejected"}
INVOICE_STATUSES = {"Submitted", "Approved", "Paid", "Disputed", "Rejected"}
PAYMENT_STATUSES = {"Completed", "Reversed", "Failed"}
EXPENSE_STATUSES = {"Submitted", "Approved", "Reimbursed", "Rejected"}
APPROVAL_DECISIONS = {"Approved", "Rejected", "Returned"}
ENTITY_TYPES = {"purchase_order", "invoice", "employee_expense"}


def _failure(check_id: str, table: str, record_id: str, column: str, reason: str) -> dict:
    return {
        "check_id": check_id,
        "table_name": table,
        "record_id": record_id,
        "column_name": column,
        "reason": reason,
    }


def _ids(frame: pd.DataFrame, column: str) -> set[str]:
    if column not in frame.columns:
        return set()
    return {str(value) for value in frame[column].dropna() if str(value) not in {"", "nan", "None"}}


def validate_tables(tables: dict[str, pd.DataFrame], config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return one row per check and one row per failed record."""
    failures: list[dict] = []
    as_of = pd.Timestamp(config["analysis_as_of"])
    employees = tables["employees"]
    vendors = tables["vendors"]
    orders = tables["purchase_orders"]
    invoices = tables["invoices"]
    payments = tables["payments"]
    expenses = tables["employee_expenses"]
    approvals = tables["approval_records"]

    for column, check_id, reason in (
        ("email", "NULL_EMPLOYEE_EMAIL", "Employee email is missing."),
        ):
        missing = employees[employees[column].isna() | (employees[column].astype(str).str.strip() == "")]
        for record_id in missing["employee_id"]:
            failures.append(_failure(check_id, "employees", str(record_id), column, reason))

    missing_city = vendors[vendors["city"].isna() | (vendors["city"].astype(str).str.strip() == "")]
    for record_id in missing_city["vendor_id"]:
        failures.append(_failure("NULL_VENDOR_CITY", "vendors", str(record_id), "city", "Vendor city is missing."))

    for table_name, frame in tables.items():
        key = PRIMARY_KEYS[table_name]
        duplicated = frame[frame[key].duplicated(keep=False)]
        for record_id in duplicated[key]:
            failures.append(_failure("DUPLICATE_PRIMARY_KEY", table_name, str(record_id), key, "Primary key value is repeated."))

    for table_name, frame, columns in (
        ("purchase_orders", orders, ["po_amount_inr"]),
        ("invoices", invoices, ["unit_price_inr", "invoice_amount_inr", "tax_amount_inr", "total_amount_inr"]),
        ("payments", payments, ["payment_amount_inr"]),
        ("employee_expenses", expenses, ["amount_inr"]),
    ):
        key = PRIMARY_KEYS[table_name]
        for column in columns:
            negative = frame[pd.to_numeric(frame[column], errors="coerce") < 0]
            for record_id in negative[key]:
                failures.append(_failure("NEGATIVE_AMOUNT", table_name, str(record_id), column, "Amount is negative."))

    invoice_dates = pd.to_datetime(invoices["invoice_date"], errors="coerce")
    due_dates = pd.to_datetime(invoices["due_date"], errors="coerce")
    bad_due = invoices[due_dates.notna() & invoice_dates.notna() & (due_dates < invoice_dates)]
    for record_id in bad_due["invoice_id"]:
        failures.append(_failure("INVALID_DATE_SEQUENCE", "invoices", str(record_id), "due_date", "Due date is before the invoice date."))

    expense_dates = pd.to_datetime(expenses["expense_date"], errors="coerce")
    out_of_range = expenses[expense_dates.notna() & ((expense_dates < pd.Timestamp(config["date_range"]["start"])) | (expense_dates > as_of))]
    for record_id in out_of_range["expense_id"]:
        failures.append(_failure("OUT_OF_RANGE_DATE", "employee_expenses", str(record_id), "expense_date", "Expense date is outside the analysis window."))

    hire = employees[["employee_id", "hire_date"]].copy()
    hire["hire_date"] = pd.to_datetime(hire["hire_date"], errors="coerce")
    expense_hire = expenses.merge(hire, on="employee_id", how="left")
    expense_hire["expense_date"] = pd.to_datetime(expense_hire["expense_date"], errors="coerce")
    before_hire = expense_hire[expense_hire["expense_date"].notna() & expense_hire["hire_date"].notna() & (expense_hire["expense_date"] < expense_hire["hire_date"])]
    for record_id in before_hire["expense_id"]:
        failures.append(_failure("TRANSACTION_BEFORE_HIRE", "employee_expenses", str(record_id), "expense_date", "Expense date is before the employee hire date."))

    vendor_ids = _ids(vendors.drop_duplicates("vendor_id"), "vendor_id")
    employee_ids = _ids(employees.drop_duplicates("employee_id"), "employee_id")
    po_ids = _ids(orders.drop_duplicates("po_id"), "po_id")
    invoice_ids = _ids(invoices.drop_duplicates("invoice_id"), "invoice_id")
    expense_ids = _ids(expenses.drop_duplicates("expense_id"), "expense_id")

    for _, row in invoices.iterrows():
        if str(row["vendor_id"]) not in vendor_ids:
            failures.append(_failure("ORPHAN_VENDOR", "invoices", str(row["invoice_id"]), "vendor_id", "Vendor does not exist."))
        po_id = str(row["po_id"]) if pd.notna(row["po_id"]) else ""
        if po_id not in {"", "nan", "None"} and po_id not in po_ids:
            failures.append(_failure("ORPHAN_PO_REFERENCE", "invoices", str(row["invoice_id"]), "po_id", "Purchase order does not exist."))
    for _, row in orders.iterrows():
        if str(row["vendor_id"]) not in vendor_ids:
            failures.append(_failure("ORPHAN_VENDOR", "purchase_orders", str(row["po_id"]), "vendor_id", "Vendor does not exist."))
        if str(row["requestor_employee_id"]) not in employee_ids:
            failures.append(_failure("ORPHAN_EMPLOYEE", "purchase_orders", str(row["po_id"]), "requestor_employee_id", "Requestor does not exist."))
    for _, row in payments.iterrows():
        if str(row["vendor_id"]) not in vendor_ids:
            failures.append(_failure("ORPHAN_VENDOR", "payments", str(row["payment_id"]), "vendor_id", "Vendor does not exist."))
        invoice_id = str(row["invoice_id"]) if pd.notna(row["invoice_id"]) else ""
        if invoice_id not in invoice_ids:
            failures.append(_failure("ORPHAN_INVOICE_REFERENCE", "payments", str(row["payment_id"]), "invoice_id", "Invoice does not exist."))
    for _, row in expenses.iterrows():
        if str(row["employee_id"]) not in employee_ids:
            failures.append(_failure("ORPHAN_EMPLOYEE", "employee_expenses", str(row["expense_id"]), "employee_id", "Employee does not exist."))
    for _, row in approvals.iterrows():
        if str(row["approver_employee_id"]) not in employee_ids:
            failures.append(_failure("ORPHAN_EMPLOYEE", "approval_records", str(row["approval_id"]), "approver_employee_id", "Approver does not exist."))
        entity_type = str(row["entity_type"])
        entity_id = str(row["entity_id"])
        populations = {
            "purchase_order": po_ids,
            "invoice": invoice_ids,
            "employee_expense": expense_ids,
        }
        if entity_type not in populations or entity_id not in populations.get(entity_type, set()):
            failures.append(_failure("ORPHAN_APPROVAL_ENTITY", "approval_records", str(row["approval_id"]), "entity_id", "Approved entity does not exist."))

    _categorical(failures, employees, "employee_id", "employment_status", EMPLOYEE_STATUSES, "employees")
    _categorical(failures, vendors, "vendor_id", "vendor_status", VENDOR_STATUSES, "vendors")
    _categorical(failures, orders, "po_id", "status", PO_STATUSES, "purchase_orders")
    _categorical(failures, invoices, "invoice_id", "status", INVOICE_STATUSES, "invoices")
    _categorical(failures, payments, "payment_id", "status", PAYMENT_STATUSES, "payments")
    _categorical(failures, expenses, "expense_id", "status", EXPENSE_STATUSES, "employee_expenses")
    _categorical(failures, approvals, "approval_id", "decision", APPROVAL_DECISIONS, "approval_records")
    _categorical(failures, approvals, "approval_id", "entity_type", ENTITY_TYPES, "approval_records")

    bank_counts = vendors["bank_account_hash"].value_counts()
    duplicated_hashes = set(bank_counts[bank_counts > 1].index.astype(str))
    for _, row in vendors[vendors["bank_account_hash"].astype(str).isin(duplicated_hashes)].iterrows():
        failures.append(_failure("DUPLICATE_BANK_HASH", "vendors", str(row["vendor_id"]), "bank_account_hash", "Bank-account hash is shared by more than one vendor."))

    math_gap = (
        pd.to_numeric(invoices["invoice_amount_inr"], errors="coerce").fillna(0)
        + pd.to_numeric(invoices["tax_amount_inr"], errors="coerce").fillna(0)
        - pd.to_numeric(invoices["total_amount_inr"], errors="coerce").fillna(0)
    ).abs()
    for record_id in invoices.loc[math_gap > 0.05, "invoice_id"]:
        failures.append(_failure("INVOICE_MATH_MISMATCH", "invoices", str(record_id), "total_amount_inr", "Invoice total does not equal taxable amount plus tax."))

    failure_frame = pd.DataFrame(failures)
    if failure_frame.empty:
        failure_frame = pd.DataFrame(columns=["check_id", "table_name", "record_id", "column_name", "reason"])
    else:
        failure_frame = failure_frame.drop_duplicates().sort_values(["check_id", "table_name", "record_id"]).reset_index(drop=True)

    summary = (
        failure_frame.groupby(["check_id", "table_name"], as_index=False)
        .size()
        .rename(columns={"size": "failure_count"})
    )
    expected = pd.DataFrame(
        [
            ("NULL_EMPLOYEE_EMAIL", "employees"),
            ("NULL_VENDOR_CITY", "vendors"),
            ("DUPLICATE_PRIMARY_KEY", "employees"),
            ("DUPLICATE_PRIMARY_KEY", "vendors"),
            ("DUPLICATE_PRIMARY_KEY", "purchase_orders"),
            ("DUPLICATE_PRIMARY_KEY", "invoices"),
            ("DUPLICATE_PRIMARY_KEY", "payments"),
            ("DUPLICATE_PRIMARY_KEY", "employee_expenses"),
            ("DUPLICATE_PRIMARY_KEY", "approval_records"),
            ("NEGATIVE_AMOUNT", "invoices"),
            ("NEGATIVE_AMOUNT", "employee_expenses"),
            ("NEGATIVE_AMOUNT", "payments"),
            ("NEGATIVE_AMOUNT", "purchase_orders"),
            ("INVALID_DATE_SEQUENCE", "invoices"),
            ("OUT_OF_RANGE_DATE", "employee_expenses"),
            ("TRANSACTION_BEFORE_HIRE", "employee_expenses"),
            ("ORPHAN_VENDOR", "invoices"),
            ("ORPHAN_PO_REFERENCE", "invoices"),
            ("ORPHAN_VENDOR", "purchase_orders"),
            ("ORPHAN_EMPLOYEE", "purchase_orders"),
            ("ORPHAN_VENDOR", "payments"),
            ("ORPHAN_INVOICE_REFERENCE", "payments"),
            ("ORPHAN_EMPLOYEE", "employee_expenses"),
            ("ORPHAN_EMPLOYEE", "approval_records"),
            ("ORPHAN_APPROVAL_ENTITY", "approval_records"),
            ("INVALID_CATEGORY", "employees"),
            ("INVALID_CATEGORY", "vendors"),
            ("INVALID_CATEGORY", "invoices"),
            ("DUPLICATE_BANK_HASH", "vendors"),
            ("INVOICE_MATH_MISMATCH", "invoices"),
        ],
        columns=["check_id", "table_name"],
    )
    summary = expected.merge(summary, on=["check_id", "table_name"], how="left")
    summary["failure_count"] = summary["failure_count"].fillna(0).astype(int)
    summary["passed"] = summary["failure_count"] == 0
    summary["pass_rate_contribution"] = summary["passed"].astype(int)
    return summary.sort_values(["check_id", "table_name"]).reset_index(drop=True), failure_frame


def _categorical(failures: list[dict], frame: pd.DataFrame, key: str, column: str, allowed: set[str], table: str) -> None:
    invalid = frame[~frame[column].astype(str).isin(allowed)]
    for record_id in invalid[key]:
        failures.append(_failure("INVALID_CATEGORY", table, str(record_id), column, f"Value is outside the allowed list: {', '.join(sorted(allowed))}."))


def pass_rate(summary: pd.DataFrame) -> float:
    if summary.empty:
        return 0.0
    return float(summary["passed"].mean())
