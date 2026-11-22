-- ==============================================================================
-- DDL SCRIPT: 01_init_database.sql
-- CƠ SỞ DỮ LIỆU: Stock_Warehouse (PostgreSQL 16)
-- KIẾN TRÚC: Enterprise Multi-Schema Data Warehouse (8 Schemas Chuyên Biệt)
-- TRIẾT LÝ: Bill Inmon (Corporate Information Factory) + Kimball Dimensional Marts
-- TÁC GIẢ: Nguyễn Văn Việt (Toán - Tin K68 HUST) | GVHD: TS. Nguyễn Danh Tú
-- ==============================================================================

-- 1. KHỞI TẠO 8 SCHEMAS CHUYÊN BIỆT THEO CHUẨN DOANH NGHIỆP
CREATE SCHEMA IF NOT EXISTS staging;          -- 1. Vùng staging trung chuyển ELT
CREATE SCHEMA IF NOT EXISTS master_data;      -- 2. Vùng dữ liệu chủ (MDM - Dim Tables)
CREATE SCHEMA IF NOT EXISTS mart_valuation;   -- 3. Data Mart Module 1: Định giá Gordon P/B vs ROE
CREATE SCHEMA IF NOT EXISTS mart_camels;      -- 4. Data Mart Module 2: Thẻ điểm rủi ro CAMELS
CREATE SCHEMA IF NOT EXISTS mart_technical;   -- 5. Data Mart Module 3: Kỹ thuật nến OHLCV & Vĩ mô
CREATE SCHEMA IF NOT EXISTS mart_governance;  -- 6. Data Mart Module 4: Quản trị, Lãnh đạo & Cổ đông
CREATE SCHEMA IF NOT EXISTS mart_sentiment;   -- 7. Data Mart Module 5: Tin tức & Tâm lý Thị trường
CREATE SCHEMA IF NOT EXISTS metadata;         -- 8. Vùng quản trị siêu dữ liệu, Catalog & DQ

-- ==============================================================================
-- PHẦN I: SCHEMA metadata (Kiểm toán vận hành, Lineage & Data Quality)
-- Tiền tố chuẩn: meta_
-- ==============================================================================

