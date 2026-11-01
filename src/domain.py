"""Shared codes for detection, labeling, and evaluation.

Ground-truth files are not referenced here. These constants only name the
business rules and the synthetic pattern codes the generator records.
"""

REVIEW_STATUSES = (
    "Pending Review",
    "Under Investigation",
    "Reviewed — No Issue",
    "Escalated for Investigation",
)

RISK_CATEGORIES = ("Low", "Medium", "High", "Critical")

ENTITY_INVOICE = "invoice"
ENTITY_PURCHASE_ORDER = "purchase_order"
ENTITY_PAYMENT = "payment"
ENTITY_EXPENSE = "employee_expense"
ENTITY_APPROVAL = "approval_record"
ENTITY_VENDOR = "vendor"
ENTITY_EMPLOYEE = "employee"

# Maps a detection rule to the synthetic pattern codes that count as positives.
# Benign-control labels use different pattern codes and stay in the negative class.
RULES = {
    "EXACT_DUP_INVOICE": {
        "name": "Exact duplicate invoice number",
        "entity_type": ENTITY_INVOICE,
        "severity": "High",
        "positive_patterns": ("EXACT_DUP_INVOICE",),
    },
    "NEAR_TIME_DUP_INVOICE": {
        "name": "Near-time duplicate invoice",
        "entity_type": ENTITY_INVOICE,
        "severity": "Medium",
        "positive_patterns": ("NEAR_TIME_DUP_INVOICE",),
    },
    "FUZZY_DUP_INVOICE": {
        "name": "Fuzzy duplicate invoice number",
        "entity_type": ENTITY_INVOICE,
        "severity": "High",
        "positive_patterns": ("FUZZY_DUP_INVOICE",),
    },
    "SPLIT_PURCHASE": {
        "name": "Split purchase below approval threshold",
        "entity_type": ENTITY_PURCHASE_ORDER,
        "severity": "High",
        "positive_patterns": ("SPLIT_PURCHASE",),
    },
    "THRESHOLD_GAMING": {
        "name": "Repeated near-threshold purchase orders",
        "entity_type": ENTITY_PURCHASE_ORDER,
        "severity": "Medium",
        "positive_patterns": ("THRESHOLD_GAMING",),
    },
    "DUP_PAYMENT": {
        "name": "Duplicate full payment",
        "entity_type": ENTITY_PAYMENT,
        "severity": "Critical",
        "positive_patterns": ("DUP_PAYMENT",),
    },
    "EARLY_PAYMENT": {
        "name": "Payment before invoice date",
        "entity_type": ENTITY_PAYMENT,
        "severity": "High",
        "positive_patterns": ("EARLY_PAYMENT",),
    },
    "LATE_PAYMENT": {
        "name": "Severely delayed payment",
        "entity_type": ENTITY_PAYMENT,
        "severity": "Medium",
        "positive_patterns": ("LATE_PAYMENT",),
    },
    "PAYMENT_MISMATCH": {
        "name": "Payment amount mismatch",
        "entity_type": ENTITY_PAYMENT,
        "severity": "High",
        "positive_patterns": ("PAYMENT_MISMATCH",),
    },
    "DUPLICATE_EXPENSE": {
        "name": "Duplicate employee expense claim",
        "entity_type": ENTITY_EXPENSE,
        "severity": "High",
        "positive_patterns": ("DUPLICATE_EXPENSE",),
    },
    "THRESHOLD_GAMING_EXPENSE": {
        "name": "Repeated near-threshold expenses",
        "entity_type": ENTITY_EXPENSE,
        "severity": "Medium",
        "positive_patterns": ("THRESHOLD_GAMING_EXPENSE",),
    },
    "OFFHOURS_EXPENSE": {
        "name": "Off-hours expense without receipt",
        "entity_type": ENTITY_EXPENSE,
        "severity": "Low",
        "positive_patterns": ("OFFHOURS_EXPENSE",),
    },
    "SELF_APPROVAL": {
        "name": "Self-approval conflict",
        "entity_type": ENTITY_APPROVAL,
        "severity": "Critical",
        "positive_patterns": ("SELF_APPROVAL",),
    },
    "PO_APPROVAL_LIMIT_BREACH": {
        "name": "Approver limit below purchase order value",
        "entity_type": ENTITY_PURCHASE_ORDER,
        "severity": "High",
        "positive_patterns": ("PO_APPROVAL_LIMIT_BREACH",),
    },
    "PO_MISSING_APPROVAL": {
        "name": "Missing purchase order approval",
        "entity_type": ENTITY_PURCHASE_ORDER,
        "severity": "High",
        "positive_patterns": ("PO_MISSING_APPROVAL",),
    },
    "PRICE_VOLATILITY": {
        "name": "Vendor item price volatility",
        "entity_type": ENTITY_VENDOR,
        "severity": "Medium",
        "positive_patterns": ("PRICE_VOLATILITY",),
    },
    "HIGH_DISPUTE_RATE": {
        "name": "Elevated vendor dispute rate",
        "entity_type": ENTITY_VENDOR,
        "severity": "Medium",
        "positive_patterns": ("HIGH_DISPUTE_RATE",),
    },
}

SEVERITY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
