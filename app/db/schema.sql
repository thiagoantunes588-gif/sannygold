PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS migration_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    source_data_dir TEXT NOT NULL,
    database_path TEXT NOT NULL,
    status TEXT NOT NULL,
    imported_count INTEGER NOT NULL DEFAULT 0,
    ignored_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    report_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS migration_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    entity TEXT NOT NULL,
    source_file TEXT NOT NULL,
    record_id TEXT,
    status TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (run_id) REFERENCES migration_runs(id)
);

CREATE TABLE IF NOT EXISTS clients (
    client_id TEXT PRIMARY KEY,
    customer_name TEXT,
    phone TEXT,
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    title TEXT,
    event_date TEXT,
    status TEXT,
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equipment (
    equipment_id TEXT PRIMARY KEY,
    equipment_type TEXT,
    status TEXT,
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id TEXT PRIMARY KEY,
    plate TEXT,
    vehicle_type TEXT,
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT,
    nome TEXT,
    role TEXT,
    status TEXT,
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id TEXT PRIMARY KEY,
    created_at TEXT,
    user_email TEXT,
    action TEXT,
    module TEXT,
    target_id TEXT,
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS financial_receivables (
    receivable_id TEXT PRIMARY KEY,
    client_id TEXT,
    client_name TEXT,
    event_id TEXT,
    amount REAL,
    amount_received REAL,
    due_date TEXT,
    status TEXT,
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS financial_entries (
    entry_id TEXT PRIMARY KEY,
    entry_type TEXT,
    category TEXT,
    amount REAL,
    entry_date TEXT,
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS financial_closeouts (
    closeout_id TEXT PRIMARY KEY,
    period TEXT,
    revenue_total REAL,
    expense_total REAL,
    profit_total REAL,
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS json_records (
    entity TEXT NOT NULL,
    record_id TEXT NOT NULL,
    record_label TEXT,
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    PRIMARY KEY (entity, record_id)
);

CREATE TABLE IF NOT EXISTS json_documents (
    entity TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backup_files (
    filename TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    modified_at TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    migrated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(customer_name);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);
CREATE INDEX IF NOT EXISTS idx_financial_receivables_due ON financial_receivables(due_date);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_json_records_entity ON json_records(entity);
