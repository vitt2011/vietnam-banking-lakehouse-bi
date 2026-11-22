-- ==============================================================================
-- MIGRATION: 003_create_mart_facts.sql
-- BẢNG SỰ KIỆN (FACT TABLES) CÁC MART NGHIỆP VỤ
-- ==============================================================================

-- 1. FACT: GIÁ VÀ KHỐI LƯỢNG GIAO DỊCH NGÀY (mart_technical)
CREATE TABLE IF NOT EXISTS mart_technical.fact_daily_market_ohlcv (
    fact_id BIGSERIAL PRIMARY KEY,
    bank_sk INT NOT NULL REFERENCES master_data.dim_bank(bank_sk),
    date_sk INT NOT NULL REFERENCES master_data.dim_date(date_sk),
    open_price NUMERIC(12, 2) NOT NULL,
    high_price NUMERIC(12, 2) NOT NULL,
    low_price NUMERIC(12, 2) NOT NULL,
    close_price NUMERIC(12, 2) NOT NULL,
    volume BIGINT NOT NULL,
    turnover_vnd NUMERIC(20, 2) NOT NULL,
    return_daily_pct NUMERIC(8, 4),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_bank_date UNIQUE (bank_sk, date_sk)
);

-- 2. FACT: CHỈ SỐ KINH TẾ VĨ MÔ & LÃI SUẤT (mart_technical)
CREATE TABLE IF NOT EXISTS mart_technical.fact_macro_indicators (
    fact_id BIGSERIAL PRIMARY KEY,
    date_sk INT NOT NULL REFERENCES master_data.dim_date(date_sk),
    indicator_code VARCHAR(50) NOT NULL,
    indicator_name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    value NUMERIC(18, 4) NOT NULL,
    unit VARCHAR(20) NOT NULL,
    frequency VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_macro_date_ind UNIQUE (date_sk, indicator_code)
);

-- 3. FACT: BÁO CÁO TÀI CHÍNH QUÝ (mart_camels)
CREATE TABLE IF NOT EXISTS mart_camels.fact_quarterly_financial_statements (
    fact_id BIGSERIAL PRIMARY KEY,
    bank_sk INT NOT NULL REFERENCES master_data.dim_bank(bank_sk),
    fiscal_year INT NOT NULL,
    fiscal_quarter INT NOT NULL,
    period_date_sk INT NOT NULL REFERENCES master_data.dim_date(date_sk),
    total_assets NUMERIC(22, 2),
    cash_and_gold NUMERIC(22, 2),
    balances_with_sbv NUMERIC(22, 2),
    loans_to_customers NUMERIC(22, 2),
    provision_for_credit_losses NUMERIC(22, 2),
    total_liabilities NUMERIC(22, 2),
    deposits_from_customers NUMERIC(22, 2),
    owners_equity NUMERIC(22, 2),
    charter_capital NUMERIC(22, 2),
    net_interest_income NUMERIC(22, 2),
    net_fee_income NUMERIC(22, 2),
    net_gain_fx NUMERIC(22, 2),
    net_gain_securities NUMERIC(22, 2),
    other_operating_income_residual NUMERIC(22, 2),
    total_operating_income NUMERIC(22, 2),
    general_and_admin_expenses NUMERIC(22, 2),
    provision_expense NUMERIC(22, 2),
    net_profit_before_tax NUMERIC(22, 2),
    net_profit_after_tax NUMERIC(22, 2),
    is_standalone_quarter BOOLEAN DEFAULT TRUE,
    reporting_scope VARCHAR(20) DEFAULT 'CONSOLIDATED',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_camels_bank_quarter UNIQUE (bank_sk, fiscal_year, fiscal_quarter)
);

