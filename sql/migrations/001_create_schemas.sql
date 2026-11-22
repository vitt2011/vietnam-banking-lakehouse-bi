-- ==============================================================================
-- MIGRATION: 001_create_schemas.sql
-- CƠ SỞ DỮ LIỆU: Stock_Warehouse (PostgreSQL 16)
-- KIẾN TRÚC: Enterprise Multi-Schema Lakehouse Marts
-- ==============================================================================

CREATE SCHEMA IF NOT EXISTS master_data;      -- Dữ liệu chủ (MDM - Dim Tables)
CREATE SCHEMA IF NOT EXISTS silver_analytics; -- Vùng staging chuẩn hóa dữ liệu tài chính
CREATE SCHEMA IF NOT EXISTS mart_valuation;   -- Data Mart Module 1: Định giá Gordon P/B vs ROE
CREATE SCHEMA IF NOT EXISTS mart_camels;      -- Data Mart Module 2: Thẻ điểm rủi ro CAMELS
CREATE SCHEMA IF NOT EXISTS mart_technical;   -- Data Mart Module 3: Kỹ thuật nến OHLCV & Vĩ mô
CREATE SCHEMA IF NOT EXISTS mart_governance;  -- Data Mart Module 4: Quản trị, Lãnh đạo & Cổ đông
CREATE SCHEMA IF NOT EXISTS mart_sentiment;   -- Data Mart Module 5: Tin tức & Tâm lý Thị trường
CREATE SCHEMA IF NOT EXISTS ops;              -- Điều phối, giám sát trạng thái pipeline
CREATE SCHEMA IF NOT EXISTS metadata;         -- Quản trị từ điển siêu dữ liệu & Catalog
