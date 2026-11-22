-- ==============================================================================
-- DDL SCRIPT: 02_metadata_schema.sql
-- CƠ SỞ DỮ LIỆU: Stock_Warehouse (PostgreSQL 16)
-- SCHEMA: metadata (Kiểm toán vận hành, Lineage & Data Quality)
-- ==============================================================================

CREATE SCHEMA IF NOT EXISTS metadata;

-- 1. BẢNG TÀI SẢN DỮ LIỆU (meta_assets)
CREATE TABLE IF NOT EXISTS metadata.meta_assets (
    asset_id SERIAL PRIMARY KEY,
    asset_urn VARCHAR(255) UNIQUE NOT NULL,
    asset_name VARCHAR(255) NOT NULL,
    layer_name VARCHAR(50) NOT NULL,
    domain_name VARCHAR(50),
    asset_type VARCHAR(50) NOT NULL,
    storage_location TEXT NOT NULL,
    partition_keys TEXT[],
    schema_version INT DEFAULT 1,
    row_count_estimate BIGINT DEFAULT 0,
    size_bytes BIGINT DEFAULT 0,
    file_checksum_sha256 VARCHAR(64),
    refresh_frequency VARCHAR(50),
    sla_latency_minutes INT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. TỪ ĐIỂN DỮ LIỆU NGHIỆP VỤ (meta_data_dictionary)
CREATE TABLE IF NOT EXISTS metadata.meta_data_dictionary (
    column_id SERIAL PRIMARY KEY,
    asset_id INT REFERENCES metadata.meta_assets(asset_id) ON DELETE CASCADE,
    column_name VARCHAR(100) NOT NULL,
    ordinal_position INT,
    data_type VARCHAR(50),
    is_nullable BOOLEAN DEFAULT TRUE,
    is_primary_key BOOLEAN DEFAULT FALSE,
    is_foreign_key BOOLEAN DEFAULT FALSE,
    referenced_table VARCHAR(100),
    business_term_vi VARCHAR(255) NOT NULL,
    business_definition TEXT,
    calculation_formula TEXT,
    unit_of_measure VARCHAR(50),
    criticality_level VARCHAR(20) DEFAULT 'MEDIUM',
    source_system_map JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    additivity_type VARCHAR(30) DEFAULT 'FULLY_ADDITIVE',
    CONSTRAINT uq_asset_col UNIQUE (asset_id, column_name)
);

-- 3. NHẬT KÝ PHIÊN CHẠY PIPELINE (meta_pipeline_executions)
CREATE TABLE IF NOT EXISTS metadata.meta_pipeline_executions (
    execution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_name VARCHAR(100) NOT NULL,
    task_name VARCHAR(100),
    source_asset_id INT,
    target_asset_id INT,
    batch_date DATE,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    duration_seconds NUMERIC(10, 2),
    status VARCHAR(30) NOT NULL,
    records_extracted BIGINT DEFAULT 0,
    records_inserted BIGINT DEFAULT 0,
    records_updated BIGINT DEFAULT 0,
    records_quarantined BIGINT DEFAULT 0,
    error_code VARCHAR(50),
    error_message TEXT,
    execution_context JSONB
);

-- 4. CHỈ SỐ KIỂM ĐỊNH DATA QUALITY (meta_data_quality_metrics)
CREATE TABLE IF NOT EXISTS metadata.meta_data_quality_metrics (
    dq_check_id BIGSERIAL PRIMARY KEY,
    execution_id UUID,
    asset_id INT,
    rule_code VARCHAR(100) NOT NULL,
    rule_dimension VARCHAR(50),
    severity_level VARCHAR(20) DEFAULT 'BLOCKER',
    total_records_eval BIGINT DEFAULT 0,
    failed_records_cnt BIGINT DEFAULT 0,
    pass_rate_pct NUMERIC(6, 3),
    threshold_pct NUMERIC(6, 3),
    is_passed BOOLEAN NOT NULL,
    sample_failed_keys JSONB,
    evaluated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 5. BẢNG KIỂM TOÁN ĐỘ PHỦ DỮ LIỆU BCTC (meta_data_coverage_audit)
CREATE TABLE IF NOT EXISTS metadata.meta_data_coverage_audit (
    audit_id SERIAL PRIMARY KEY,
    bank_sk INT NOT NULL REFERENCES master_data.dim_bank(bank_sk),
    ticker VARCHAR(10) NOT NULL,
    expected_quarters INT DEFAULT 35,
    actual_quarters INT NOT NULL,
    missing_quarters INT NOT NULL,
    coverage_pct NUMERIC(6, 2) NOT NULL,
    earliest_quarter VARCHAR(10),
    latest_quarter VARCHAR(10),
    missing_quarter_list TEXT,
    last_audited_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 6. CATALOG TOÀN DIỆN CÁC CỘT TRONG DWH (data_catalog)
CREATE TABLE IF NOT EXISTS metadata.data_catalog (
    catalog_id SERIAL PRIMARY KEY,
    schema_name VARCHAR(100) NOT NULL,
    table_name VARCHAR(100) NOT NULL,
    column_name VARCHAR(100) NOT NULL,
    data_type VARCHAR(100) NOT NULL,
    business_definition TEXT,
    is_primary_key BOOLEAN DEFAULT FALSE,
    is_nullable BOOLEAN DEFAULT TRUE,
    source_layer VARCHAR(50),
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_catalog_col UNIQUE (schema_name, table_name, column_name)
);

-- 7. CÁC BẢNG NHẬT KÝ BỔ TRỢ (pipeline_execution_log & data_quality_log)
CREATE TABLE IF NOT EXISTS metadata.pipeline_execution_log (
    pipeline_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_name VARCHAR(100) NOT NULL,
    batch_id VARCHAR(100) NOT NULL,
    stage_name VARCHAR(50) NOT NULL,
    records_extracted INT DEFAULT 0,
    records_loaded INT DEFAULT 0,
    status VARCHAR(20) NOT NULL,
    execution_duration_sec NUMERIC(10, 2),
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metadata.data_quality_log (
    check_id SERIAL PRIMARY KEY,
    batch_id VARCHAR(100) NOT NULL,
    gateway_level VARCHAR(20) NOT NULL,
    rule_code VARCHAR(100) NOT NULL,
    rule_description TEXT,
    records_tested INT DEFAULT 0,
    records_passed INT DEFAULT 0,
    records_failed INT DEFAULT 0,
    check_status VARCHAR(20) NOT NULL,
    details JSONB,
    checked_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