-- 4. FACT: TỶ SỐ TÀI CHÍNH & ĐỊNH GIÁ (mart_camels)
CREATE TABLE IF NOT EXISTS mart_camels.fact_quarterly_banking_ratios (
    fact_id BIGSERIAL PRIMARY KEY,
    bank_sk INT NOT NULL REFERENCES master_data.dim_bank(bank_sk),
    fiscal_year INT NOT NULL,
    fiscal_quarter INT NOT NULL,
    period_date_sk INT NOT NULL REFERENCES master_data.dim_date(date_sk),
    pb_ratio NUMERIC(10, 4),
    pe_ratio NUMERIC(10, 4),
    roe NUMERIC(10, 4),
    roa NUMERIC(10, 4),
    net_interest_margin NUMERIC(10, 4),
    cost_to_income_ratio NUMERIC(10, 4),
    npl_ratio NUMERIC(10, 4),
    loan_loss_reserve_to_npls NUMERIC(10, 4),
    capital_adequacy_ratio NUMERIC(10, 4),
    casa_ratio NUMERIC(10, 4),
    loan_to_deposit_ratio NUMERIC(10, 4),
    ldr_simple NUMERIC(10, 4),
    avg_yield_on_assets NUMERIC(10, 4),
    avg_cost_of_funds NUMERIC(10, 4),
    credit_cost_ratio NUMERIC(10, 4),
    estimated_npl_amount NUMERIC(22, 2),
    loan_growth_yoy NUMERIC(10, 4),
    deposit_growth_yoy NUMERIC(10, 4),
    credit_deposit_gap NUMERIC(22, 2),
    formula_version VARCHAR(20) DEFAULT '2.0-PRODUCTION',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_ratios_bank_quarter UNIQUE (bank_sk, fiscal_year, fiscal_quarter)
);

-- 5. FACT & BRIDGE: QUẢN TRỊ & MẠNG LƯỚI SỞ HỮU (mart_governance)
CREATE TABLE IF NOT EXISTS mart_governance.fact_bank_officers (
    officer_id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    officer_name VARCHAR(255) NOT NULL,
    position_title VARCHAR(255) NOT NULL,
    ownership_pct NUMERIC(8, 4),
    shares_quantity BIGINT,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mart_governance.fact_bank_shareholders (
    shareholder_id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    shareholder_name VARCHAR(255) NOT NULL,
    quantity BIGINT NOT NULL,
    ownership_pct NUMERIC(8, 4) NOT NULL,
    update_date DATE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mart_governance.fact_bank_subsidiaries (
    sub_id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    subsidiary_name VARCHAR(255) NOT NULL,
    ownership_pct NUMERIC(8, 4) NOT NULL,
    charter_capital_vnd NUMERIC(20, 2),
    business_area VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mart_governance.fact_corporate_events (
    event_id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    event_title TEXT NOT NULL,
    ex_date DATE,
    record_date DATE,
    execution_date DATE,
    value_ratio VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mart_governance.bridge_governance_network (
    bridge_id BIGSERIAL PRIMARY KEY,
    bank_sk INT NOT NULL REFERENCES master_data.dim_bank(bank_sk),
    stakeholder_sk INT NOT NULL REFERENCES master_data.dim_stakeholder(stakeholder_sk),
    relationship_type VARCHAR(50) NOT NULL,
    title VARCHAR(100),
    ownership_pct NUMERIC(8, 4),
    voting_power_pct NUMERIC(8, 4),
    start_date DATE,
    end_date DATE,
    is_current BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 6. FACT: TÂM LÝ & SẮC THÁI TIN TỨC (mart_sentiment)
CREATE TABLE IF NOT EXISTS mart_sentiment.fact_media_sentiment_daily (
    fact_id BIGSERIAL PRIMARY KEY,
    bank_sk INT NOT NULL REFERENCES master_data.dim_bank(bank_sk),
    date_sk INT NOT NULL REFERENCES master_data.dim_date(date_sk),
    article_external_id VARCHAR(100),
    title TEXT NOT NULL,
    source_name VARCHAR(100) NOT NULL,
    source_url TEXT,
    is_official_disclosure BOOLEAN DEFAULT FALSE,
    sentiment_score NUMERIC(5, 4),
    sentiment_label VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
