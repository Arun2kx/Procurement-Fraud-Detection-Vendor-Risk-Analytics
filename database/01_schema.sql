-- ProcureGuard relational schema.
-- Safe to re-run: tables and indexes are created only when missing.
-- This script does not DROP or TRUNCATE existing tables.
-- Fuzzy matching does not require pg_trgm. database/03_duplicate_invoice_detection.sql
-- creates a small immutable Levenshtein function. pg_trgm remains an optional
-- alternative if a DBA wants index-backed similarity search.

CREATE TABLE IF NOT EXISTS employees (
    employee_id VARCHAR(20) PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(180),
    department VARCHAR(80) NOT NULL,
    job_title VARCHAR(120) NOT NULL,
    job_level VARCHAR(40) NOT NULL,
    manager_id VARCHAR(20),
    approval_limit_inr NUMERIC(14, 2) NOT NULL CHECK (approval_limit_inr >= 0),
    hire_date DATE NOT NULL,
    employment_status VARCHAR(20) NOT NULL CHECK (employment_status IN ('Active', 'Inactive')),
    city VARCHAR(80) NOT NULL,
    CONSTRAINT fk_employee_manager FOREIGN KEY (manager_id) REFERENCES employees (employee_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS vendors (
    vendor_id VARCHAR(20) PRIMARY KEY,
    vendor_name VARCHAR(180) NOT NULL,
    vendor_category VARCHAR(80) NOT NULL,
    gstin VARCHAR(20) NOT NULL,
    city VARCHAR(80),
    state VARCHAR(80) NOT NULL,
    bank_account_hash VARCHAR(64) NOT NULL,
    onboarding_date DATE NOT NULL,
    vendor_status VARCHAR(20) NOT NULL CHECK (vendor_status IN ('Active', 'Suspended', 'Inactive')),
    contact_email VARCHAR(180) NOT NULL,
    payment_terms_days INTEGER NOT NULL CHECK (payment_terms_days >= 0)
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    po_id VARCHAR(20) PRIMARY KEY,
    vendor_id VARCHAR(20) NOT NULL REFERENCES vendors (vendor_id),
    requestor_employee_id VARCHAR(20) NOT NULL REFERENCES employees (employee_id),
    department VARCHAR(80) NOT NULL,
    category VARCHAR(80) NOT NULL,
    po_date DATE NOT NULL,
    po_amount_inr NUMERIC(14, 2) NOT NULL CHECK (po_amount_inr > 0),
    currency CHAR(3) NOT NULL CHECK (currency = 'INR'),
    status VARCHAR(20) NOT NULL CHECK (status IN ('Approved', 'Closed', 'Pending', 'Rejected')),
    description VARCHAR(240) NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id VARCHAR(20) PRIMARY KEY,
    invoice_number VARCHAR(60) NOT NULL,
    vendor_id VARCHAR(20) NOT NULL REFERENCES vendors (vendor_id),
    po_id VARCHAR(20) REFERENCES purchase_orders (po_id),
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    item_code VARCHAR(40) NOT NULL,
    item_description VARCHAR(180) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_inr NUMERIC(14, 2) NOT NULL,
    invoice_amount_inr NUMERIC(14, 2) NOT NULL,
    tax_amount_inr NUMERIC(14, 2) NOT NULL,
    total_amount_inr NUMERIC(14, 2) NOT NULL,
    currency CHAR(3) NOT NULL CHECK (currency = 'INR'),
    status VARCHAR(20) NOT NULL CHECK (status IN ('Submitted', 'Approved', 'Paid', 'Disputed', 'Rejected')),
    dispute_flag BOOLEAN NOT NULL,
    description VARCHAR(240) NOT NULL,
    submitted_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id VARCHAR(20) PRIMARY KEY,
    invoice_id VARCHAR(20) NOT NULL REFERENCES invoices (invoice_id),
    vendor_id VARCHAR(20) NOT NULL REFERENCES vendors (vendor_id),
    payment_date DATE NOT NULL,
    payment_amount_inr NUMERIC(14, 2) NOT NULL CHECK (payment_amount_inr > 0),
    currency CHAR(3) NOT NULL CHECK (currency = 'INR'),
    payment_method VARCHAR(20) NOT NULL CHECK (payment_method IN ('NEFT', 'RTGS', 'IMPS', 'Cheque')),
    payment_reference VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('Completed', 'Reversed', 'Failed'))
);

CREATE TABLE IF NOT EXISTS employee_expenses (
    expense_id VARCHAR(20) PRIMARY KEY,
    employee_id VARCHAR(20) NOT NULL REFERENCES employees (employee_id),
    expense_date DATE NOT NULL,
    submitted_at TIMESTAMP NOT NULL,
    category VARCHAR(40) NOT NULL,
    amount_inr NUMERIC(14, 2) NOT NULL,
    currency CHAR(3) NOT NULL CHECK (currency = 'INR'),
    description VARCHAR(240) NOT NULL,
    receipt_attached BOOLEAN NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('Submitted', 'Approved', 'Reimbursed', 'Rejected'))
);

