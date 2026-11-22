-- ==============================================================================
-- MIGRATION: 004_create_ops_and_metadata.sql
-- BẢNG VẬN HÀNH (OPS) & QUẢN TRỊ SIÊU DỮ LIỆU (METADATA)
-- ==============================================================================

-- 1. BẢNG THEO DÕI PHIÊN CHẠY PIPELINE (ops.pipeline_runs)
CREATE TABLE IF NOT EXISTS ops.pipeline_runs (
    run_id VARCHAR(64) PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL,
    trigger_type VARCHAR(32) DEFAULT 'manual',
    source_dataset TEXT,
    target_datasets TEXT[],
    records_ingested INT DEFAULT 0,
    records_validated INT DEFAULT 0,
    records_published INT DEFAULT 0,
    validation_status VARCHAR(32) DEFAULT 'PASSED',
    status VARCHAR(32) NOT NULL,
    duration_seconds NUMERIC(10, 2),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    error_message TEXT,
    manifest_path TEXT
);

-- 2. BẢNG TRẠNG THÁI CÔNG BỐ DATASET (ops.dataset_publish_state)
CREATE TABLE IF NOT EXISTS ops.dataset_publish_state (
    dataset_name VARCHAR(64) PRIMARY KEY,
    target_table VARCHAR(128) NOT NULL,
    latest_run_id VARCHAR(64) REFERENCES ops.pipeline_runs(run_id),
    latest_record_count INT DEFAULT 0,
    latest_snapshot_date DATE,
    status VARCHAR(32) NOT NULL DEFAULT 'CURRENT',
    last_published_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. BẢNG DATA CATALOG (metadata.data_catalog)
CREATE TABLE IF NOT EXISTS metadata.data_catalog (
    catalog_id SERIAL PRIMARY KEY,
    table_schema VARCHAR(63) NOT NULL,
    table_name VARCHAR(63) NOT NULL,
    column_name VARCHAR(63) NOT NULL,
    ordinal_position INT NOT NULL,
    data_type VARCHAR(63) NOT NULL,
    is_nullable VARCHAR(3) NOT NULL,
    column_default TEXT,
    data_classification VARCHAR(32) DEFAULT 'INTERNAL',
    business_term VARCHAR(128),
    business_description TEXT,
    last_cataloged_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_catalog_col UNIQUE (table_schema, table_name, column_name)
);

-- 4. BẢNG AUDIT LOGS (metadata)
CREATE TABLE IF NOT EXISTS metadata.pipeline_execution_log (
    log_id BIGSERIAL PRIMARY KEY,
    pipeline_name VARCHAR(100) NOT NULL,
    batch_id VARCHAR(100) NOT NULL,
    stage_name VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    records_extracted INT DEFAULT 0,
    records_loaded INT DEFAULT 0,
    error_message TEXT,
    execution_time_sec NUMERIC(10, 2),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metadata.data_quality_log (
    log_id BIGSERIAL PRIMARY KEY,
    batch_id VARCHAR(100) NOT NULL,
    check_name VARCHAR(100) NOT NULL,
    table_name VARCHAR(100) NOT NULL,
    column_name VARCHAR(100),
    failed_records_count INT DEFAULT 0,
    severity VARCHAR(20) NOT NULL,
    description TEXT,
    checked_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
