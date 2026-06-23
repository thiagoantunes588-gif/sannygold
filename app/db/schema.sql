PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);

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
    id TEXT,
    plate TEXT,
    plate_normalized TEXT NOT NULL DEFAULT '',
    renavam TEXT,
    renavam_normalized TEXT NOT NULL DEFAULT '',
    chassis TEXT,
    chassis_normalized TEXT NOT NULL DEFAULT '',
    brand TEXT,
    model TEXT,
    version TEXT,
    manufacture_year INTEGER,
    model_year INTEGER,
    vehicle_type TEXT,
    fuel_type TEXT,
    current_mileage INTEGER NOT NULL DEFAULT 0 CHECK (current_mileage >= 0),
    legal_owner_company TEXT,
    operating_company TEXT,
    cost_center TEXT,
    acquisition_date TEXT,
    acquisition_value REAL NOT NULL DEFAULT 0 CHECK (acquisition_value >= 0),
    usual_driver_id TEXT,
    status TEXT NOT NULL DEFAULT 'disponivel',
    tracker_installed INTEGER NOT NULL DEFAULT 0 CHECK (tracker_installed IN (0, 1)),
    camera_installed INTEGER NOT NULL DEFAULT 0 CHECK (camera_installed IN (0, 1)),
    notes TEXT,
    created_at TEXT,
    updated_at TEXT,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fleet_documents (
    document_id TEXT PRIMARY KEY,
    id TEXT,
    vehicle_id TEXT,
    document_type TEXT,
    document_number TEXT,
    issued_at TEXT,
    expires_at TEXT,
    issue_date TEXT,
    expiration_date TEXT,
    file_path TEXT,
    status TEXT,
    responsible TEXT,
    responsible_user_id TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vehicle_mileage (
    id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL,
    mileage INTEGER NOT NULL CHECK (mileage >= 0),
    record_date TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    user_id TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS vehicle_audit_logs (
    id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL,
    user_id TEXT,
    action TEXT NOT NULL,
    previous_data TEXT,
    new_data TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_service_orders (
    id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL,
    order_number TEXT NOT NULL UNIQUE,
    maintenance_type TEXT NOT NULL,
    maintenance_plan_id TEXT,
    status TEXT NOT NULL DEFAULT 'aberta',
    priority TEXT NOT NULL DEFAULT 'normal',
    reported_problem TEXT NOT NULL,
    diagnosis TEXT,
    services_performed TEXT,
    opening_date TEXT NOT NULL,
    expected_completion_date TEXT,
    completion_date TEXT,
    entry_mileage INTEGER NOT NULL CHECK (entry_mileage >= 0),
    exit_mileage INTEGER CHECK (exit_mileage IS NULL OR exit_mileage >= 0),
    supplier_id TEXT,
    supplier_name TEXT,
    internal_responsible_user_id TEXT,
    driver_id TEXT,
    labor_cost REAL NOT NULL DEFAULT 0 CHECK (labor_cost >= 0),
    parts_cost REAL NOT NULL DEFAULT 0 CHECK (parts_cost >= 0),
    additional_cost REAL NOT NULL DEFAULT 0 CHECK (additional_cost >= 0),
    discount REAL NOT NULL DEFAULT 0 CHECK (discount >= 0),
    total_cost REAL NOT NULL DEFAULT 0 CHECK (total_cost >= 0),
    total_override_justification TEXT,
    downtime_hours REAL NOT NULL DEFAULT 0 CHECK (downtime_hours >= 0),
    warranty_expiration_date TEXT,
    next_service_date TEXT,
    next_service_mileage INTEGER CHECK (next_service_mileage IS NULL OR next_service_mileage >= 0),
    notes TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_service_order_items (
    id TEXT PRIMARY KEY,
    service_order_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    description TEXT NOT NULL,
    quantity REAL NOT NULL CHECK (quantity > 0),
    unit TEXT NOT NULL,
    unit_cost REAL NOT NULL DEFAULT 0 CHECK (unit_cost >= 0),
    total_cost REAL NOT NULL DEFAULT 0 CHECK (total_cost >= 0),
    inventory_item_id TEXT,
    supplier_id TEXT,
    warranty_days INTEGER NOT NULL DEFAULT 0 CHECK (warranty_days >= 0),
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (service_order_id) REFERENCES fleet_service_orders(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS vehicle_maintenance_plans (
    id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    interval_mileage INTEGER CHECK (interval_mileage IS NULL OR interval_mileage > 0),
    interval_days INTEGER CHECK (interval_days IS NULL OR interval_days > 0),
    warning_mileage INTEGER NOT NULL DEFAULT 0 CHECK (warning_mileage >= 0),
    warning_days INTEGER NOT NULL DEFAULT 0 CHECK (warning_days >= 0),
    last_service_date TEXT,
    last_service_mileage INTEGER CHECK (last_service_mileage IS NULL OR last_service_mileage >= 0),
    next_service_date TEXT,
    next_service_mileage INTEGER CHECK (next_service_mileage IS NULL OR next_service_mileage >= 0),
    priority TEXT NOT NULL DEFAULT 'normal',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    instructions TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_maintenance_attachments (
    id TEXT PRIMARY KEY,
    service_order_id TEXT NOT NULL,
    vehicle_id TEXT NOT NULL,
    attachment_type TEXT NOT NULL,
    original_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content_type TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    notes TEXT,
    uploaded_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (service_order_id) REFERENCES fleet_service_orders(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_inventory_reservations (
    id TEXT PRIMARY KEY,
    service_order_id TEXT NOT NULL,
    service_order_item_id TEXT NOT NULL,
    inventory_item_id TEXT NOT NULL,
    quantity REAL NOT NULL CHECK (quantity > 0),
    status TEXT NOT NULL CHECK (status IN ('reservada', 'consumida', 'liberada')),
    reserved_by TEXT,
    reserved_at TEXT,
    consumed_by TEXT,
    consumed_at TEXT,
    released_by TEXT,
    released_at TEXT,
    warehouse_movement_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (service_order_id) REFERENCES fleet_service_orders(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (service_order_item_id) REFERENCES fleet_service_order_items(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_checklist_templates (
    id TEXT PRIMARY KEY,
    logical_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    checklist_type TEXT NOT NULL,
    vehicle_type TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    version INTEGER NOT NULL CHECK (version > 0),
    supersedes_template_id TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    UNIQUE (logical_id, version)
);

CREATE TABLE IF NOT EXISTS fleet_checklist_template_items (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    display_order INTEGER NOT NULL DEFAULT 0 CHECK (display_order >= 0),
    response_type TEXT NOT NULL,
    selection_options_json TEXT NOT NULL DEFAULT '[]',
    is_required INTEGER NOT NULL DEFAULT 0 CHECK (is_required IN (0, 1)),
    is_critical INTEGER NOT NULL DEFAULT 0 CHECK (is_critical IN (0, 1)),
    requires_photo INTEGER NOT NULL DEFAULT 0 CHECK (requires_photo IN (0, 1)),
    requires_note_on_failure INTEGER NOT NULL DEFAULT 0 CHECK (requires_note_on_failure IN (0, 1)),
    creates_occurrence_on_failure INTEGER NOT NULL DEFAULT 0 CHECK (creates_occurrence_on_failure IN (0, 1)),
    blocks_vehicle_on_failure INTEGER NOT NULL DEFAULT 0 CHECK (blocks_vehicle_on_failure IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (template_id) REFERENCES fleet_checklist_templates(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_checklists (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    template_version INTEGER NOT NULL CHECK (template_version > 0),
    checklist_type TEXT NOT NULL,
    vehicle_id TEXT NOT NULL,
    driver_id TEXT,
    route_id TEXT,
    operation_id TEXT,
    service_order_id TEXT,
    status TEXT NOT NULL DEFAULT 'rascunho',
    started_at TEXT,
    completed_at TEXT,
    start_mileage INTEGER CHECK (start_mileage IS NULL OR start_mileage >= 0),
    end_mileage INTEGER CHECK (end_mileage IS NULL OR end_mileage >= 0),
    distance_travelled INTEGER CHECK (distance_travelled IS NULL OR distance_travelled >= 0),
    fuel_level TEXT,
    general_status TEXT,
    location_text TEXT,
    latitude REAL,
    longitude REAL,
    responsible_user_id TEXT NOT NULL,
    signature_name TEXT,
    confirmation_hash TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (template_id) REFERENCES fleet_checklist_templates(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_checklist_responses (
    id TEXT PRIMARY KEY,
    checklist_id TEXT NOT NULL,
    template_item_id TEXT NOT NULL,
    item_title_snapshot TEXT NOT NULL,
    category_snapshot TEXT NOT NULL,
    response_value TEXT,
    response_status TEXT,
    note TEXT,
    is_critical_snapshot INTEGER NOT NULL DEFAULT 0 CHECK (is_critical_snapshot IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (checklist_id) REFERENCES fleet_checklists(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_checklist_evidence (
    id TEXT PRIMARY KEY,
    checklist_id TEXT NOT NULL,
    response_id TEXT,
    template_item_id TEXT,
    evidence_type TEXT NOT NULL,
    original_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content_type TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    sha256 TEXT NOT NULL,
    uploaded_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (checklist_id) REFERENCES fleet_checklists(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_occurrences (
    id TEXT PRIMARY KEY,
    occurrence_number TEXT NOT NULL UNIQUE,
    vehicle_id TEXT NOT NULL,
    driver_id TEXT,
    route_id TEXT,
    operation_id TEXT,
    checklist_id TEXT,
    service_order_id TEXT,
    occurrence_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'aberta',
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    occurrence_date TEXT NOT NULL,
    reported_at TEXT NOT NULL,
    location TEXT,
    responsible_user_id TEXT NOT NULL,
    assigned_user_id TEXT,
    resolution TEXT,
    resolved_at TEXT,
    resolved_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS vehicle_operational_blocks (
    id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL,
    occurrence_id TEXT,
    checklist_id TEXT,
    service_order_id TEXT,
    block_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    severity TEXT NOT NULL,
    blocked_at TEXT NOT NULL,
    blocked_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ativo',
    released_at TEXT,
    released_by TEXT,
    release_reason TEXT,
    resolution_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (resolution_confirmed IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_vehicle_assignments (
    id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL,
    driver_id TEXT NOT NULL,
    route_id TEXT,
    operation_id TEXT,
    departure_checklist_id TEXT NOT NULL,
    return_checklist_id TEXT,
    delivered_by TEXT NOT NULL,
    received_by_driver TEXT NOT NULL,
    delivered_at TEXT NOT NULL,
    expected_return_at TEXT,
    returned_at TEXT,
    returned_by_driver TEXT,
    received_return_by TEXT,
    start_mileage INTEGER NOT NULL CHECK (start_mileage >= 0),
    end_mileage INTEGER CHECK (end_mileage IS NULL OR end_mileage >= 0),
    start_fuel_level TEXT,
    end_fuel_level TEXT,
    status TEXT NOT NULL DEFAULT 'entregue',
    override_justification TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_driver_authorizations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    employee_id TEXT,
    authorized_vehicle_ids_json TEXT NOT NULL DEFAULT '[]',
    authorized_vehicle_types_json TEXT NOT NULL DEFAULT '[]',
    is_usual_driver INTEGER NOT NULL DEFAULT 0 CHECK (is_usual_driver IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'ativo',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
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
CREATE INDEX IF NOT EXISTS idx_fleet_documents_vehicle ON fleet_documents(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_fleet_documents_expiry ON fleet_documents(expires_at);
CREATE INDEX IF NOT EXISTS idx_vehicle_mileage_vehicle_date ON vehicle_mileage(vehicle_id, record_date DESC);
CREATE INDEX IF NOT EXISTS idx_vehicle_audit_vehicle_created ON vehicle_audit_logs(vehicle_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fleet_service_orders_vehicle_status ON fleet_service_orders(vehicle_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fleet_service_orders_number ON fleet_service_orders(order_number);
CREATE INDEX IF NOT EXISTS idx_fleet_service_orders_opening ON fleet_service_orders(opening_date DESC);
CREATE INDEX IF NOT EXISTS idx_fleet_service_order_items_order ON fleet_service_order_items(service_order_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_maintenance_plans_due ON vehicle_maintenance_plans(vehicle_id, next_service_date, next_service_mileage);
CREATE INDEX IF NOT EXISTS idx_fleet_maintenance_attachments_order ON fleet_maintenance_attachments(service_order_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fleet_inventory_reservations_item_status ON fleet_inventory_reservations(inventory_item_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fleet_inventory_reservation_active
    ON fleet_inventory_reservations(service_order_item_id)
    WHERE status = 'reservada';
CREATE INDEX IF NOT EXISTS idx_fleet_checklist_templates_active ON fleet_checklist_templates(checklist_type, vehicle_type, is_active);
CREATE INDEX IF NOT EXISTS idx_fleet_checklist_template_items_template ON fleet_checklist_template_items(template_id, display_order);
CREATE INDEX IF NOT EXISTS idx_fleet_checklists_vehicle_status ON fleet_checklists(vehicle_id, status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_fleet_checklists_route ON fleet_checklists(route_id, operation_id, checklist_type);
CREATE INDEX IF NOT EXISTS idx_fleet_checklist_responses_checklist ON fleet_checklist_responses(checklist_id, category_snapshot);
CREATE INDEX IF NOT EXISTS idx_fleet_checklist_evidence_checklist ON fleet_checklist_evidence(checklist_id, evidence_type);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fleet_occurrence_number ON fleet_occurrences(occurrence_number);
CREATE INDEX IF NOT EXISTS idx_fleet_occurrences_vehicle_status ON fleet_occurrences(vehicle_id, status, severity);
CREATE INDEX IF NOT EXISTS idx_vehicle_operational_blocks_active ON vehicle_operational_blocks(vehicle_id, status, severity);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fleet_vehicle_assignment_open
    ON fleet_vehicle_assignments(vehicle_id)
    WHERE status = 'entregue' AND deleted_at = '';
CREATE INDEX IF NOT EXISTS idx_fleet_vehicle_assignments_driver ON fleet_vehicle_assignments(driver_id, status, delivered_at DESC);
CREATE INDEX IF NOT EXISTS idx_fleet_driver_authorizations_user ON fleet_driver_authorizations(user_id, status);

CREATE TABLE IF NOT EXISTS fleet_traffic_infractions (
    id TEXT PRIMARY KEY,
    internal_number TEXT NOT NULL UNIQUE,
    vehicle_id TEXT,
    driver_id TEXT,
    route_id TEXT,
    operation_id TEXT,
    issuing_authority TEXT NOT NULL,
    infraction_notice_number TEXT NOT NULL,
    infraction_date TEXT NOT NULL,
    vehicle_plate_snapshot TEXT NOT NULL,
    notification_type TEXT,
    status TEXT NOT NULL DEFAULT 'recebida',
    decision_status TEXT,
    payment_status TEXT,
    driver_identification_status TEXT,
    nic_risk_status TEXT,
    assigned_to TEXT,
    original_infraction_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (original_infraction_id) REFERENCES fleet_traffic_infractions(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_infraction_deadlines (
    id TEXT PRIMARY KEY,
    infraction_id TEXT NOT NULL,
    deadline_type TEXT NOT NULL,
    official_deadline TEXT NOT NULL,
    internal_deadline TEXT,
    status TEXT NOT NULL DEFAULT 'aberto',
    responsible_user_id TEXT,
    completed_at TEXT,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (infraction_id) REFERENCES fleet_traffic_infractions(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_infraction_driver_identifications (
    id TEXT PRIMARY KEY,
    infraction_id TEXT NOT NULL,
    suggested_driver_id TEXT,
    confirmed_driver_id TEXT,
    confidence TEXT,
    status TEXT NOT NULL DEFAULT 'nao_analisada',
    confirmed_by TEXT,
    confirmed_at TEXT,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (infraction_id) REFERENCES fleet_traffic_infractions(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_infraction_document_templates (
    id TEXT PRIMARY KEY,
    issuing_authority TEXT NOT NULL,
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fleet_infraction_document_template_items (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    document_type TEXT NOT NULL,
    is_required INTEGER NOT NULL DEFAULT 1,
    display_order INTEGER NOT NULL DEFAULT 0,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (template_id) REFERENCES fleet_infraction_document_templates(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_infraction_documents (
    id TEXT PRIMARY KEY,
    infraction_id TEXT NOT NULL,
    document_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendente',
    file_path TEXT,
    is_sensitive INTEGER NOT NULL DEFAULT 0,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (infraction_id) REFERENCES fleet_traffic_infractions(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_infraction_proceedings (
    id TEXT PRIMARY KEY,
    infraction_id TEXT NOT NULL,
    proceeding_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'nao_iniciado',
    responsible_user_id TEXT,
    official_deadline TEXT,
    internal_deadline TEXT,
    protocol_number TEXT,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (infraction_id) REFERENCES fleet_traffic_infractions(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_infraction_protocols (
    id TEXT PRIMARY KEY,
    infraction_id TEXT NOT NULL,
    proceeding_id TEXT,
    protocol_number TEXT,
    protocol_date TEXT NOT NULL,
    protocol_channel TEXT NOT NULL,
    proof_path TEXT,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (infraction_id) REFERENCES fleet_traffic_infractions(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (proceeding_id) REFERENCES fleet_infraction_proceedings(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_infraction_payments (
    id TEXT PRIMARY KEY,
    infraction_id TEXT NOT NULL,
    financial_entry_id TEXT,
    due_date TEXT,
    paid_amount REAL NOT NULL DEFAULT 0,
    payment_date TEXT,
    status TEXT NOT NULL DEFAULT 'pendente',
    receipt_path TEXT,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (infraction_id) REFERENCES fleet_traffic_infractions(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_infraction_attachments (
    id TEXT PRIMARY KEY,
    infraction_id TEXT NOT NULL,
    proceeding_id TEXT,
    category TEXT NOT NULL,
    file_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    is_sensitive INTEGER NOT NULL DEFAULT 0,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (infraction_id) REFERENCES fleet_traffic_infractions(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_infraction_decisions (
    id TEXT PRIMARY KEY,
    infraction_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    responsible_user_id TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (infraction_id) REFERENCES fleet_traffic_infractions(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fleet_infraction_audit_logs (
    id TEXT PRIMARY KEY,
    infraction_id TEXT NOT NULL,
    user_id TEXT,
    action TEXT NOT NULL,
    justification TEXT,
    created_at TEXT NOT NULL,
    source_file TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    FOREIGN KEY (infraction_id) REFERENCES fleet_traffic_infractions(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_fleet_infraction_natural_key
    ON fleet_traffic_infractions(issuing_authority, infraction_notice_number, vehicle_plate_snapshot, infraction_date)
    WHERE deleted_at = '';
CREATE INDEX IF NOT EXISTS idx_fleet_infractions_vehicle_status ON fleet_traffic_infractions(vehicle_id, status, infraction_date DESC);
CREATE INDEX IF NOT EXISTS idx_fleet_infractions_driver ON fleet_traffic_infractions(driver_id, driver_identification_status);
CREATE INDEX IF NOT EXISTS idx_fleet_infraction_deadlines_priority ON fleet_infraction_deadlines(status, official_deadline, internal_deadline);
CREATE INDEX IF NOT EXISTS idx_fleet_infraction_identification ON fleet_infraction_driver_identifications(infraction_id, status);
CREATE INDEX IF NOT EXISTS idx_fleet_infraction_template_items ON fleet_infraction_document_template_items(template_id, display_order);
CREATE INDEX IF NOT EXISTS idx_fleet_infraction_documents ON fleet_infraction_documents(infraction_id, status, document_type);
CREATE INDEX IF NOT EXISTS idx_fleet_infraction_proceedings ON fleet_infraction_proceedings(infraction_id, status, official_deadline);
CREATE INDEX IF NOT EXISTS idx_fleet_infraction_protocols ON fleet_infraction_protocols(infraction_id, protocol_date DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fleet_infraction_payment_financial_entry ON fleet_infraction_payments(financial_entry_id) WHERE financial_entry_id <> '' AND deleted_at = '';
CREATE INDEX IF NOT EXISTS idx_fleet_infraction_attachments ON fleet_infraction_attachments(infraction_id, category);
CREATE INDEX IF NOT EXISTS idx_fleet_infraction_decisions ON fleet_infraction_decisions(infraction_id, decided_at DESC);
CREATE INDEX IF NOT EXISTS idx_fleet_infraction_audit ON fleet_infraction_audit_logs(infraction_id, created_at DESC);
