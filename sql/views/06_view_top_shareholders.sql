-- ==============================================================================
-- VIEW: mart_governance.view_top_shareholders
-- FILE: sql/views/06_view_top_shareholders.sql
-- ==============================================================================

CREATE OR REPLACE VIEW mart_governance.view_top_shareholders AS
SELECT s.ticker,
    b.short_name AS bank_name,
    b.tier_group,
    s.shareholder_name,
    s.quantity,
    s.ownership_pct,
    s.update_date
   FROM (mart_governance.fact_bank_shareholders s
     JOIN master_data.dim_bank b ON (((s.ticker)::text = (b.ticker)::text)))
  ORDER BY s.ticker, s.ownership_pct DESC;;