-- Approvals point at purchase orders, invoices, or expenses. A foreign key cannot
-- express that polymorphism, so database/02_data_quality_checks.sql validates it.
CREATE TABLE IF NOT EXISTS approval_records (
    approval_id VARCHAR(20) PRIMARY KEY,
    entity_type VARCHAR(30) NOT NULL CHECK (entity_type IN ('purchase_order', 'invoice', 'employee_expense')),
    entity_id VARCHAR(20) NOT NULL,
    approver_employee_id VARCHAR(20) NOT NULL REFERENCES employees (employee_id),
    approval_date DATE NOT NULL,
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('Approved', 'Rejected', 'Returned')),
    approval_level VARCHAR(40) NOT NULL,
    comments VARCHAR(240) NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_alerts_log (
    alert_id VARCHAR(20) PRIMARY KEY,
    entity_type VARCHAR(40) NOT NULL,
    entity_id VARCHAR(40) NOT NULL,
    vendor_id VARCHAR(20),
    employee_id VARCHAR(20),
    rule_code VARCHAR(60) NOT NULL,
    rule_name VARCHAR(160) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('Critical', 'High', 'Medium', 'Low')),
    risk_score NUMERIC(6, 2),
    estimated_exposure_inr NUMERIC(14, 2) NOT NULL,
    detection_reason TEXT NOT NULL,
    supporting_evidence TEXT NOT NULL,
    detection_timestamp TIMESTAMP NOT NULL,
    review_status VARCHAR(40) NOT NULL CHECK (
        review_status IN (
            'Pending Review',
            'Under Investigation',
            'Reviewed — No Issue',
            'Escalated for Investigation'
        )
    )
);

CREATE TABLE IF NOT EXISTS risk_weight_config (
    factor_name VARCHAR(64) PRIMARY KEY,
    weight NUMERIC(8, 4) NOT NULL CHECK (weight >= 0 AND weight <= 1)
);

INSERT INTO risk_weight_config (factor_name, weight)
SELECT seed.factor_name, seed.weight
FROM (
    VALUES
        ('duplicate_invoice_rate', 0.2200),
        ('dispute_rate', 0.1000),
        ('price_volatility', 0.1200),
        ('split_purchase_involvement', 0.1800),
        ('po_approval_violations', 0.1600),
        ('payment_anomaly_rate', 0.1400),
        ('spend_concentration', 0.0800)
) AS seed(factor_name, weight)
WHERE NOT EXISTS (SELECT 1 FROM risk_weight_config);

CREATE INDEX IF NOT EXISTS idx_po_vendor_date ON purchase_orders (vendor_id, po_date);
CREATE INDEX IF NOT EXISTS idx_po_split_keys ON purchase_orders (vendor_id, department, category, po_date);
CREATE INDEX IF NOT EXISTS idx_invoice_vendor_date ON invoices (vendor_id, invoice_date);
CREATE INDEX IF NOT EXISTS idx_invoice_number ON invoices (vendor_id, invoice_number);
CREATE INDEX IF NOT EXISTS idx_invoice_po ON invoices (po_id);
CREATE INDEX IF NOT EXISTS idx_payment_invoice ON payments (invoice_id);
CREATE INDEX IF NOT EXISTS idx_payment_vendor_date ON payments (vendor_id, payment_date);
CREATE INDEX IF NOT EXISTS idx_expense_employee_date ON employee_expenses (employee_id, expense_date);
CREATE INDEX IF NOT EXISTS idx_approval_entity ON approval_records (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_alert_rule ON audit_alerts_log (rule_code);
CREATE INDEX IF NOT EXISTS idx_alert_vendor ON audit_alerts_log (vendor_id);
CREATE INDEX IF NOT EXISTS idx_alert_status ON audit_alerts_log (review_status);
