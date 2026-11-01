"""Controlled vocabularies for the synthetic procurement population."""

from __future__ import annotations

DEPARTMENTS = [
    "Procurement",
    "Finance",
    "Operations",
    "Information Technology",
    "Human Resources",
    "Facilities",
    "Marketing",
    "Legal",
]

VENDOR_CATEGORIES = [
    "IT Services",
    "Office Supplies",
    "Facilities Management",
    "Professional Services",
    "Logistics",
    "Marketing Services",
    "Utilities",
    "Equipment",
]

JOB_LIMITS = {
    "Analyst": 50000.0,
    "Senior Analyst": 50000.0,
    "Manager": 200000.0,
    "Department Head": 500000.0,
    "Director": 2000000.0,
}

CITY_STATE = [
    ("Mumbai", "Maharashtra"),
    ("Pune", "Maharashtra"),
    ("Bengaluru", "Karnataka"),
    ("Hyderabad", "Telangana"),
    ("Chennai", "Tamil Nadu"),
    ("New Delhi", "Delhi"),
    ("Gurugram", "Haryana"),
    ("Kolkata", "West Bengal"),
    ("Ahmedabad", "Gujarat"),
    ("Jaipur", "Rajasthan"),
]

ITEM_CATALOG = {
    "IT Services": [
        ("IT-SUP-01", "Workstation support visit", 18000),
        ("IT-LIC-02", "Software subscription seat", 12500),
        ("IT-HW-03", "Laptop standard build", 68000),
        ("IT-CLD-04", "Cloud workspace licence", 22000),
    ],
    "Office Supplies": [
        ("OFS-STA-01", "Office stationery kit", 4500),
        ("OFS-PRT-02", "Printer consumables", 8200),
        ("OFS-FUR-03", "Task chair", 14500),
        ("OFS-PPR-04", "Paper and packaging", 3600),
    ],
    "Facilities Management": [
        ("FAC-HK-01", "Housekeeping monthly block", 54000),
        ("FAC-REP-02", "Building repair visit", 28000),
        ("FAC-SEC-03", "Security staffing block", 76000),
        ("FAC-AC-04", "Air-conditioning service", 19000),
    ],
    "Professional Services": [
        ("PRF-ADV-01", "Advisory workshop", 85000),
        ("PRF-AUD-02", "Process review", 64000),
        ("PRF-TRN-03", "Staff training batch", 32000),
        ("PRF-REC", "Monthly AMC retainer", 40678),
    ],
    "Logistics": [
        ("LOG-FRT-01", "Domestic freight", 24000),
        ("LOG-WH-02", "Warehouse handling", 18500),
        ("LOG-SEA-01", "Seasonal linehaul", 30000),
        ("LOG-LST-04", "Last-mile delivery", 9600),
    ],
    "Marketing Services": [
        ("MKT-CMP-01", "Campaign production", 54000),
        ("MKT-EVT-02", "Event logistics", 47000),
        ("MKT-DIG-03", "Digital media placement", 26000),
        ("MKT-PRT-04", "Print collateral", 11000),
    ],
    "Utilities": [
        ("UTL-PWR", "Electricity charges", 18000),
        ("UTL-WTR-02", "Water and waste", 7000),
        ("UTL-NET-03", "Leased line", 15000),
        ("UTL-TEL-04", "Voice services", 4200),
    ],
    "Equipment": [
        ("EQP-TLS-01", "Maintenance tools", 16000),
        ("EQP-GEN-02", "Small plant equipment", 54000),
        ("EQP-VOL-01", "Industrial sensor unit", 2500),
        ("EQP-STA-01", "Standard sensor unit", 2500),
    ],
}

EXPENSE_CATEGORIES = [
    "Meals",
    "Fuel",
    "Travel",
    "Lodging",
    "Client Entertainment",
    "Office Supplies",
]

PO_STATUSES = ["Approved", "Closed", "Pending", "Rejected"]
INVOICE_STATUSES = ["Submitted", "Approved", "Paid", "Disputed", "Rejected"]
PAYMENT_METHODS = ["NEFT", "RTGS", "IMPS", "Cheque"]
PAYMENT_STATUSES = ["Completed", "Reversed", "Failed"]
EXPENSE_STATUSES = ["Submitted", "Approved", "Reimbursed", "Rejected"]
