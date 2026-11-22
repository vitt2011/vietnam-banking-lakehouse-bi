-- ==============================================================================
-- VIEW: mart_governance.view_bank_officers_list
-- FILE: sql/views/07_view_bank_officers_list.sql
-- ==============================================================================

CREATE OR REPLACE VIEW mart_governance.view_bank_officers_list AS
SELECT o.ticker,
    b.short_name AS bank_name,
    b.tier_group,
    o.officer_name,
    o.position_title,
    o.ownership_pct,
    o.shares_quantity
   FROM (mart_governance.fact_bank_officers o
     JOIN master_data.dim_bank b ON (((o.ticker)::text = (b.ticker)::text)))
  ORDER BY o.ticker, o.ownership_pct DESC;;
