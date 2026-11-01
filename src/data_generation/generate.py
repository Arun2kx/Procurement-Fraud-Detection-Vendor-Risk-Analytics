"""Generate the synthetic ProcureGuard procurement population.

Every record is fictional. Pattern labels are written only to the evaluation
folder. Screening code does not read that folder.
"""

from __future__ import annotations

import hashlib
import json
import math
from calendar import monthrange
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

from src.data_generation.catalogs import (
    CITY_STATE,
    DEPARTMENTS,
    EXPENSE_CATEGORIES,
    ITEM_CATALOG,
    JOB_LIMITS,
    VENDOR_CATEGORIES,
)
from src.utils.frames import TABLE_FILES, write_table
from src.utils.money import line_amounts, money

EMPLOYEE_COLUMNS = [
    "employee_id",
    "full_name",
    "email",
    "department",
    "job_title",
    "job_level",
    "manager_id",
    "approval_limit_inr",
    "hire_date",
    "employment_status",
    "city",
]
VENDOR_COLUMNS = [
    "vendor_id",
    "vendor_name",
    "vendor_category",
    "gstin",
    "city",
    "state",
    "bank_account_hash",
    "onboarding_date",
    "vendor_status",
    "contact_email",
    "payment_terms_days",
]
PO_COLUMNS = [
    "po_id",
    "vendor_id",
    "requestor_employee_id",
    "department",
    "category",
    "po_date",
    "po_amount_inr",
    "currency",
    "status",
    "description",
]
INVOICE_COLUMNS = [
    "invoice_id",
    "invoice_number",
    "vendor_id",
    "po_id",
    "invoice_date",
    "due_date",
    "item_code",
    "item_description",
    "quantity",
    "unit_price_inr",
    "invoice_amount_inr",
    "tax_amount_inr",
    "total_amount_inr",
    "currency",
    "status",
    "dispute_flag",
    "description",
    "submitted_at",
]
PAYMENT_COLUMNS = [
    "payment_id",
    "invoice_id",
    "vendor_id",
    "payment_date",
    "payment_amount_inr",
    "currency",
    "payment_method",
    "payment_reference",
    "status",
]
EXPENSE_COLUMNS = [
    "expense_id",
    "employee_id",
    "expense_date",
    "submitted_at",
    "category",
    "amount_inr",
    "currency",
    "description",
    "receipt_attached",
    "status",
]
APPROVAL_COLUMNS = [
    "approval_id",
    "entity_type",
    "entity_id",
    "approver_employee_id",
    "approval_date",
    "decision",
    "approval_level",
    "comments",
]
LABEL_COLUMNS = [
    "label_id",
    "entity_type",
    "entity_id",
    "pattern_code",
    "is_suspicious",
    "is_benign_control",
    "is_data_quality_defect",
    "pattern_description",
    "related_entity_ids",
]


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def bank_hash(token: str) -> str:
    return hashlib.sha256(f"SYNTHETIC-ACCOUNT-{token}".encode()).hexdigest()


class IdFactory:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def next(self, prefix: str, width: int) -> str:
        self._counts[prefix] = self._counts.get(prefix, 0) + 1
        return f"{prefix}{self._counts[prefix]:0{width}d}"


