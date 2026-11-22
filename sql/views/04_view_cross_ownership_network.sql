-- ==============================================================================
-- VIEW: mart_governance.view_governance_network
-- FILE: sql/views/04_view_cross_ownership_network.sql
-- ==============================================================================

CREATE OR REPLACE VIEW mart_governance.view_governance_network AS
SELECT bg.bridge_id,
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
   FROM ((mart_governance.bridge_governance_network bg
     JOIN master_data.dim_bank b ON ((bg.bank_sk = b.bank_sk)))
     JOIN master_data.dim_stakeholder s ON ((bg.stakeholder_sk = s.stakeholder_sk)));;
