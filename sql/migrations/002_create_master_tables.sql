-- ==============================================================================
-- MIGRATION: 002_create_master_tables.sql
-- BẢNG CHIỀU (DIMENSION TABLES) TRONG SCHEMA master_data
-- ==============================================================================

-- 1. BẢNG CHIỀU: NGÂN HÀNG (dim_bank)
CREATE TABLE IF NOT EXISTS master_data.dim_bank (
    bank_sk SERIAL PRIMARY KEY,
    bank_uuid UUID DEFAULT gen_random_uuid(),
    ticker VARCHAR(10) UNIQUE NOT NULL,
    isin_code VARCHAR(12),
    bank_name VARCHAR(255) NOT NULL,
    bank_name_en VARCHAR(255),
    short_name VARCHAR(50) NOT NULL,
    tax_code VARCHAR(20),
    listing_exchange VARCHAR(10) NOT NULL,
    tier_group VARCHAR(20) NOT NULL,
    charter_capital_vnd NUMERIC(20, 2),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. BẢNG CHIỀU: THỜI GIAN GIAO DỊCH VÀ BÁO CÁO (dim_date)
CREATE TABLE IF NOT EXISTS master_data.dim_date (
    date_sk INT PRIMARY KEY,
    full_date DATE UNIQUE NOT NULL,
    day_of_week INT NOT NULL,
    day_name VARCHAR(10) NOT NULL,
    day_of_month INT NOT NULL,
    day_of_year INT NOT NULL,
    week_of_year INT NOT NULL,
    calendar_month INT NOT NULL,
    month_name VARCHAR(10) NOT NULL,
    calendar_quarter INT NOT NULL,
    calendar_year INT NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    is_trading_day BOOLEAN NOT NULL,
    fiscal_quarter VARCHAR(10) NOT NULL,
    fiscal_year INT NOT NULL
);

-- 3. BẢNG CHIỀU: CHỈ SỐ THỊ TRƯỜNG & CHỨNG KHOÁN (dim_market_index)
CREATE TABLE IF NOT EXISTS master_data.dim_market_index (
    index_sk SERIAL PRIMARY KEY,
    index_code VARCHAR(20) UNIQUE NOT NULL,
    index_name VARCHAR(100) NOT NULL,
    exchange_code VARCHAR(10) NOT NULL,
    description TEXT,
    base_date DATE,
    base_value NUMERIC(10, 2),
    is_active BOOLEAN DEFAULT TRUE
);

-- 4. BẢNG CHIỀU: CÁ NHÂN / TỔ CHỨC CÓ LIÊN QUAN (dim_stakeholder)
CREATE TABLE IF NOT EXISTS master_data.dim_stakeholder (
    stakeholder_sk SERIAL PRIMARY KEY,
    stakeholder_code VARCHAR(50) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    stakeholder_type VARCHAR(20) NOT NULL,
    nationality VARCHAR(50) DEFAULT 'Vietnam',
    tax_code VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