CREATE TABLE IF NOT EXISTS metadata.meta_assets (
    asset_id SERIAL PRIMARY KEY,
    asset_name VARCHAR(100) UNIQUE NOT NULL,
    layer_name VARCHAR(50) NOT NULL,
    storage_type VARCHAR(50) NOT NULL,
    path_or_table VARCHAR(255) NOT NULL,
    partition_strategy VARCHAR(100),
    data_format VARCHAR(30),
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metadata.meta_data_dictionary (
    dictionary_id SERIAL PRIMARY KEY,
    term_code VARCHAR(100) UNIQUE NOT NULL,
    term_name_vi VARCHAR(255) NOT NULL,
    term_name_en VARCHAR(255),
    domain VARCHAR(50) NOT NULL,
    formula_latex TEXT,
    unit VARCHAR(30),
    additivity_type VARCHAR(30) DEFAULT 'FULLY_ADDITIVE', -- 'FULLY_ADDITIVE', 'SEMI_ADDITIVE', 'NON_ADDITIVE'
    definition TEXT,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metadata.meta_pipeline_executions (
    execution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_name VARCHAR(100) NOT NULL,
    batch_id VARCHAR(100) NOT NULL,
    source_layer VARCHAR(50) NOT NULL,
    target_layer VARCHAR(50) NOT NULL,
    records_in INT DEFAULT 0,
    records_out INT DEFAULT 0,
    status VARCHAR(20) NOT NULL,
    duration_sec NUMERIC(10, 2),
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metadata.meta_data_quality_metrics (
    metric_id SERIAL PRIMARY KEY,
    batch_id VARCHAR(100) NOT NULL,
    gateway_level VARCHAR(20) NOT NULL,
    rule_name VARCHAR(100) NOT NULL,
    target_table VARCHAR(100) NOT NULL,
    records_tested INT DEFAULT 0,
    records_passed INT DEFAULT 0,
    records_failed INT DEFAULT 0,
    status VARCHAR(20) NOT NULL,
    checked_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 5. BẢNG KIỂM TOÁN ĐỘ PHỦ DỮ LIỆU BCTC (meta_data_coverage_audit)
-- Theo dõi 35 quý lịch sử (2018 - 2026) cho 27 ngân hàng
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

-- ==============================================================================
-- PHẦN II: SCHEMA master_data (Master Data Management - MDM)
-- Tiền tố chuẩn: dim_
-- ==============================================================================

-- 1. BẢNG CHIỀU: NGÂN HÀNG (dim_bank)
CREATE TABLE IF NOT EXISTS master_data.dim_bank (
    bank_sk SERIAL PRIMARY KEY,
    ticker VARCHAR(10) UNIQUE NOT NULL,
    bank_name VARCHAR(255) NOT NULL,
    bank_name_en VARCHAR(255),
    short_name VARCHAR(50),
    tax_code VARCHAR(20),
    listing_exchange VARCHAR(10) NOT NULL, -- 'HOSE', 'HNX', 'UPCOM'
    tier_group VARCHAR(30) NOT NULL,       -- 'STATE_BIG4', 'TIER1_PRIVATE', 'TIER2_MIDCAP', 'TIER3_SMALL'
    charter_capital_vnd NUMERIC(20, 2),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. BẢNG CHIỀU: THỜI GIAN TÀI CHÍNH (dim_date)
CREATE TABLE IF NOT EXISTS master_data.dim_date (
    date_sk INT PRIMARY KEY,               -- Định dạng số nguyên YYYYMMDD (VD: 20261021)
    full_date DATE UNIQUE NOT NULL,
    year INT NOT NULL,
    quarter INT NOT NULL,
    month INT NOT NULL,
    day INT NOT NULL,
    day_of_week INT NOT NULL,             -- 1: Thứ 2 ... 7: Chủ Nhật
    quarter_name VARCHAR(10) NOT NULL,    -- '2026-Q1'
    is_weekend BOOLEAN NOT NULL,
    is_trading_day BOOLEAN NOT NULL DEFAULT TRUE,
    is_month_end BOOLEAN DEFAULT FALSE,
    is_quarter_end BOOLEAN DEFAULT FALSE
);

-- 3. BẢNG CHIỀU: BAN LÃNH ĐẠO & CỔ ĐÔNG (dim_stakeholder)
CREATE TABLE IF NOT EXISTS master_data.dim_stakeholder (
    stakeholder_sk SERIAL PRIMARY KEY,
    stakeholder_code VARCHAR(100) UNIQUE,
    full_name VARCHAR(255) NOT NULL,
    stakeholder_type VARCHAR(50) NOT NULL, -- 'INDIVIDUAL', 'ORGANIZATION'
    tax_code VARCHAR(50),
    country VARCHAR(50) DEFAULT 'Vietnam',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 4. BẢNG CHIỀU: CHỈ SỐ THỊ TRƯỜNG (dim_market_index)
CREATE TABLE IF NOT EXISTS master_data.dim_market_index (
    index_sk SERIAL PRIMARY KEY,
    index_symbol VARCHAR(30) UNIQUE NOT NULL, -- 'VNINDEX', 'VN30', 'VNFINLEAD'
    index_name VARCHAR(255) NOT NULL,
    exchange VARCHAR(20) DEFAULT 'HOSE',
    is_active BOOLEAN DEFAULT TRUE
);

-- ==============================================================================
-- PHẦN III: SCHEMA mart_technical (Data Mart Kỹ Thuật & Vĩ Mô)
-- Tiền tố chuẩn: fact_, view_
-- ==============================================================================

-- 1. BẢNG SỰ THẬT: GIÁ KHỚP LỆNH HÀNG NGÀY (fact_daily_market_ohlcv)
CREATE TABLE IF NOT EXISTS mart_technical.fact_daily_market_ohlcv (
    fact_id BIGSERIAL PRIMARY KEY,
    bank_sk INT NOT NULL REFERENCES master_data.dim_bank(bank_sk),
    date_sk INT NOT NULL REFERENCES master_data.dim_date(date_sk),
    open_price NUMERIC(15, 2) NOT NULL,
    high_price NUMERIC(15, 2) NOT NULL,
    low_price NUMERIC(15, 2) NOT NULL,
    close_price NUMERIC(15, 2) NOT NULL,
    volume BIGINT NOT NULL,
    turnover_vnd NUMERIC(20, 2),
    return_daily_pct NUMERIC(8, 4),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_tech_bank_date UNIQUE (bank_sk, date_sk)
);
CREATE INDEX IF NOT EXISTS idx_tech_ohlcv_bank_date ON mart_technical.fact_daily_market_ohlcv(bank_sk, date_sk);

-- 2. BẢNG SỰ THẬT: CHỈ SỐ KINH TẾ VĨ MÔ (fact_macro_indicators)
CREATE TABLE IF NOT EXISTS mart_technical.fact_macro_indicators (
    fact_id BIGSERIAL PRIMARY KEY,
    date_sk INT NOT NULL REFERENCES master_data.dim_date(date_sk),
    indicator_code VARCHAR(50) NOT NULL,   -- 'INDEX_VNINDEX_CLOSE', 'SBV_REFINANCING_RATE', 'USDVND_RATE'
    indicator_name VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL,
    value NUMERIC(18, 4) NOT NULL,
    unit VARCHAR(30),
    frequency VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_tech_macro_date UNIQUE (indicator_code, date_sk)
);
CREATE INDEX IF NOT EXISTS idx_tech_macro_code_date ON mart_technical.fact_macro_indicators(indicator_code, date_sk);

-- 3. VIEW PHÂN TÍCH KỸ THUẬT & SMA
CREATE OR REPLACE VIEW mart_technical.view_technical_market_daily AS
SELECT 
    b.ticker,
    b.short_name,
    b.tier_group,
    d.full_date,
    f.date_sk,
    f.open_price,
    f.high_price,
    f.low_price,
    f.close_price,
    f.volume,
    f.turnover_vnd,
    f.return_daily_pct,
    ROUND(AVG(f.close_price) OVER(PARTITION BY f.bank_sk ORDER BY f.date_sk ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 2) AS sma_20,
    ROUND(AVG(f.close_price) OVER(PARTITION BY f.bank_sk ORDER BY f.date_sk ROWS BETWEEN 49 PRECEDING AND CURRENT ROW), 2) AS sma_50,
    ROUND(AVG(f.close_price) OVER(PARTITION BY f.bank_sk ORDER BY f.date_sk ROWS BETWEEN 199 PRECEDING AND CURRENT ROW), 2) AS sma_200,
    ROUND(AVG(f.volume) OVER(PARTITION BY f.bank_sk ORDER BY f.date_sk ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 0) AS avg_volume_20d,
    CASE 
        WHEN AVG(f.volume) OVER(PARTITION BY f.bank_sk ORDER BY f.date_sk ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) > 0 
        THEN ROUND(f.volume / AVG(f.volume) OVER(PARTITION BY f.bank_sk ORDER BY f.date_sk ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 2)
        ELSE 1.0 
    END AS volume_surge_ratio
FROM mart_technical.fact_daily_market_ohlcv f
JOIN master_data.dim_bank b ON f.bank_sk = b.bank_sk
JOIN master_data.dim_date d ON f.date_sk = d.date_sk;

-- 4. VIEW TƯƠNG QUAN THỊ TRƯỜNG & CHÍNH SÁCH TIỀN TỆ VĨ MÔ
CREATE OR REPLACE VIEW mart_technical.view_macro_market_correlation AS
WITH vnindex AS (
    SELECT date_sk, value AS vnindex_close
    FROM mart_technical.fact_macro_indicators
    WHERE indicator_code = 'INDEX_VNINDEX_CLOSE'
),
sbv_rate AS (
    SELECT date_sk, value AS sbv_refinancing_rate
    FROM mart_technical.fact_macro_indicators
    WHERE indicator_code = 'SBV_REFINANCING_RATE'
),
usdvnd AS (
    SELECT date_sk, value AS usdvnd_rate
    FROM mart_technical.fact_macro_indicators
    WHERE indicator_code = 'USDVND_RATE'
)
SELECT 
    b.ticker,
    b.tier_group,
    d.full_date,
    f.date_sk,
    f.close_price,
    f.return_daily_pct,
    f.volume,
    v.vnindex_close,
    s.sbv_refinancing_rate,
    u.usdvnd_rate
FROM mart_technical.fact_daily_market_ohlcv f
JOIN master_data.dim_bank b ON f.bank_sk = b.bank_sk
JOIN master_data.dim_date d ON f.date_sk = d.date_sk
LEFT JOIN vnindex v ON f.date_sk = v.date_sk
LEFT JOIN sbv_rate s ON f.date_sk = s.date_sk
LEFT JOIN usdvnd u ON f.date_sk = u.date_sk;

-- ==============================================================================
-- PHẦN IV: SCHEMA mart_camels (Data Mart Báo Cáo Tài Chính & Khung Rủi Ro CAMELS)
-- Tiền tố chuẩn: fact_, view_
-- ==============================================================================

-- 1. BẢNG SỰ THẬT: BÁO CÁO TÀI CHÍNH HÀNG QUÝ (fact_quarterly_financial_statements)
CREATE TABLE IF NOT EXISTS mart_camels.fact_quarterly_financial_statements (
    fact_id BIGSERIAL PRIMARY KEY,
    bank_sk INT NOT NULL REFERENCES master_data.dim_bank(bank_sk),
    fiscal_year INT NOT NULL,
    fiscal_quarter INT NOT NULL,           -- 1, 2, 3, 4
    period_date_sk INT REFERENCES master_data.dim_date(date_sk),
    -- Cân đối Kế toán (Balance Sheet)
    total_assets NUMERIC(20, 2),
    cash_and_gold NUMERIC(20, 2),
    balances_with_sbv NUMERIC(20, 2),
    loans_to_customers NUMERIC(20, 2),
    provision_for_credit_losses NUMERIC(20, 2), -- Số dư dự phòng lũy kế rủi ro cho vay (CĐKT)
    total_liabilities NUMERIC(20, 2),
    deposits_from_customers NUMERIC(20, 2),
    owners_equity NUMERIC(20, 2),
    charter_capital NUMERIC(20, 2),
    -- Báo cáo Kết quả Kinh doanh (Income Statement)
    net_interest_income NUMERIC(20, 2),
    net_fee_income NUMERIC(20, 2),
    net_gain_fx NUMERIC(20, 2),                         -- Lãi/lỗ thuần kinh doanh ngoại hối và vàng
    net_gain_securities NUMERIC(20, 2),                 -- Lãi/lỗ thuần kinh doanh & đầu tư chứng khoán
    other_operating_income_residual NUMERIC(20, 2),     -- Thu nhập hoạt động khác (thu hồi nợ ngoại bảng...)
    total_operating_income NUMERIC(20, 2),
    general_and_admin_expenses NUMERIC(20, 2),
    provision_expense NUMERIC(20, 2),                   -- Chi phí trích lập dự phòng rủi ro tín dụng trong kỳ (KQKD)
    net_profit_before_tax NUMERIC(20, 2),
    net_profit_after_tax NUMERIC(20, 2),
    is_standalone_quarter BOOLEAN DEFAULT TRUE,         -- Đánh dấu số riêng quý hay lũy kế YTD
    reporting_scope VARCHAR(20) DEFAULT 'CONSOLIDATED', -- CONSOLIDATED (Hợp nhất) hoặc PARENT (Riêng lẻ)
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_camels_bctc UNIQUE (bank_sk, fiscal_year, fiscal_quarter)
);
CREATE INDEX IF NOT EXISTS idx_camels_bctc_bank ON mart_camels.fact_quarterly_financial_statements(bank_sk, fiscal_year, fiscal_quarter);

-- 2. BẢNG SỰ THẬT: TỶ SỐ TÀI CHÍNH & CHỈ SỐ CAMELS (fact_quarterly_banking_ratios)
CREATE TABLE IF NOT EXISTS mart_camels.fact_quarterly_banking_ratios (
    fact_id BIGSERIAL PRIMARY KEY,
    bank_sk INT NOT NULL REFERENCES master_data.dim_bank(bank_sk),
    fiscal_year INT NOT NULL,
    fiscal_quarter INT NOT NULL,
    period_date_sk INT REFERENCES master_data.dim_date(date_sk),
    -- Định giá
    pb_ratio NUMERIC(14, 4),
    pe_ratio NUMERIC(14, 4),
    -- Khung CAMELS
    roe NUMERIC(14, 4),
    roa NUMERIC(14, 4),
    net_interest_margin NUMERIC(14, 4),     -- NIM
    cost_to_income_ratio NUMERIC(14, 4),    -- CIR
    npl_ratio NUMERIC(14, 4),               -- Nợ xấu NPL
    loan_loss_reserve_to_npls NUMERIC(14, 4),-- Bao phủ nợ xấu LLR
    capital_adequacy_ratio NUMERIC(14, 4),  -- CAR (Basel II)
    casa_ratio NUMERIC(14, 4),              -- CASA
    loan_to_deposit_ratio NUMERIC(14, 4),   -- LDR công bố (reported)
    ldr_simple NUMERIC(14, 4),              -- LDR đơn giản = loans / deposits
    credit_cost_ratio NUMERIC(14, 4),       -- Chi phí tín dụng = (provision_expense * 4) / avg_loans
    estimated_npl_amount NUMERIC(20, 2),    -- Số dư nợ xấu ước tính = npl_ratio * loans
    loan_growth_yoy NUMERIC(14, 4),         -- Tăng trưởng dư nợ cho vay cùng kỳ
    deposit_growth_yoy NUMERIC(14, 4),      -- Tăng trưởng tiền gửi cùng kỳ
    credit_deposit_gap NUMERIC(14, 4),      -- Chênh lệch tăng trưởng tín dụng - huy động
    avg_yield_on_assets NUMERIC(14, 4),
    avg_cost_of_funds NUMERIC(14, 4),       -- COF
    formula_version VARCHAR(20) DEFAULT 'v2.0-Equity',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_camels_ratios UNIQUE (bank_sk, fiscal_year, fiscal_quarter)
);
CREATE INDEX IF NOT EXISTS idx_camels_ratios_bank ON mart_camels.fact_quarterly_banking_ratios(bank_sk, fiscal_year, fiscal_quarter);

-- 3. VIEW RADAR SỨC KHỎE NGÂN HÀNG CAMELS
CREATE OR REPLACE VIEW mart_camels.view_camels_radar AS
SELECT 
    b.bank_sk,
    b.ticker,
    b.short_name,
    b.tier_group,
    r.fiscal_year,
    r.fiscal_quarter,
    -- Trụ cột C: Vốn (Capital Adequacy)
    r.capital_adequacy_ratio AS c_capital_car,
    r.capital_adequacy_ratio AS c_car,
    -- Trụ cột A: Chất lượng tài sản (Asset Quality)
    r.npl_ratio AS a_asset_quality_npl,
    r.npl_ratio AS a_npl,
    r.loan_loss_reserve_to_npls AS a_provision_llr,
    r.loan_loss_reserve_to_npls AS a_llr,
    -- Trụ cột M: Hiệu quả quản trị (Management)
    r.cost_to_income_ratio AS m_management_cir,
    r.cost_to_income_ratio AS m_cir,
    -- Trụ cột E: Thu nhập & Sinh lời (Earnings)
    r.roe AS e_earnings_roe,
    r.roe AS e_roe,
    r.net_interest_margin AS e_earnings_nim,
    r.net_interest_margin AS e_nim,
    -- Trụ cột L: Thanh khoản (Liquidity)
    r.loan_to_deposit_ratio AS l_liquidity_ldr,
    r.loan_to_deposit_ratio AS l_ldr,
    r.casa_ratio AS l_liquidity_casa,
    r.casa_ratio AS l_casa
FROM mart_camels.fact_quarterly_banking_ratios r
JOIN master_data.dim_bank b ON r.bank_sk = b.bank_sk;

-- 4. VIEW BÓC TÁCH CHẤT LƯỢNG LỢI NHUẬN & CHI PHÍ DỰ PHÒNG (view_earnings_quality_breakdown)
-- Phục vụ Câu hỏi 4 Equity Research: Lợi nhuận tạo ra có bền vững không?
CREATE OR REPLACE VIEW mart_camels.view_earnings_quality_breakdown AS
SELECT 
    b.bank_sk,
    b.ticker,
    b.short_name,
    b.tier_group,
    f.fiscal_year,
    f.fiscal_quarter,
    f.period_date_sk,
    f.net_interest_income AS nii,
    f.net_fee_income AS nfi,
    COALESCE(f.net_gain_fx, 0) AS net_gain_fx,
    COALESCE(f.net_gain_securities, 0) AS net_gain_securities,
    COALESCE(f.other_operating_income_residual, f.total_operating_income - f.net_interest_income - f.net_fee_income) AS other_operating_income_residual,
    f.total_operating_income AS toi,
    f.general_and_admin_expenses AS opex,
    (f.total_operating_income - f.general_and_admin_expenses) AS ppop,
    COALESCE(f.provision_expense, 0) AS provision_expense,
    f.net_profit_before_tax AS pbt,
    f.net_profit_after_tax AS npat,
    r.net_interest_margin AS nim,
    r.cost_to_income_ratio AS cir,
    r.credit_cost_ratio,
    r.roe,
    r.roa
FROM mart_camels.fact_quarterly_financial_statements f
JOIN master_data.dim_bank b ON f.bank_sk = b.bank_sk
LEFT JOIN mart_camels.fact_quarterly_banking_ratios r 
    ON f.bank_sk = r.bank_sk AND f.fiscal_year = r.fiscal_year AND f.fiscal_quarter = r.fiscal_quarter
WHERE b.bank_sk > 0;

-- ==============================================================================
-- PHẦN V: SCHEMA mart_valuation (Data Mart Định Giá Gordon P/B vs ROE)
-- Tiền tố chuẩn: view_
-- ==============================================================================

CREATE OR REPLACE VIEW mart_valuation.view_gordon_pb_roe_matrix AS
SELECT 
    b.bank_sk,
    b.ticker,
    b.short_name,
    b.tier_group,
    r.fiscal_year,
    r.fiscal_quarter,
    r.pb_ratio,
    r.roe,
    r.roe / NULLIF(r.pb_ratio, 0::numeric) AS roe_to_pb_efficiency,
    CASE 
        WHEN r.roe >= 0.18 AND r.pb_ratio <= 1.2 THEN 'VÙNG KIM CƯƠNG (RẺ & TỐT)'
        WHEN r.roe >= 0.18 AND r.pb_ratio > 1.2 THEN 'ĐẮT XẮT RA MIẾNG (TỐT & ĐẮT)'
        WHEN r.roe < 0.18 AND r.pb_ratio <= 1.2 THEN 'BẪY GIÁ RẺ (RẺ & YẾU)'
        ELSE 'RỦI RO CAO (YẾU & ĐẮT)'
    END AS gordon_quadrant,
    CASE 
        WHEN r.roe >= 0.18 AND r.pb_ratio <= 1.2 THEN 'VÙNG KIM CƯƠNG (RẺ & TỐT)'
        WHEN r.roe >= 0.18 AND r.pb_ratio > 1.2 THEN 'ĐẮT XẮT RA MIẾNG (TỐT & ĐẮT)'
        WHEN r.roe < 0.18 AND r.pb_ratio <= 1.2 THEN 'BẪY GIÁ RẺ (RẺ & YẾU)'
        ELSE 'RỦI RO CAO (YẾU & ĐẮT)'
    END AS gordon_zone
FROM mart_camels.fact_quarterly_banking_ratios r
JOIN master_data.dim_bank b ON r.bank_sk = b.bank_sk;

-- 2. VIEW MA TRẬN ĐỊNH GIÁ EQUITY RESEARCH TƯƠNG ĐỐI & NỘI TẠI
CREATE OR REPLACE VIEW mart_valuation.view_valuation_regime_matrix AS
SELECT 
    b.bank_sk,
    b.ticker,
    b.short_name,
    b.tier_group,
    r.fiscal_year,
    r.fiscal_quarter,
    r.period_date_sk,
    r.pb_ratio,
    r.pe_ratio,
    r.roe,
    r.cost_to_income_ratio,
    r.npl_ratio,
    r.loan_loss_reserve_to_npls,
    r.capital_adequacy_ratio,
    r.casa_ratio,
    r.loan_to_deposit_ratio,
    r.ldr_simple,
    r.credit_cost_ratio,
    CASE 
        WHEN r.roe >= 0.15 AND r.pb_ratio <= 1.2 THEN 'VUNG_KIM_CUONG_UNDERVALUED'
        WHEN r.roe >= 0.15 AND r.pb_ratio > 1.2 THEN 'VUNG_TANG_TRUONG_PREMIUM'
        WHEN r.roe < 0.15 AND r.pb_ratio <= 1.0 THEN 'VUNG_BAY_GIA_TRI_VALUE_TRAP'
        ELSE 'VUNG_DINH_GIA_CAO_OVERVALUED'
    END AS valuation_quadrant
FROM mart_camels.fact_quarterly_banking_ratios r
JOIN master_data.dim_bank b ON r.bank_sk = b.bank_sk
WHERE b.bank_sk > 0 AND r.pb_ratio IS NOT NULL AND r.roe IS NOT NULL;

-- ==============================================================================
-- PHẦN VI: SCHEMA mart_governance (Data Mart Quản Trị, Cổ Đông & Ban Lãnh Đạo)
-- Tiền tố chuẩn: fact_, bridge_, view_
-- ==============================================================================

-- 1. BẢNG CẦU NỐI: MẠNG LƯỚI QUẢN TRỊ (bridge_governance_network)
CREATE TABLE IF NOT EXISTS mart_governance.bridge_governance_network (
    bridge_id BIGSERIAL PRIMARY KEY,
    bank_sk INT NOT NULL REFERENCES master_data.dim_bank(bank_sk),
    stakeholder_sk INT NOT NULL REFERENCES master_data.dim_stakeholder(stakeholder_sk),
    relationship_type VARCHAR(50) NOT NULL, -- 'OFFICER', 'SHAREHOLDER', 'SUBSIDIARY'
    role_title VARCHAR(150),
    ownership_pct NUMERIC(8, 4),
    shares_quantity BIGINT,
    is_current BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_gov_bridge UNIQUE (bank_sk, stakeholder_sk, relationship_type)
);
CREATE INDEX IF NOT EXISTS idx_gov_bridge ON mart_governance.bridge_governance_network(bank_sk, stakeholder_sk);

-- 2. BẢNG SỰ THẬT: CƠ CẤU CỔ ĐÔNG LỚN (fact_bank_shareholders)
CREATE TABLE IF NOT EXISTS mart_governance.fact_bank_shareholders (
    id BIGSERIAL PRIMARY KEY,
    bank_sk INT NOT NULL REFERENCES master_data.dim_bank(bank_sk),
    ticker VARCHAR(10) NOT NULL REFERENCES master_data.dim_bank(ticker),
    shareholder_name VARCHAR(255) NOT NULL,
    shareholder_type VARCHAR(50),
    quantity BIGINT,
    ownership_pct NUMERIC(8, 4),
    update_date DATE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_gov_sh_bank_sk ON mart_governance.fact_bank_shareholders(bank_sk);
CREATE INDEX IF NOT EXISTS idx_gov_sh_ticker ON mart_governance.fact_bank_shareholders(ticker);

-- 3. BẢNG SỰ THẬT: BAN LÃNH ĐẠO & HĐQT (fact_bank_officers)
CREATE TABLE IF NOT EXISTS mart_governance.fact_bank_officers (
    id BIGSERIAL PRIMARY KEY,
    bank_sk INT NOT NULL REFERENCES master_data.dim_bank(bank_sk),
    ticker VARCHAR(10) NOT NULL REFERENCES master_data.dim_bank(ticker),
    officer_name VARCHAR(255) NOT NULL,
    position_title VARCHAR(150),
    ownership_pct NUMERIC(8, 4),
    shares_quantity BIGINT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_gov_off_bank_sk ON mart_governance.fact_bank_officers(bank_sk);
CREATE INDEX IF NOT EXISTS idx_gov_off_ticker ON mart_governance.fact_bank_officers(ticker);

-- 4. BẢNG SỰ THẬT: CÔNG TY CON & CÔNG TY LIÊN KẾT (fact_bank_subsidiaries)
CREATE TABLE IF NOT EXISTS mart_governance.fact_bank_subsidiaries (
    id BIGSERIAL PRIMARY KEY,
    bank_sk INT NOT NULL REFERENCES master_data.dim_bank(bank_sk),
    ticker VARCHAR(10) NOT NULL REFERENCES master_data.dim_bank(ticker),
    subsidiary_name VARCHAR(255) NOT NULL,
    ownership_pct NUMERIC(8, 4),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_gov_sub_bank_sk ON mart_governance.fact_bank_subsidiaries(bank_sk);
CREATE INDEX IF NOT EXISTS idx_gov_sub_ticker ON mart_governance.fact_bank_subsidiaries(ticker);

-- 5. BẢNG SỰ THẬT: SỰ KIỆN DOANH NGHIỆP & CỔ TỨC (fact_corporate_events)
CREATE TABLE IF NOT EXISTS mart_governance.fact_corporate_events (
    id BIGSERIAL PRIMARY KEY,
    bank_sk INT NOT NULL REFERENCES master_data.dim_bank(bank_sk),
    ticker VARCHAR(10) NOT NULL REFERENCES master_data.dim_bank(ticker),
    event_code VARCHAR(100),
    event_name_vi TEXT NOT NULL,
    public_date DATE,
    value_per_share NUMERIC(15, 2), -- Tiền cổ tức VNĐ/cp (nếu có)
    exercise_ratio NUMERIC(8, 4),  -- Tỷ lệ cổ tức/cổ phiếu thưởng (VD: 0.1 = 10%)
    exright_date DATE,             -- Ngày giao dịch không hưởng quyền (GDKHQ)
    record_date DATE,              -- Ngày chốt danh sách cổ đông
    payout_date DATE,              -- Ngày chi trả tiền về tài khoản
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_gov_ev_bank_sk ON mart_governance.fact_corporate_events(bank_sk);
CREATE INDEX IF NOT EXISTS idx_gov_ev_ticker ON mart_governance.fact_corporate_events(ticker);

-- 6. VIEWS PHỤC VỤ TRUY VẤN QUẢN TRỊ
CREATE OR REPLACE VIEW mart_governance.view_governance_network AS
SELECT 
    bg.bridge_id,
    b.ticker AS bank_ticker,
    b.short_name AS bank_name,
    b.tier_group,
    s.stakeholder_code,
    s.full_name AS stakeholder_name,
    s.stakeholder_type,
    bg.relationship_type,
    bg.role_title,
    bg.ownership_pct,
    bg.shares_quantity,
    bg.is_current,
    bg.updated_at
FROM mart_governance.bridge_governance_network bg
JOIN master_data.dim_bank b ON bg.bank_sk = b.bank_sk
JOIN master_data.dim_stakeholder s ON bg.stakeholder_sk = s.stakeholder_sk;

-- ==============================================================================
-- PHẦN VII: SCHEMA mart_sentiment (Data Mart Bản Tin & Tâm Lý Truyền Thông)
-- Tiền tố chuẩn: fact_, view_
-- ==============================================================================

CREATE TABLE IF NOT EXISTS mart_sentiment.fact_media_sentiment_daily (
    fact_id BIGSERIAL PRIMARY KEY,
    bank_sk INT NOT NULL REFERENCES master_data.dim_bank(bank_sk),
    date_sk INT NOT NULL REFERENCES master_data.dim_date(date_sk),
    article_external_id VARCHAR(100),
    title TEXT NOT NULL,
    source_name VARCHAR(100),
    source_url TEXT,
    is_official_disclosure BOOLEAN DEFAULT FALSE,
    category_code VARCHAR(50),             -- Metadata sự kiện: 'BOD', 'AGM', 'IndTr', 'OIss', 'ManaC'
    category_name VARCHAR(255),            -- Diễn giải: 'Nghị quyết HĐQT', 'Đại hội cổ đông', 'Giao dịch nội bộ'
    sentiment_score NUMERIC(6, 4),         -- Thang đo [-1.0, 1.0]
    sentiment_label VARCHAR(20),           -- 'POSITIVE', 'NEGATIVE', 'NEUTRAL'
    attachment_pdf_url TEXT,               -- Link tải file PDF gốc có dấu đỏ của Sở
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_senti_bank_article UNIQUE (bank_sk, article_external_id)
);
CREATE INDEX IF NOT EXISTS idx_senti_bank_date ON mart_sentiment.fact_media_sentiment_daily(bank_sk, date_sk);

CREATE OR REPLACE VIEW mart_sentiment.view_disclosure_feed AS
SELECT 
    f.fact_id,
    b.ticker,
    b.short_name AS bank_name,
    b.tier_group,
    d.full_date,
    f.date_sk,
    f.article_external_id,
    f.title,
    f.source_name,
    f.source_url,
    f.is_official_disclosure,
    f.category_code,
    f.category_name,
    f.sentiment_score,
    f.sentiment_label,
    f.attachment_pdf_url,
    CASE WHEN f.attachment_pdf_url IS NOT NULL THEN TRUE ELSE FALSE END AS has_attachment_pdf
FROM mart_sentiment.fact_media_sentiment_daily f
JOIN master_data.dim_bank b ON f.bank_sk = b.bank_sk
JOIN master_data.dim_date d ON f.date_sk = d.date_sk;