class SyntheticProcurementGenerator:
    """Build a reproducible synthetic procure-to-pay population."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.seed = int(config["random_seed"])
        self.rng = np.random.default_rng(self.seed)
        Faker.seed(self.seed)
        self.fake = Faker("en_IN")
        self.fake.seed_instance(self.seed)
        self.ids = IdFactory()
        self.start = date.fromisoformat(config["date_range"]["start"])
        self.end = date.fromisoformat(config["date_range"]["end"])
        self.gst = float(config["gst_rate"])
        self.labels: list[dict] = []
        self.po_mode: dict[str, str] = {}
        self.protected_invoices: set[str] = set()
        self.protected_pos: set[str] = set()
        self.protected_expenses: set[str] = set()
        self.self_approve_expenses: set[str] = set()
        self.series: dict[str, int] = {}
        self.abbr: dict[str, str] = {}
        self.used_abbr: set[str] = set()
        self.last_dates: dict[tuple[str, str, str], date] = {}
        self.employees: list[dict] = []
        self.vendors: list[dict] = []
        self.purchase_orders: list[dict] = []
        self.invoices: list[dict] = []
        self.payments: list[dict] = []
        self.expenses: list[dict] = []
        self.approvals: list[dict] = []
        self.roles: dict[str, list[str]] = {}
        self.director_id = ""
        self.invalid_employee_id = ""
        self.invalid_vendor_id = ""

    def build(self) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict]:
        self._build_employees()
        self._build_vendors()
        self._build_planted_purchases()
        self._build_ordinary_purchases()
        self._top_up_invoices()
        self._apply_disputes()
        self._apply_invoice_defects()
        self._apply_master_data_defects()
        self._build_payments()
        self._build_expenses()
        self._build_approvals()
        tables = self._frames()
        labels = self._label_frame()
        summary = self._summary(tables, labels)
        self._assert_shape(tables)
        return tables, labels, summary

    def add_label(
        self,
        entity_type: str,
        entity_id: str,
        code: str,
        description: str,
        *,
        suspicious: bool = False,
        benign: bool = False,
        defect: bool = False,
        related: list[str] | None = None,
    ) -> None:
        self.labels.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "pattern_code": code,
                "is_suspicious": suspicious,
                "is_benign_control": benign,
                "is_data_quality_defect": defect,
                "pattern_description": description,
                "related_entity_ids": "|".join(sorted(set(related or []))),
            }
        )

    def pick(self, items: list):
        if not items:
            raise RuntimeError("Tried to choose from an empty list.")
        return items[int(self.rng.integers(0, len(items)))]

    def draw(self, items: list, count: int) -> tuple[list, list]:
        if len(items) < count:
            raise RuntimeError(f"Need {count} rows but only {len(items)} are available.")
        chosen_idx = sorted(int(value) for value in self.rng.choice(len(items), size=count, replace=False))
        chosen_set = set(chosen_idx)
        chosen = [items[index] for index in chosen_idx]
        remaining = [item for index, item in enumerate(items) if index not in chosen_set]
        return chosen, remaining

    def _date_between(self, start: date | None = None, end: date | None = None) -> date:
        start = start or self.start
        end = end or self.end
        span = (end - start).days
        return start + timedelta(days=int(self.rng.integers(0, span + 1)))

    def _lognormal(self, median: float, sigma: float, low: float, high: float) -> float:
        value = float(self.rng.lognormal(math.log(median), sigma))
        return min(max(value, low), high)

    def _business_stamp(self, day: date) -> datetime:
        while day.weekday() >= 5:
            day += timedelta(days=1)
        if day > self.end:
            day = self.end
            while day.weekday() >= 5:
                day -= timedelta(days=1)
        return datetime(day.year, day.month, day.day, int(self.rng.integers(9, 18)), int(self.rng.integers(0, 60)), 0)

    def _weekend_night(self, day: date) -> datetime:
        while day.weekday() != 5:
            day += timedelta(days=1)
        if day > self.end:
            day = self.end
            while day.weekday() != 5:
                day -= timedelta(days=1)
        return datetime(day.year, day.month, day.day, 23, int(self.rng.integers(0, 50)), 0)

    def _weekday_night(self, day: date) -> datetime:
        while day.weekday() >= 5:
            day += timedelta(days=1)
        if day > self.end:
            day = self.end
            while day.weekday() >= 5:
                day -= timedelta(days=1)
        return datetime(day.year, day.month, day.day, 23, int(self.rng.integers(0, 40)), 0)

    def _abbr(self, name: str) -> str:
        letters = "".join(character for character in name.upper() if character.isalpha())
        base = (letters + "XXX")[:3]
        candidate = base
        suffix = 0
        while candidate in self.used_abbr:
            suffix += 1
            candidate = f"{base[:2]}{suffix % 10}"
        self.used_abbr.add(candidate)
        return candidate

    def _invoice_number(self, vendor_id: str, on_date: date, jump: int = 1) -> str:
        self.series[vendor_id] = self.series.get(vendor_id, 10000) + jump
        return f"{self.abbr[vendor_id]}-{on_date.year}-{self.series[vendor_id]:05d}"

    def _active(self, department: str | None = None, level: str | None = None) -> list[dict]:
        rows = []
        for employee in self.employees:
            if employee["employment_status"] != "Active":
                continue
            if employee["employee_id"] == self.invalid_employee_id:
                continue
            if department and employee["department"] != department:
                continue
            if level and employee["job_level"] != level:
                continue
            rows.append(employee)
        return rows

    def _employee(self, employee_id: str) -> dict:
        for employee in self.employees:
            if employee["employee_id"] == employee_id:
                return employee
        raise KeyError(employee_id)

    def _vendor(self, vendor_id: str) -> dict:
        for vendor in self.vendors:
            if vendor["vendor_id"] == vendor_id:
                return vendor
        raise KeyError(vendor_id)

    def _build_employees(self) -> None:
        for department in DEPARTMENTS:
            if department == "Finance":
                levels = ["Director", "Department Head"] + ["Manager"] * 3 + ["Senior Analyst"] * 4 + ["Analyst"] * 6
            else:
                levels = ["Department Head"] + ["Manager"] * 3 + ["Senior Analyst"] * 4 + ["Analyst"] * 7
            for level in levels:
                employee_id = self.ids.next("EMP", 3)
                city, _state = CITY_STATE[int(self.rng.integers(0, len(CITY_STATE)))]
                first = self.fake.first_name()
                last = self.fake.last_name()
                self.employees.append(
                    {
                        "employee_id": employee_id,
                        "full_name": f"{first} {last}",
                        "email": f"{first}.{last}.{employee_id}@procureguard.example".lower().replace(" ", ""),
                        "department": department,
                        "job_title": f"{level}, {department}",
                        "job_level": level,
                        "manager_id": None,
                        "approval_limit_inr": JOB_LIMITS[level],
                        "hire_date": self._date_between(date(2014, 1, 1), date(2022, 12, 15)),
                        "employment_status": "Active",
                        "city": city,
                    }
                )
        self.director_id = next(row["employee_id"] for row in self.employees if row["job_level"] == "Director")
        heads = {row["department"]: row["employee_id"] for row in self.employees if row["job_level"] == "Department Head"}
        for employee in self.employees:
            if employee["job_level"] == "Director":
                employee["manager_id"] = None
            elif employee["job_level"] == "Department Head":
                employee["manager_id"] = self.director_id
            elif employee["job_level"] == "Manager":
                employee["manager_id"] = heads[employee["department"]]
            else:
                managers = [row["employee_id"] for row in self.employees if row["department"] == employee["department"] and row["job_level"] == "Manager"]
                employee["manager_id"] = self.pick(managers)
        analysts = [row for row in self.employees if row["job_level"] == "Analyst"]
        for employee in analysts[:6]:
            employee["employment_status"] = "Inactive"
        self.invalid_employee_id = analysts[6]["employee_id"]

    def _build_vendors(self) -> None:
        role_categories = (
            ["Professional Services"] * 5
            + ["Office Supplies"] * 6
            + ["Facilities Management"] * 7
            + ["Facilities Management"] * 4
            + ["Equipment"] * 4
            + ["Equipment"] * 3
            + ["Logistics"] * 1
            + ["Logistics"] * 4
            + ["Utilities"] * 2
            + [VENDOR_CATEGORIES[index % len(VENDOR_CATEGORIES)] for index in range(24)]
        )
        assert len(role_categories) == 60
        used_names: set[str] = set()
        for index, category in enumerate(role_categories):
            vendor_id = self.ids.next("VEN", 3)
            name = self.fake.company()
            if name in used_names:
                name = f"{name} {vendor_id}"
            used_names.add(name)
            self.abbr[vendor_id] = self._abbr(name)
            city, state = CITY_STATE[index % len(CITY_STATE)]
            token = vendor_id
            if index in {50, 51}:
                token = "SHARED-PAIR-A"
            elif index in {52, 53}:
                token = "SHARED-PAIR-B"
            terms = 15 if category == "Utilities" else (30 if index % 3 else 45)
            self.vendors.append(
                {
                    "vendor_id": vendor_id,
                    "vendor_name": name,
                    "vendor_category": category,
                    "gstin": f"99SYN{index + 1:05d}1A1Z9",
                    "city": city,
                    "state": state,
                    "bank_account_hash": bank_hash(token),
                    "onboarding_date": self._date_between(date(2018, 1, 1), date(2023, 3, 1)),
                    "vendor_status": "Active" if index < 55 else ("Suspended" if index < 58 else "Inactive"),
                    "contact_email": f"accounts.{vendor_id.lower()}@vendors.example",
                    "payment_terms_days": terms,
                }
            )
        ids = [row["vendor_id"] for row in self.vendors]
        self.roles = {
            "recurring": ids[0:5],
            "high_volume": ids[5:11],
            "split_suspicious": ids[11:18],
            "split_benign": ids[18:22],
            "gaming": ids[22:26],
            "volatility": ids[26:29],
            "seasonal": ids[29:30],
            "dispute": ids[30:34],
            "utility": ids[34:36],
            "general": ids[36:59],
        }
        self.invalid_vendor_id = ids[59]
        for vendor_id in self.roles["high_volume"]:
            self.add_label(
                "vendor",
                vendor_id,
                "BENIGN_HIGH_VOLUME",
                "High-volume vendor created as a benign control. Volume alone is not a risk event.",
                benign=True,
            )
        for vendor_id in ids[50:54]:
            self.add_label(
                "vendor",
                vendor_id,
                "DUPLICATE_BANK_HASH",
                "Synthetic vendor shares a bank-account hash with one other vendor.",
                defect=True,
                related=ids[50:54],
            )

    def _add_po(
        self,
        vendor_id: str,
        department: str,
        category: str,
        po_date: date,
        amount: float,
        description: str,
        mode: str,
        status: str = "Approved",
        requestor_id: str | None = None,
    ) -> dict:
        if requestor_id is None:
            requestor = self.pick(self._active(department))
            requestor_id = requestor["employee_id"]
        record = {
            "po_id": self.ids.next("PO", 6),
            "vendor_id": vendor_id,
            "requestor_employee_id": requestor_id,
            "department": department,
            "category": category,
            "po_date": po_date,
            "po_amount_inr": money(amount),
            "currency": "INR",
            "status": status,
            "description": description,
        }
        self.po_mode[record["po_id"]] = mode
        self.purchase_orders.append(record)
        key = (vendor_id, department, category)
        previous = self.last_dates.get(key)
        self.last_dates[key] = po_date if previous is None or po_date > previous else previous
        return record

    def _add_invoice(
        self,
        vendor_id: str,
        po: dict | None,
        invoice_date: date,
        item_code: str,
        item_description: str,
        quantity: int,
        unit_price: float,
        invoice_number: str | None = None,
        description: str | None = None,
        status: str = "Approved",
        dispute: bool = False,
    ) -> dict:
        unit, taxable, tax, total = line_amounts(unit_price, quantity, self.gst)
        vendor = self._vendor(vendor_id)
        record = {
            "invoice_id": self.ids.next("INV", 6),
            "invoice_number": invoice_number or self._invoice_number(vendor_id, invoice_date),
            "vendor_id": vendor_id,
            "po_id": None if po is None else po["po_id"],
            "invoice_date": invoice_date,
            "due_date": invoice_date + timedelta(days=int(vendor["payment_terms_days"])),
            "item_code": item_code,
            "item_description": item_description,
            "quantity": int(quantity),
            "unit_price_inr": unit,
            "invoice_amount_inr": taxable,
            "tax_amount_inr": tax,
            "total_amount_inr": total,
            "currency": "INR",
            "status": "Disputed" if dispute else status,
            "dispute_flag": dispute,
            "description": description or item_description,
            "submitted_at": self._business_stamp(invoice_date),
        }
        self.invoices.append(record)
        return record

    def _clone_invoice(self, source: dict, **changes) -> dict:
        record = deepcopy(source)
        record["invoice_id"] = self.ids.next("INV", 6)
        record.update(changes)
        self.invoices.append(record)
        return record

    def _matching_po_for_invoice(self, invoice: dict, mode: str = "ordinary") -> dict:
        return self._add_po(
            vendor_id=invoice["vendor_id"],
            department="Procurement",
            category=self._vendor(invoice["vendor_id"])["vendor_category"],
            po_date=invoice["invoice_date"] - timedelta(days=5),
            amount=invoice["total_amount_inr"],
            description=invoice["description"],
            mode=mode,
        )

    def _protect_invoice(self, *records: dict) -> None:
        for record in records:
            self.protected_invoices.add(record["invoice_id"])

    def _protect_po(self, *records: dict) -> None:
        for record in records:
            self.protected_pos.add(record["po_id"])

    def _build_planted_purchases(self) -> None:
        self._build_recurring()
        self._build_utilities()
        self._build_volatility()
        self._build_repeated_amounts()
        self._build_exact_duplicates()
        self._build_near_time_duplicates()
        self._build_fuzzy_duplicates()
        self._build_split_clusters()
        self._build_threshold_gaming()
        self._build_po_control_failures()
        self._build_invoice_po_mismatches()

    def _build_recurring(self) -> None:
        for vendor_id in self.roles["recurring"]:
            fiscal_pos = {}
            for year_index, anchor in enumerate((date(2023, 4, 15), date(2024, 4, 15))):
                sample = self._add_invoice(
                    vendor_id,
                    None,
                    anchor,
                    "PRF-REC",
                    "Monthly AMC retainer",
                    1,
                    40678,
                    description="Monthly AMC retainer",
                )
                # The sample invoice is rebuilt against the annual PO below.
                self.invoices.remove(sample)
                po = self._add_po(
                    vendor_id,
                    "Procurement",
                    "Professional Services",
                    anchor - timedelta(days=10),
                    sample["total_amount_inr"] * 12,
                    "Annual professional services retainer",
                    "director",
                )
                fiscal_pos[year_index] = po
                self._protect_po(po)
            related = []
            for month_index in range(24):
                invoice_date = add_months(date(2023, 4, 15), month_index)
                po = fiscal_pos[0 if invoice_date < date(2024, 4, 1) else 1]
                invoice = self._add_invoice(
                    vendor_id,
                    po,
                    invoice_date,
                    "PRF-REC",
                    "Monthly AMC retainer",
                    1,
                    40678,
                    description="Monthly AMC retainer",
                )
                related.append(invoice["invoice_id"])
                self._protect_invoice(invoice)
            for invoice_id in related:
                self.add_label(
                    "invoice",
                    invoice_id,
                    "BENIGN_RECURRING",
                    "Legitimate monthly retainer. Amounts repeat about 30 days apart.",
                    benign=True,
                    related=related,
                )

    def _build_utilities(self) -> None:
        for vendor_id in self.roles["utility"]:
            for month_index in range(12):
                invoice_date = add_months(date(2023, 5, 8), month_index)
                amount_noise = 14000 + int(self.rng.integers(0, 7000))
                invoice = self._add_invoice(
                    vendor_id,
                    None,
                    invoice_date,
                    "UTL-PWR",
                    "Electricity charges",
                    1,
                    amount_noise,
                    description="Electricity charges",
                )
                self._protect_invoice(invoice)
                self.add_label(
                    "invoice",
                    invoice["invoice_id"],
                    "BENIGN_NON_PO",
                    "Utility invoice below the purchase-order threshold.",
                    benign=True,
                )

    def _build_volatility(self) -> None:
        volatile = [1.00, 1.55, 0.62, 1.70, 0.58, 1.48, 0.70, 1.62, 0.95, 1.40]
        stable = [1.00, 1.02, 0.99, 1.01, 0.98, 1.03, 1.00, 0.97, 1.02, 0.99]
        seasonal = [0.90, 0.94, 0.98, 1.02, 1.06, 1.10, 1.08, 1.00, 0.96, 0.92]
        for vendor_id in self.roles["volatility"]:
            self._price_series(vendor_id, "EQP-VOL-01", "Industrial sensor unit", volatile, "PRICE_VOLATILITY", suspicious=True)
            self._price_series(vendor_id, "EQP-STA-01", "Standard sensor unit", stable, "", suspicious=False)
            self.add_label(
                "vendor",
                vendor_id,
                "PRICE_VOLATILITY",
                "Planted unit-price swings on one item. A second item from the same vendor stays stable.",
                suspicious=True,
            )
        seasonal_vendor = self.roles["seasonal"][0]
        self._price_series(seasonal_vendor, "LOG-SEA-01", "Seasonal linehaul", seasonal, "", suspicious=False)
        self.add_label(
            "vendor",
            seasonal_vendor,
            "BENIGN_PRICE_VARIATION",
            "Mild seasonal price movement that should stay below the volatility cutoff.",
            benign=True,
        )

    def _price_series(self, vendor_id: str, item_code: str, description: str, multipliers: list[float], _code: str, suspicious: bool) -> None:
        for index, multiplier in enumerate(multipliers):
            invoice_date = date(2023, 5, 3) + timedelta(days=28 * index)
            invoice = self._add_invoice(
                vendor_id,
                None,
                invoice_date,
                item_code,
                description,
                8,
                2500 * multiplier,
                description=description,
            )
            po = self._matching_po_for_invoice(invoice, "ordinary")
            invoice["po_id"] = po["po_id"]
            po["department"] = "Operations"
            po["category"] = self._vendor(vendor_id)["vendor_category"]
            self._protect_invoice(invoice)
            self._protect_po(po)
            if suspicious:
                self.add_label(
                    "invoice",
                    invoice["invoice_id"],
                    "PRICE_VOLATILITY",
                    "Invoice contributes to a planted volatile unit-price series.",
                    suspicious=True,
                    related=[vendor_id, item_code],
                )

    def _build_repeated_amounts(self) -> None:
        vendors = self.roles["general"][:15]
        for index, vendor_id in enumerate(vendors):
            invoice_date = date(2023, 6, 1) + timedelta(days=40 * index)
            invoice = self._add_invoice(
                vendor_id,
                None,
                invoice_date,
                "IT-LIC-02",
                "Software subscription seat",
                1,
                12500,
                description="Software subscription seat",
            )
            po = self._matching_po_for_invoice(invoice, "ordinary")
            invoice["po_id"] = po["po_id"]
            self._protect_invoice(invoice)
            self._protect_po(po)
            self.add_label(
                "invoice",
                invoice["invoice_id"],
                "BENIGN_REPEATED_AMOUNT",
                "Standard catalogue price repeated across different vendors.",
                benign=True,
            )

    def _paired_copy(self, invoice: dict, number: str, day_shift: int, unit_price: float | None = None) -> dict:
        if unit_price is None:
            copy = self._clone_invoice(
                invoice,
                invoice_number=number,
                invoice_date=invoice["invoice_date"] + timedelta(days=day_shift),
                due_date=invoice["due_date"] + timedelta(days=day_shift),
                submitted_at=self._business_stamp(invoice["invoice_date"] + timedelta(days=day_shift)),
                po_id=None,
            )
        else:
            unit, taxable, tax, total = line_amounts(unit_price, int(invoice["quantity"]), self.gst)
            shifted = invoice["invoice_date"] + timedelta(days=day_shift)
            copy = self._clone_invoice(
                invoice,
                invoice_number=number,
                invoice_date=shifted,
                due_date=shifted + timedelta(days=int(self._vendor(invoice["vendor_id"])["payment_terms_days"])),
                unit_price_inr=unit,
                invoice_amount_inr=taxable,
                tax_amount_inr=tax,
                total_amount_inr=total,
                submitted_at=self._business_stamp(shifted),
                po_id=None,
            )
        po = self._matching_po_for_invoice(copy, "ordinary")
        copy["po_id"] = po["po_id"]
        self._protect_po(po)
        self._protect_invoice(copy)
        return copy

    def _build_exact_duplicates(self) -> None:
        vendors = self.roles["general"][15:27]
        for index, vendor_id in enumerate(vendors):
            invoice_date = date(2023, 7, 4) + timedelta(days=37 * index)
            invoice = self._add_invoice(
                vendor_id,
                None,
                invoice_date,
                "CASE-EXACT",
                "Printer consumables",
                2,
                21000 + index * 875,
                description="Printer consumables",
            )
            po = self._matching_po_for_invoice(invoice, "ordinary")
            invoice["po_id"] = po["po_id"]
            copy = self._paired_copy(invoice, invoice["invoice_number"], 1)
            self._protect_invoice(invoice)
            self._protect_po(po)
            related = [invoice["invoice_id"], copy["invoice_id"]]
            for invoice_id in related:
                self.add_label(
                    "invoice",
                    invoice_id,
                    "EXACT_DUP_INVOICE",
                    "Same vendor, invoice number, and amount submitted on adjacent days.",
                    suspicious=True,
                    related=related,
                )

    def _build_near_time_duplicates(self) -> None:
        distant_vendors = self.roles["dispute"]
        # dispute vendors are few; use general vendors that still have room, plus dispute vendors.
        vendors = (self.roles["general"][27:] + self.roles["dispute"])[:10]
        if len(vendors) < 10:
            vendors = (vendors + self.roles["high_volume"])[:10]
        for index, vendor_id in enumerate(vendors):
            invoice_date = date(2023, 8, 6) + timedelta(days=33 * index)
            base_unit = 18000 + index * 640
            invoice = self._add_invoice(
                vendor_id,
                None,
                invoice_date,
                "CASE-NEAR",
                "Domestic freight",
                2,
                base_unit,
                description="Domestic freight",
            )
            po = self._matching_po_for_invoice(invoice, "ordinary")
            invoice["po_id"] = po["po_id"]
            distant_number = self._invoice_number(vendor_id, invoice_date + timedelta(days=3), jump=4500)
            copy = self._paired_copy(invoice, distant_number, 3, unit_price=base_unit * 1.004)
            self._protect_invoice(invoice)
            self._protect_po(po)
            related = [invoice["invoice_id"], copy["invoice_id"]]
            for invoice_id in related:
                self.add_label(
                    "invoice",
                    invoice_id,
                    "NEAR_TIME_DUP_INVOICE",
                    "Close amount and date with invoice numbers far apart in the vendor series.",
                    suspicious=True,
                    related=related,
                )
        for index, vendor_id in enumerate(self.roles["high_volume"][:4]):
            invoice_date = date(2024, 1, 9) + timedelta(days=28 * index)
            invoice = self._add_invoice(
                vendor_id,
                None,
                invoice_date,
                "CASE-SEQ",
                "Office stationery kit",
                3,
                4500,
                description="Office stationery kit",
            )
            po = self._matching_po_for_invoice(invoice, "ordinary")
            invoice["po_id"] = po["po_id"]
            next_number = self._invoice_number(vendor_id, invoice_date + timedelta(days=2))
            copy = self._paired_copy(invoice, next_number, 2)
            self._protect_invoice(invoice)
            self._protect_po(po)
            related = [invoice["invoice_id"], copy["invoice_id"]]
            for invoice_id in related:
                self.add_label(
                    "invoice",
                    invoice_id,
                    "NEAR_TIME_DUP_INVOICE",
                    "Suspicious near-duplicate that uses the next serial invoice number. The sequential-gap heuristic is expected to miss it.",
                    suspicious=True,
                    related=related,
                )
        for index, vendor_id in enumerate(self.roles["high_volume"][4:]):
            invoice_date = date(2024, 5, 14) + timedelta(days=25 * index)
            invoice = self._add_invoice(
                vendor_id,
                None,
                invoice_date,
                "CASE-ORD",
                "Paper and packaging",
                2,
                3600,
                description="Paper and packaging",
            )
            po = self._matching_po_for_invoice(invoice, "ordinary")
            invoice["po_id"] = po["po_id"]
            next_number = self._invoice_number(vendor_id, invoice_date + timedelta(days=2))
            copy = self._paired_copy(invoice, next_number, 2, unit_price=3600 * 1.35)
            self._protect_invoice(invoice)
            self._protect_po(po)
            related = [invoice["invoice_id"], copy["invoice_id"]]
            for invoice_id in related:
                self.add_label(
                    "invoice",
                    invoice_id,
                    "BENIGN_REPEAT_ORDER",
                    "Sequential repeat order with a materially different amount.",
                    benign=True,
                    related=related,
                )

    def _build_fuzzy_duplicates(self) -> None:
        vendors = self.roles["general"][:8]
        for index, vendor_id in enumerate(vendors):
            invoice_date = date(2024, 2, 11) + timedelta(days=27 * index)
            invoice = self._add_invoice(
                vendor_id,
                None,
                invoice_date,
                "CASE-FUZZY",
                "Print collateral",
                4,
                11000 + index * 250,
                description="Print collateral",
            )
            po = self._matching_po_for_invoice(invoice, "ordinary")
            invoice["po_id"] = po["po_id"]
            if index < 4:
                variant = invoice["invoice_number"].replace("-", "/")
                note = "Punctuation differs, but the normalised invoice number matches."
            else:
                variant = invoice["invoice_number"].replace("0", "O", 1)
                note = "One character in the invoice number resembles an OCR or typing substitution."
            copy = self._paired_copy(invoice, variant, 1)
            self._protect_invoice(invoice)
            self._protect_po(po)
            related = [invoice["invoice_id"], copy["invoice_id"]]
            for invoice_id in related:
                self.add_label("invoice", invoice_id, "FUZZY_DUP_INVOICE", note, suspicious=True, related=related)

    def _build_split_clusters(self) -> None:
        suspicious_amounts = [166000, 172000, 178000]
        benign_amounts = [162000, 168000, 174000]
        for index, vendor_id in enumerate(self.roles["split_suspicious"]):
            anchor = date(2023, 6, 2) + timedelta(days=46 * index)
            cluster_ids = []
            for step, amount in enumerate(suspicious_amounts):
                po = self._add_po(
                    vendor_id,
                    "Facilities",
                    "Facilities Management",
                    anchor + timedelta(days=4 * step),
                    amount,
                    "Facilities maintenance call-off",
                    "manager",
                )
                invoice = self._add_invoice(
                    vendor_id,
                    po,
                    po["po_date"] + timedelta(days=3),
                    "FAC-REP-02",
                    "Building repair visit",
                    1,
                    amount / 1.18,
                    description="Building repair visit",
                )
                # Align the PO to the tax-inclusive invoice total, then restore the intended total
                # by setting both from the same rounded amount.
                po["po_amount_inr"] = money(amount)
                self._retarget_invoice_total(invoice, amount)
                cluster_ids.append(po["po_id"])
                self._protect_po(po)
                self._protect_invoice(invoice)
            for po_id in cluster_ids:
                self.add_label(
                    "purchase_order",
                    po_id,
                    "SPLIT_PURCHASE",
                    "Three sub-threshold facilities orders within a week. Combined value exceeds manager authority.",
                    suspicious=True,
                    related=cluster_ids,
                )
        for index, vendor_id in enumerate(self.roles["split_benign"]):
            anchor = date(2024, 6, 3) + timedelta(days=40 * index)
            cluster_ids = []
            for step, amount in enumerate(benign_amounts):
                po = self._add_po(
                    vendor_id,
                    "Facilities",
                    "Facilities Management",
                    anchor + timedelta(days=3 * step),
                    amount,
                    "Approved facilities programme split",
                    "director",
                )
                invoice = self._add_invoice(
                    vendor_id,
                    po,
                    po["po_date"] + timedelta(days=4),
                    "FAC-SEC-03",
                    "Security staffing block",
                    1,
                    amount / 1.18,
                    description="Security staffing block",
                )
                po["po_amount_inr"] = money(amount)
                self._retarget_invoice_total(invoice, amount)
                cluster_ids.append(po["po_id"])
                self._protect_po(po)
                self._protect_invoice(invoice)
            for po_id in cluster_ids:
                self.add_label(
                    "purchase_order",
                    po_id,
                    "BENIGN_VALID_SPLIT",
                    "Split orders whose combined value was approved by a director with sufficient authority.",
                    benign=True,
                    related=cluster_ids,
                )

    def _retarget_invoice_total(self, invoice: dict, total: float) -> None:
        """Set a tax-inclusive total, accepting a small unit-price rounding difference.

        Purchase-order matching uses the purchase-order amount. The invoice stores
        a consistent taxable, tax, and total computed from a rounded unit price.
        Callers that need the PO to match the invoice should copy invoice total
        back onto the PO. Split patterns keep the PO at the planted amount and
        allow the invoice to land within a rupee.
        """
        quantity = int(invoice["quantity"])
        taxable_target = total / (1 + self.gst)
        unit, taxable, tax, computed = line_amounts(taxable_target / quantity, quantity, self.gst)
        invoice["unit_price_inr"] = unit
        invoice["invoice_amount_inr"] = taxable
        invoice["tax_amount_inr"] = tax
        invoice["total_amount_inr"] = computed

    def _build_threshold_gaming(self) -> None:
        amounts = [181000, 189500, 197000]
        for index, vendor_id in enumerate(self.roles["gaming"]):
            anchor = date(2023, 9, 5) + timedelta(days=50 * index)
            related = []
            for step, amount in enumerate(amounts):
                po = self._add_po(
                    vendor_id,
                    "Operations",
                    "Equipment",
                    anchor + timedelta(days=20 * step),
                    amount,
                    "Equipment replenishment",
                    "manager",
                )
                invoice = self._add_invoice(
                    vendor_id,
                    po,
                    po["po_date"] + timedelta(days=4),
                    "CASE-GAMING",
                    "Small plant equipment",
                    1,
                    amount / 1.18,
                    description="Small plant equipment",
                )
                po["po_amount_inr"] = invoice["total_amount_inr"]
                if not 180000 <= po["po_amount_inr"] < 200000:
                    po["po_amount_inr"] = money(amount)
                    self._retarget_invoice_total(invoice, amount)
                    po["po_amount_inr"] = invoice["total_amount_inr"]
                related.append(po["po_id"])
                self._protect_po(po)
                self._protect_invoice(invoice)
            for po_id in related:
                self.add_label(
                    "purchase_order",
                    po_id,
                    "THRESHOLD_GAMING",
                    "Repeated equipment orders placed just below the 200,000 approval threshold.",
                    suspicious=True,
                    related=related,
                )
        for index, vendor_id in enumerate(self.roles["general"][8:18]):
            po = self._add_po(
                vendor_id,
                "Human Resources",
                self._vendor(vendor_id)["vendor_category"],
                date(2024, 8, 1) + timedelta(days=12 * index),
                186000,
                "Single near-threshold equipment purchase",
                "manager",
            )
            invoice = self._add_invoice(
                vendor_id,
                po,
                po["po_date"] + timedelta(days=3),
                "CASE-ONCE",
                "Small plant equipment",
                1,
                186000 / 1.18,
                description="Small plant equipment",
            )
            po["po_amount_inr"] = invoice["total_amount_inr"]
            self._protect_po(po)
            self._protect_invoice(invoice)
            self.add_label(
                "purchase_order",
                po["po_id"],
                "BENIGN_NEAR_THRESHOLD",
                "One order near the threshold. Repetition, not proximity alone, is the alerting condition.",
                benign=True,
            )

    def _build_po_control_failures(self) -> None:
        managers = self._active("Procurement", "Manager")
        for index in range(10):
            po = self._add_po(
                self.roles["general"][index % len(self.roles["general"])],
                "Procurement",
                "Office Supplies",
                date(2023, 10, 2) + timedelta(days=18 * index),
                80000 + index * 1500,
                "Purchase without an approval record",
                "none",
            )
            self._invoice_for_po(po, "CASE-PO", "Purchase without an approval record")
            self._protect_po(po)
            self.add_label(
                "purchase_order",
                po["po_id"],
                "PO_MISSING_APPROVAL",
                "Approved purchase order above 50,000 with no approval record.",
                suspicious=True,
            )
        for index in range(6):
            requestor = managers[index % len(managers)]
            po = self._add_po(
                self.roles["general"][(index + 3) % len(self.roles["general"])],
                requestor["department"],
                "Professional Services",
                date(2024, 3, 4) + timedelta(days=20 * index),
                95000 + index * 1200,
                "Purchase approved by the requestor",
                "self",
                requestor_id=requestor["employee_id"],
            )
            self._invoice_for_po(po, "CASE-PO", "Purchase approved by the requestor")
            self._protect_po(po)
        for index in range(8):
            po = self._add_po(
                self.roles["general"][(index + 5) % len(self.roles["general"])],
                "Finance",
                "IT Services",
                date(2024, 7, 8) + timedelta(days=16 * index),
                350000 + index * 8000,
                "Purchase approved below delegated authority",
                "analyst_low",
            )
            self._invoice_for_po(po, "CASE-PO", "Purchase approved below delegated authority")
            self._protect_po(po)
            self.add_label(
                "purchase_order",
                po["po_id"],
                "PO_APPROVAL_LIMIT_BREACH",
                "Approved by an analyst whose limit is below the order value.",
                suspicious=True,
            )

    def _invoice_for_po(self, po: dict, item_code: str, description: str) -> dict:
        invoice = self._add_invoice(
            po["vendor_id"],
            po,
            po["po_date"] + timedelta(days=4),
            item_code,
            description,
            1,
            float(po["po_amount_inr"]) / 1.18,
            description=description,
        )
        po["po_amount_inr"] = invoice["total_amount_inr"]
        self._protect_invoice(invoice)
        return invoice

    def _build_invoice_po_mismatches(self) -> None:
        for index in range(8):
            vendor_id = self.roles["general"][(index + 11) % len(self.roles["general"])]
            po = self._add_po(
                vendor_id,
                "Marketing",
                self._vendor(vendor_id)["vendor_category"],
                date(2024, 9, 2) + timedelta(days=10 * index),
                64000 + index * 1500,
                "Campaign invoice exceeds purchase order",
                "ordinary",
            )
            invoice = self._add_invoice(
                vendor_id,
                po,
                po["po_date"] + timedelta(days=5),
                "CASE-MIS",
                "Campaign production",
                1,
                float(po["po_amount_inr"]) / 1.18,
                description="Campaign production",
            )
            invoice["total_amount_inr"] = money(invoice["total_amount_inr"] + 2500)
            self._protect_invoice(invoice)
            self._protect_po(po)
            self.add_label(
                "invoice",
                invoice["invoice_id"],
                "INVOICE_PO_MISMATCH",
                "Invoice total exceeds the related purchase order by a planted difference.",
                defect=True,
                related=[po["po_id"]],
            )

    def _ordinary_amount(self) -> float:
        roll = float(self.rng.random())
        if roll < 0.78:
            value = self._lognormal(42000, 0.45, 4000, 150000)
        elif roll < 0.93:
            value = self._lognormal(420000, 0.28, 210000, 900000)
        else:
            value = 60000 + float(self.rng.random()) * 80000
        if 180000 <= value < 200000:
            value = 150000
        return money(value)

    def _spaced_date(self, vendor_id: str, department: str, category: str) -> date:
        key = (vendor_id, department, category)
        last = self.last_dates.get(key)
        if last is None:
            chosen = self._date_between()
        else:
            chosen = last + timedelta(days=21 + int(self.rng.integers(0, 20)))
            if chosen > self.end:
                chosen = self.start + timedelta(days=int(self.rng.integers(0, 30)))
        self.last_dates[key] = chosen
        return chosen

    def _build_ordinary_purchases(self) -> None:
        pool = self.roles["general"] + self.roles["high_volume"] * 4 + self.roles["dispute"] * 3
        target_pos = int(self.config["dataset_sizes"]["purchase_orders"])
        while len(self.purchase_orders) < target_pos:
            vendor_id = self.pick(pool)
            vendor = self._vendor(vendor_id)
            department = self.pick(DEPARTMENTS)
            po_date = self._spaced_date(vendor_id, department, vendor["vendor_category"])
            amount = self._ordinary_amount()
            status_roll = float(self.rng.random())
            if status_roll < 0.86:
                status, mode = "Approved", "ordinary"
            elif status_roll < 0.93:
                status, mode = "Closed", "ordinary"
            elif status_roll < 0.97:
                status, mode = "Pending", "ordinary"
            else:
                status, mode = "Rejected", "reject"
            po = self._add_po(
                vendor_id,
                department,
                vendor["vendor_category"],
                po_date,
                amount,
                f"{vendor['vendor_category']} purchase",
                mode,
                status=status,
            )
            if status == "Rejected" or float(self.rng.random()) < 0.12:
                continue
            choices = [
                item
                for item in ITEM_CATALOG[vendor["vendor_category"]]
                if item[0] not in {"PRF-REC", "EQP-VOL-01", "EQP-STA-01", "LOG-SEA-01"}
            ]
            item_code, description, base_price = self.pick(choices)
            quantity = int(self.rng.integers(1, 5))
            unit_price = base_price * (0.94 + float(self.rng.random()) * 0.1)
            invoice = self._add_invoice(
                vendor_id,
                po,
                min(self.end, po_date + timedelta(days=int(self.rng.integers(2, 12)))),
                item_code,
                description,
                quantity,
                unit_price,
            )
            po["po_amount_inr"] = invoice["total_amount_inr"]
            if float(self.rng.random()) < 0.22 and po_date + timedelta(days=55) <= self.end:
                second = self._add_invoice(
                    vendor_id,
                    po,
                    po_date + timedelta(days=55),
                    item_code,
                    description,
                    max(quantity, 1),
                    unit_price,
                    description=f"{description} progress bill",
                )
                po["po_amount_inr"] = money(invoice["total_amount_inr"] + second["total_amount_inr"])
                self.add_label(
                    "invoice",
                    invoice["invoice_id"],
                    "BENIGN_PROGRESS_BILLING",
                    "First of two progress bills against one purchase order.",
                    benign=True,
                    related=[second["invoice_id"], po["po_id"]],
                )
                self.add_label(
                    "invoice",
                    second["invoice_id"],
                    "BENIGN_PROGRESS_BILLING",
                    "Second progress bill, dated well outside the near-duplicate window.",
                    benign=True,
                    related=[invoice["invoice_id"], po["po_id"]],
                )

    def _top_up_invoices(self) -> None:
        target = int(self.config["dataset_sizes"]["invoices"]) - 2
        pool = self.roles["general"] + self.roles["high_volume"]
        safety = 0
        while len(self.invoices) < target:
            safety += 1
            if safety > 5000:
                raise RuntimeError(f"Could not reach {target} invoices. Current count is {len(self.invoices)}.")
            vendor_id = pool[len(self.invoices) % len(pool)]
            slot = len(self.invoices) % 6
            bases = [3200, 4800, 6400, 8100, 9600, 12400]
            invoice_date = self.start + timedelta(days=(len(self.invoices) * 3) % ((self.end - self.start).days - 2))
            self._add_invoice(
                vendor_id,
                None,
                invoice_date,
                f"PTC-0{slot + 1}",
                "Petty purchase",
                1,
                bases[slot],
                description="Petty purchase below the purchase-order threshold",
            )

    def _apply_disputes(self) -> None:
        by_vendor: dict[str, list[dict]] = {}
        for invoice in self.invoices:
            by_vendor.setdefault(invoice["vendor_id"], []).append(invoice)
        planted = set(self.roles["dispute"])
        for vendor_id, rows in by_vendor.items():
            eligible = [row for row in rows if row["invoice_id"] not in self.protected_invoices and row["status"] == "Approved"]
            if vendor_id in planted:
                target = max(6, math.ceil(0.22 * len(rows)))
                target = min(target, len(eligible))
                for invoice in eligible[:target]:
                    invoice["status"] = "Disputed"
                    invoice["dispute_flag"] = True
                self.add_label(
                    "vendor",
                    vendor_id,
                    "HIGH_DISPUTE_RATE",
                    "Planted concentration of disputed invoices.",
                    suspicious=True,
                )
                continue
            for invoice in eligible:
                if float(self.rng.random()) < 0.03:
                    invoice["status"] = "Disputed"
                    invoice["dispute_flag"] = True
        for vendor_id, rows in by_vendor.items():
            if vendor_id in planted:
                continue
            disputed = [row for row in rows if row["dispute_flag"]]
            while disputed and (len(disputed) >= 5 and len(disputed) / len(rows) >= 0.15):
                invoice = disputed.pop()
                invoice["status"] = "Approved"
                invoice["dispute_flag"] = False

    def _apply_invoice_defects(self) -> None:
        pool = [
            invoice
            for invoice in self.invoices
            if invoice["invoice_id"] not in self.protected_invoices and invoice["status"] == "Approved" and invoice["total_amount_inr"] > 0
        ]
        negative, pool = self.draw(pool, 3)
        for invoice in negative:
            invoice["unit_price_inr"] = money(-abs(invoice["unit_price_inr"]))
            invoice["invoice_amount_inr"] = money(-abs(invoice["invoice_amount_inr"]))
            invoice["tax_amount_inr"] = money(-abs(invoice["tax_amount_inr"]))
            invoice["total_amount_inr"] = money(-abs(invoice["total_amount_inr"]))
            self.add_label("invoice", invoice["invoice_id"], "NEGATIVE_AMOUNT", "Planted negative invoice amount.", defect=True)
        bad_dates, pool = self.draw(pool, 4)
        for invoice in bad_dates:
            invoice["due_date"] = invoice["invoice_date"] - timedelta(days=12)
            self.add_label("invoice", invoice["invoice_id"], "INVALID_DATE_SEQUENCE", "Due date is before the invoice date.", defect=True)
        orphans, pool = self.draw(pool, 6)
        for invoice in orphans:
            invoice["po_id"] = "PO-ORPHAN"
            self.add_label("invoice", invoice["invoice_id"], "ORPHAN_PO_REFERENCE", "Invoice references a purchase order that does not exist.", defect=True)
        unknown, pool = self.draw(pool, 4)
        for invoice in unknown:
            invoice["status"] = "UNKNOWN"
            self.add_label("invoice", invoice["invoice_id"], "INVALID_CATEGORY", "Invoice status is outside the allowed list.", defect=True)
        broken_math, pool = self.draw(pool, 5)
        for invoice in broken_math:
            invoice["total_amount_inr"] = money(invoice["total_amount_inr"] + 250)
            self.add_label("invoice", invoice["invoice_id"], "INVOICE_MATH_MISMATCH", "Invoice total does not equal taxable amount plus tax.", defect=True)
        copies, _pool = self.draw(pool, 2)
        for invoice in copies:
            clone = deepcopy(invoice)
            self.invoices.append(clone)
            self.add_label("invoice", invoice["invoice_id"], "DUPLICATE_PRIMARY_KEY", "A second raw row repeats this invoice id.", defect=True)

    def _apply_master_data_defects(self) -> None:
        email_targets = [row for row in self.employees if row["job_level"] == "Analyst" and row["employee_id"] != self.invalid_employee_id][:4]
        for employee in email_targets:
            employee["email"] = None
            self.add_label("employee", employee["employee_id"], "NULL_EMAIL", "Planted missing employee email.", defect=True)
        self._employee(self.invalid_employee_id)["employment_status"] = "On Leave"
        self.add_label(
            "employee",
            self.invalid_employee_id,
            "INVALID_CATEGORY",
            "Employment status is outside Active and Inactive.",
            defect=True,
        )
        for vendor in self.vendors[46:49]:
            vendor["city"] = None
            self.add_label("vendor", vendor["vendor_id"], "NULL_VENDOR_CITY", "Planted missing vendor city.", defect=True)
        invalid_vendor = self._vendor(self.invalid_vendor_id)
        invalid_vendor["vendor_status"] = "UNKNOWN"
        self.add_label("vendor", invalid_vendor["vendor_id"], "INVALID_CATEGORY", "Vendor status is outside the allowed list.", defect=True)

    def _build_payments(self) -> None:
        unique_ids = set()
        payable = []
        seen = set()
        for invoice in self.invoices:
            if invoice["invoice_id"] in seen:
                continue
            seen.add(invoice["invoice_id"])
            if invoice["status"] in {"Rejected", "UNKNOWN"}:
                continue
            if invoice["total_amount_inr"] is None or invoice["total_amount_inr"] <= 0:
                continue
            if invoice["dispute_flag"] and float(self.rng.random()) < 0.65:
                continue
            payable.append(invoice)
            unique_ids.add(invoice["invoice_id"])
        order = [payable[index] for index in self.rng.permutation(len(payable))]
        base_target = 1379
        chosen = order[: min(base_target, len(order))]
        paid_rows = []
        for invoice in chosen:
            payment = self._add_payment(invoice, invoice["total_amount_inr"], self._payment_date(invoice), "Completed")
            paid_rows.append((invoice, payment))
            if not invoice["dispute_flag"]:
                invoice["status"] = "Paid"
        self._plant_payment_patterns(paid_rows)

    def _payment_date(self, invoice: dict) -> date:
        lag = int(self.rng.integers(0, 25))
        candidate = invoice["invoice_date"] + timedelta(days=lag)
        if candidate < invoice["invoice_date"]:
            candidate = invoice["invoice_date"]
        return candidate

    def _add_payment(self, invoice: dict | None, amount: float, pay_date: date, status: str, vendor_id: str | None = None, invoice_id: str | None = None) -> dict:
        payment = {
            "payment_id": self.ids.next("PAY", 6),
            "invoice_id": invoice_id if invoice is None else invoice["invoice_id"],
            "vendor_id": vendor_id if invoice is None else invoice["vendor_id"],
            "payment_date": pay_date,
            "payment_amount_inr": money(amount),
            "currency": "INR",
            "payment_method": self.pick(["NEFT", "NEFT", "NEFT", "RTGS", "IMPS", "Cheque"]),
            "payment_reference": f"SYN{self.ids.next('REF', 8)}",
            "status": status,
        }
        self.payments.append(payment)
        return payment

    def _plant_payment_patterns(self, paid_rows: list[tuple[dict, dict]]) -> None:
        available = [(invoice, payment) for invoice, payment in paid_rows if invoice["invoice_id"] not in self.protected_invoices and not invoice["dispute_flag"]]
        cursor = 0

        def take(count: int) -> list[tuple[dict, dict]]:
            nonlocal cursor
            if cursor + count > len(available):
                raise RuntimeError("Not enough ordinary payments to plant payment patterns.")
            rows = available[cursor : cursor + count]
            cursor += count
            return rows

        for invoice, payment in take(10):
            extra = self._add_payment(invoice, invoice["total_amount_inr"], payment["payment_date"] + timedelta(days=3), "Completed")
            related = [payment["payment_id"], extra["payment_id"]]
            for payment_id in related:
                self.add_label("payment", payment_id, "DUP_PAYMENT", "Two completed payments each cover the invoice total.", suspicious=True, related=related + [invoice["invoice_id"]])
        for invoice, payment in take(8):
            half = money(invoice["total_amount_inr"] / 2)
            remainder = money(invoice["total_amount_inr"] - half)
            payment["payment_amount_inr"] = half
            extra = self._add_payment(invoice, remainder, payment["payment_date"] + timedelta(days=10), "Completed")
            invoice["status"] = "Paid"
            related = [payment["payment_id"], extra["payment_id"]]
            for payment_id in related:
                self.add_label("payment", payment_id, "BENIGN_PARTIAL_PAYMENT", "Two payments that together equal the invoice total.", benign=True, related=related)
        for invoice, payment in take(5):
            payment["payment_date"] = invoice["invoice_date"] - timedelta(days=6)
            self.add_label("payment", payment["payment_id"], "EARLY_PAYMENT", "Payment date is several days before the invoice date.", suspicious=True, related=[invoice["invoice_id"]])
        for invoice, payment in take(3):
            payment["payment_date"] = invoice["invoice_date"] - timedelta(days=1)
            self.add_label("payment", payment["payment_id"], "BENIGN_POSTING_LAG", "One-day earlier payment consistent with a posting lag. The date rule still flags it.", benign=True, related=[invoice["invoice_id"]])
        for invoice, payment in take(15):
            payment["payment_date"] = invoice["due_date"] + timedelta(days=70 + int(self.rng.integers(0, 35)))
            self.add_label("payment", payment["payment_id"], "LATE_PAYMENT", "Non-disputed payment more than 60 days after the due date.", suspicious=True, related=[invoice["invoice_id"]])
        for invoice, payment in take(6):
            payment["payment_date"] = invoice["due_date"] + timedelta(days=68 + int(self.rng.integers(0, 20)))
            self.add_label("payment", payment["payment_id"], "BENIGN_LATE_PAYMENT", "Long operational delay with no separate dispute marker. The delay rule flags it.", benign=True, related=[invoice["invoice_id"]])
        for invoice, payment in take(5):
            payment["payment_amount_inr"] = money(invoice["total_amount_inr"] * 1.12)
            self.add_label("payment", payment["payment_id"], "PAYMENT_MISMATCH", "Single payment exceeds the invoice total.", suspicious=True, related=[invoice["invoice_id"]])
        for index in range(3):
            payment = self._add_payment(
                None,
                15000 + index * 1000,
                self._date_between(),
                "Completed",
                vendor_id=self.roles["general"][index],
                invoice_id="INV-ORPHAN",
            )
            self.add_label("payment", payment["payment_id"], "ORPHAN_INVOICE_REFERENCE", "Payment references an invoice that does not exist.", defect=True)

    def _build_expenses(self) -> None:
        thresholds = self.config["expense_category_thresholds_inr"]
        active = self._active()
        descriptions = {
            "Meals": "Business meal",
            "Fuel": "Local travel fuel",
            "Travel": "Intercity travel",
            "Lodging": "Hotel stay",
            "Client Entertainment": "Client meeting",
            "Office Supplies": "Office consumables",
        }
        target = int(self.config["dataset_sizes"]["employee_expenses"])
        for _ in range(target):
            employee = self.pick(active)
            category = self.pick(EXPENSE_CATEGORIES)
            limit = float(thresholds[category])
            amount = self._lognormal(limit * 0.35, 0.35, 250, limit * 0.72)
            expense_date = self._date_between()
            self.expenses.append(
                {
                    "expense_id": self.ids.next("EXP", 6),
                    "employee_id": employee["employee_id"],
                    "expense_date": expense_date,
                    "submitted_at": self._business_stamp(expense_date + timedelta(days=1)),
                    "category": category,
                    "amount_inr": money(amount),
                    "currency": "INR",
                    "description": descriptions[category],
                    "receipt_attached": bool(float(self.rng.random()) < 0.9),
                    "status": "Reimbursed",
                }
            )
        pool = list(self.expenses)
        self._plant_expense_patterns(pool, active)

    def _plant_expense_patterns(self, pool: list[dict], active: list[dict]) -> None:
        employees = [row["employee_id"] for row in active if row["job_level"] in {"Analyst", "Senior Analyst", "Manager"}]
        gaming, pool = self.draw(pool, 20)
        amounts = [4620, 4710, 4880, 4950]
        for employee_index in range(5):
            anchor = date(2024, 1, 8) + timedelta(days=40 * employee_index)
            related = []
            for claim_index in range(4):
                expense = gaming[employee_index * 4 + claim_index]
                expense.update(
                    {
                        "employee_id": employees[employee_index],
                        "category": "Meals",
                        "amount_inr": money(amounts[claim_index]),
                        "expense_date": anchor + timedelta(days=7 * claim_index),
                        "submitted_at": self._business_stamp(anchor + timedelta(days=7 * claim_index + 1)),
                        "description": "Business meal",
                        "receipt_attached": True,
                    }
                )
                related.append(expense["expense_id"])
                self.protected_expenses.add(expense["expense_id"])
            for expense_id in related:
                self.add_label("employee_expense", expense_id, "THRESHOLD_GAMING_EXPENSE", "Repeated meal claims just below the 5,000 threshold.", suspicious=True, related=related)
        one_offs, pool = self.draw(pool, 8)
        for index, expense in enumerate(one_offs):
            expense.update(
                {
                    "employee_id": employees[10 + index],
                    "category": "Meals",
                    "amount_inr": money(4800 + index * 15),
                    "expense_date": date(2024, 4, 2) + timedelta(days=21 * index),
                    "submitted_at": self._business_stamp(date(2024, 4, 3) + timedelta(days=21 * index)),
                    "description": "Business meal",
                    "receipt_attached": True,
                }
            )
            self.protected_expenses.add(expense["expense_id"])
            self.add_label("employee_expense", expense["expense_id"], "BENIGN_NEAR_THRESHOLD_EXPENSE", "Single near-threshold meal claim.", benign=True)
        duplicates, pool = self.draw(pool, 16)
        for index in range(8):
            anchor = date(2023, 11, 6) + timedelta(days=30 * index)
            left = duplicates[index * 2]
            right = duplicates[index * 2 + 1]
            amount = money(6400 + index * 125)
            for offset, expense in enumerate((left, right)):
                expense.update(
                    {
                        "employee_id": employees[20 + index],
                        "category": "Travel",
                        "amount_inr": amount,
                        "expense_date": anchor + timedelta(days=offset),
                        "submitted_at": self._business_stamp(anchor + timedelta(days=offset + 1)),
                        "description": "Intercity travel",
                        "receipt_attached": True,
                    }
                )
                self.protected_expenses.add(expense["expense_id"])
            related = [left["expense_id"], right["expense_id"]]
            for expense_id in related:
                self.add_label("employee_expense", expense_id, "DUPLICATE_EXPENSE", "Same employee, category, and amount claimed on adjacent days.", suspicious=True, related=related)
        repeated, pool = self.draw(pool, 6)
        for index in range(3):
            left, right = repeated[index * 2], repeated[index * 2 + 1]
            amount = money(5100 + index * 80)
            for offset, expense in enumerate((left, right)):
                expense.update(
                    {
                        "employee_id": employees[30 + index],
                        "category": "Lodging",
                        "amount_inr": amount,
                        "expense_date": date(2023, 5, 10) + timedelta(days=45 * offset + 20 * index),
                        "submitted_at": self._business_stamp(date(2023, 5, 12) + timedelta(days=45 * offset + 20 * index)),
                        "description": "Hotel stay",
                        "receipt_attached": True,
                    }
                )
                self.protected_expenses.add(expense["expense_id"])
            related = [left["expense_id"], right["expense_id"]]
            for expense_id in related:
                self.add_label("employee_expense", expense_id, "BENIGN_REPEATED_EXPENSE", "Same amount repeated well outside the one-day duplicate window.", benign=True, related=related)
        suspicious_off, pool = self.draw(pool, 12)
        benign_off, pool = self.draw(pool, 4)
        with_receipt, pool = self.draw(pool, 5)
        weekday_night, pool = self.draw(pool, 5)
        small_off, pool = self.draw(pool, 4)
        self._paint_offhours(suspicious_off, employees[40:52], suspicious=True, receipt=False, amount=4500, night="weekend")
        self._paint_offhours(benign_off, employees[52:56], suspicious=False, receipt=False, amount=4300, night="weekend", benign_code="BENIGN_OFFHOURS_CONTEXT")
        self._paint_offhours(with_receipt, employees[56:61], suspicious=False, receipt=True, amount=4300, night="weekend", benign_code="BENIGN_OFFHOURS_WITH_RECEIPT")
        self._paint_offhours(weekday_night, employees[61:66], suspicious=False, receipt=False, amount=4300, night="weekday", benign_code="BENIGN_WEEKDAY_NO_RECEIPT")
        self._paint_offhours(small_off, employees[66:70], suspicious=False, receipt=False, amount=800, night="weekend", benign_code="BENIGN_SMALL_OFFHOURS")
        self_claims, pool = self.draw(pool, 8)
        for index, expense in enumerate(self_claims):
            expense["employee_id"] = employees[71 + index]
            expense["amount_inr"] = money(3600 + index * 90)
            self.self_approve_expenses.add(expense["expense_id"])
            self.protected_expenses.add(expense["expense_id"])
        negative, pool = self.draw(pool, 3)
        for expense in negative:
            expense["amount_inr"] = money(-1500)
            self.add_label("employee_expense", expense["expense_id"], "NEGATIVE_AMOUNT", "Planted negative expense amount.", defect=True)
        future, pool = self.draw(pool, 3)
        for expense in future:
            expense["expense_date"] = date(2025, 6, 18)
            expense["submitted_at"] = datetime(2025, 6, 18, 11, 0, 0)
            self.add_label("employee_expense", expense["expense_id"], "OUT_OF_RANGE_DATE", "Expense date is after the analysis window.", defect=True)
        early, _pool = self.draw(pool, 3)
        for expense in early:
            expense["expense_date"] = date(2012, 1, 15)
            expense["submitted_at"] = datetime(2012, 1, 16, 11, 0, 0)
            self.add_label("employee_expense", expense["expense_id"], "TRANSACTION_BEFORE_HIRE", "Expense date is before the employee hire date.", defect=True)

    def _paint_offhours(self, rows: list[dict], employee_ids: list[str], *, suspicious: bool, receipt: bool, amount: float, night: str, benign_code: str = "") -> None:
        for index, expense in enumerate(rows):
            day = date(2024, 2, 5) + timedelta(days=18 * index)
            stamp = self._weekend_night(day) if night == "weekend" else self._weekday_night(day)
            expense.update(
                {
                    "employee_id": employee_ids[index],
                    "category": "Client Entertainment",
                    "amount_inr": money(amount + index * 25),
                    "expense_date": stamp.date(),
                    "submitted_at": stamp,
                    "description": "Client meeting",
                    "receipt_attached": receipt,
                }
            )
            self.protected_expenses.add(expense["expense_id"])
            if suspicious:
                self.add_label(
                    "employee_expense",
                    expense["expense_id"],
                    "OFFHOURS_EXPENSE",
                    "Weekend late-night claim without a receipt.",
                    suspicious=True,
                )
            else:
                self.add_label(
                    "employee_expense",
                    expense["expense_id"],
                    benign_code,
                    "Lookalike expense that misses at least one element of the off-hours rule, or is a plausible claim the rule cannot distinguish.",
                    benign=True,
                )

    def _build_approvals(self) -> None:
        for po in self.purchase_orders:
            mode = self.po_mode[po["po_id"]]
            if mode == "none":
                continue
            requestor = po["requestor_employee_id"]
            if mode == "self":
                approver = self._employee(requestor)
                decision = "Approved"
            elif mode == "analyst_low":
                candidates = [row for row in self._active(level="Analyst") if row["employee_id"] != requestor]
                approver = self.pick(candidates)
                decision = "Approved"
            elif mode == "director":
                approver = self._employee(self.director_id)
                decision = "Approved"
            elif mode == "manager":
                candidates = [row for row in self._active(po["department"], "Manager") if row["employee_id"] != requestor]
                if not candidates:
                    candidates = [row for row in self._active(level="Manager") if row["employee_id"] != requestor]
                approver = self.pick(candidates)
                decision = "Approved"
            elif mode == "reject":
                approver = self._sufficient_approver(po["department"], float(po["po_amount_inr"]), requestor)
                decision = "Rejected"
            else:
                approver = self._sufficient_approver(po["department"], float(po["po_amount_inr"]), requestor)
                decision = "Approved"
            approval = self._add_approval("purchase_order", po["po_id"], approver, po["po_date"] + timedelta(days=1), decision)
            if mode == "self":
                self.add_label(
                    "approval_record",
                    approval["approval_id"],
                    "SELF_APPROVAL",
                    "Purchase order was approved by the employee who requested it.",
                    suspicious=True,
                    related=[po["po_id"], requestor],
                )
        for invoice in self._unique_invoices():
            if invoice["total_amount_inr"] is None or invoice["total_amount_inr"] < 200000:
                continue
            if invoice["status"] in {"Rejected", "UNKNOWN"}:
                continue
            approver = self._sufficient_approver("Finance", float(invoice["total_amount_inr"]), "")
            self._add_approval("invoice", invoice["invoice_id"], approver, invoice["invoice_date"] + timedelta(days=1), "Approved")
        for expense in self.expenses:
            employee = self._employee(expense["employee_id"])
            if expense["expense_id"] in self.self_approve_expenses:
                approver = employee
            else:
                manager_id = employee["manager_id"]
                if manager_id and manager_id != employee["employee_id"]:
                    approver = self._employee(manager_id)
                else:
                    approver = self.pick([row for row in self._active(employee["department"]) if row["employee_id"] != employee["employee_id"]])
            decision = "Approved" if expense["amount_inr"] and expense["amount_inr"] > 0 else "Returned"
            approval = self._add_approval("employee_expense", expense["expense_id"], approver, expense["expense_date"] + timedelta(days=1), decision)
            if expense["expense_id"] in self.self_approve_expenses and decision == "Approved":
                self.add_label(
                    "approval_record",
                    approval["approval_id"],
                    "SELF_APPROVAL",
                    "Expense claim was approved by the employee who submitted it.",
                    suspicious=True,
                    related=[expense["expense_id"], employee["employee_id"]],
                )

    def _sufficient_approver(self, department: str, amount: float, exclude: str) -> dict:
        pool = [
            row
            for row in self._active()
            if row["employee_id"] != exclude and float(row["approval_limit_inr"]) >= amount
        ]
        same = [row for row in pool if row["department"] == department]
        if same:
            return self.pick(same)
        if pool:
            return self.pick(pool)
        return self._employee(self.director_id)

    def _add_approval(self, entity_type: str, entity_id: str, approver: dict, approval_date: date, decision: str) -> dict:
        record = {
            "approval_id": self.ids.next("APR", 6),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "approver_employee_id": approver["employee_id"],
            "approval_date": approval_date,
            "decision": decision,
            "approval_level": approver["job_level"],
            "comments": "Recorded in the synthetic approval register.",
        }
        self.approvals.append(record)
        return record

    def _unique_invoices(self) -> list[dict]:
        seen = set()
        rows = []
        for invoice in self.invoices:
            if invoice["invoice_id"] in seen:
                continue
            seen.add(invoice["invoice_id"])
            rows.append(invoice)
        return rows

    def _frames(self) -> dict[str, pd.DataFrame]:
        tables = {
            "employees": pd.DataFrame(self.employees, columns=EMPLOYEE_COLUMNS),
            "vendors": pd.DataFrame(self.vendors, columns=VENDOR_COLUMNS),
            "purchase_orders": pd.DataFrame(self.purchase_orders, columns=PO_COLUMNS),
            "invoices": pd.DataFrame(self.invoices, columns=INVOICE_COLUMNS),
            "payments": pd.DataFrame(self.payments, columns=PAYMENT_COLUMNS),
            "employee_expenses": pd.DataFrame(self.expenses, columns=EXPENSE_COLUMNS),
            "approval_records": pd.DataFrame(self.approvals, columns=APPROVAL_COLUMNS),
        }
        for name, frame in tables.items():
            key = {
                "employees": "employee_id",
                "vendors": "vendor_id",
                "purchase_orders": "po_id",
                "invoices": "invoice_id",
                "payments": "payment_id",
                "employee_expenses": "expense_id",
                "approval_records": "approval_id",
            }[name]
            tables[name] = frame.sort_values(key).reset_index(drop=True)
        return tables

    def _label_frame(self) -> pd.DataFrame:
        ordered = sorted(self.labels, key=lambda row: (row["entity_type"], row["entity_id"], row["pattern_code"]))
        for index, row in enumerate(ordered, start=1):
            row["label_id"] = f"LBL{index:06d}"
        return pd.DataFrame(ordered, columns=LABEL_COLUMNS)

    def _summary(self, tables: dict[str, pd.DataFrame], labels: pd.DataFrame) -> dict:
        pattern_counts = (
            labels.groupby(["pattern_code", "is_suspicious", "is_benign_control", "is_data_quality_defect"])
            .size()
            .reset_index(name="rows")
            .to_dict("records")
        )
        return {
            "synthetic": True,
            "random_seed": self.seed,
            "currency": "INR",
            "row_counts": {name: int(len(frame)) for name, frame in tables.items()},
            "ground_truth_rows": int(len(labels)),
            "pattern_counts": pattern_counts,
            "disclaimer": "All people, vendors, GSTINs, bank hashes, and transactions are synthetic. They are not real fraud cases or real financial losses.",
        }

    def _assert_shape(self, tables: dict[str, pd.DataFrame]) -> None:
        sizes = self.config["dataset_sizes"]
        expected = {
            "employees": sizes["employees"],
            "vendors": sizes["vendors"],
            "purchase_orders": sizes["purchase_orders"],
            "invoices": sizes["invoices"],
            "employee_expenses": sizes["employee_expenses"],
        }
        actual = {name: len(tables[name]) for name in expected}
        if actual != expected:
            raise RuntimeError(f"Unexpected row counts: {actual}")


def _json_ready(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def write_generation_summary(summary: dict, path: Path) -> None:
    lines = [
        "# Synthetic data generation summary",
        "",
        "All records described here are synthetic. Nothing in this file is a real fraud finding or a real financial loss.",
        "",
        f"- Random seed: {summary['random_seed']}",
        f"- Currency: {summary['currency']}",
        "",
        "## Row counts",
        "",
    ]
    for name, count in summary["row_counts"].items():
        lines.append(f"- {name}: {count}")
    lines.extend(["", "## Planted pattern labels", ""])
    for row in summary["pattern_counts"]:
        kind = "suspicious" if row["is_suspicious"] else "benign control" if row["is_benign_control"] else "data-quality defect" if row["is_data_quality_defect"] else "other"
        lines.append(f"- {row['pattern_code']}: {row['rows']} labels ({kind})")
    lines.extend(["", summary["disclaimer"], ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def generate_datasets(config: dict, output_root: Path | None = None) -> dict:
    """Generate CSV files, ground-truth labels, and a generation summary."""
    root = Path(config["_project_root"])
    raw_dir = Path(output_root) / "raw" if output_root else root / config["paths"]["raw_dir"]
    evaluation_dir = Path(output_root) / "evaluation" if output_root else root / config["paths"]["evaluation_dir"]
    reports_dir = root / config["paths"]["reports_dir"] if output_root is None else Path(output_root) / "reports"
    generator = SyntheticProcurementGenerator(config)
    tables, labels, summary = generator.build()
    raw_dir.mkdir(parents=True, exist_ok=True)
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    for name, filename in TABLE_FILES.items():
        write_table(tables[name], raw_dir / filename)
    write_table(labels, evaluation_dir / "ground_truth_labels.csv")
    manifest = {
        "synthetic": True,
        "random_seed": summary["random_seed"],
        "row_counts": summary["row_counts"],
        "ground_truth_rows": summary["ground_truth_rows"],
    }
    (raw_dir / "generation_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_generation_summary(summary, reports_dir / "generation_summary.md")
    return {
        "tables": tables,
        "labels": labels,
        "summary": summary,
        "raw_dir": raw_dir,
        "evaluation_dir": evaluation_dir,
    }


def main() -> None:
    from src.utils.config import load_config

    result = generate_datasets(load_config())
    print(json.dumps(_json_ready(result["summary"]), indent=2))


if __name__ == "__main__":
    main()
