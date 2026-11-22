-- ==============================================================================
-- VIEW: mart_camels.view_camels_radar
-- FILE: sql/views/02_view_camels_radar_ranking.sql
-- ==============================================================================

CREATE OR REPLACE VIEW mart_camels.view_camels_radar AS
SELECT b.bank_sk,
    b.ticker,
    b.short_name,
    b.tier_group,
    r.fiscal_year,
    r.fiscal_quarter,
    r.capital_adequacy_ratio AS c_capital_car,
    r.capital_adequacy_ratio AS c_car,
    r.npl_ratio AS a_asset_quality_npl,
    r.npl_ratio AS a_npl,
    r.loan_loss_reserve_to_npls AS a_provision_llr,
    r.loan_loss_reserve_to_npls AS a_llr,
    r.cost_to_income_ratio AS m_management_cir,
    r.cost_to_income_ratio AS m_cir,
    r.roe AS e_earnings_roe,
    r.roe AS e_roe,
    r.net_interest_margin AS e_earnings_nim,
    r.net_interest_margin AS e_nim,
    r.loan_to_deposit_ratio AS l_liquidity_ldr,
    r.loan_to_deposit_ratio AS l_ldr,
    r.casa_ratio AS l_liquidity_casa,
    r.casa_ratio AS l_casa
   FROM (mart_camels.fact_quarterly_banking_ratios r
     JOIN master_data.dim_bank b ON ((r.bank_sk = b.bank_sk)));;
