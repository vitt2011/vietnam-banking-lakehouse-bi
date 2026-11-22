-- ==============================================================================
-- VIEW: mart_valuation.view_valuation_regime_matrix
-- FILE: sql/views/10_view_valuation_regime_matrix.sql
-- ==============================================================================

CREATE OR REPLACE VIEW mart_valuation.view_valuation_regime_matrix AS
SELECT b.bank_sk,
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
            WHEN ((r.roe >= 0.15) AND (r.pb_ratio <= 1.2)) THEN 'VUNG_KIM_CUONG_UNDERVALUED'::text
            WHEN ((r.roe >= 0.15) AND (r.pb_ratio > 1.2)) THEN 'VUNG_TANG_TRUONG_PREMIUM'::text
            WHEN ((r.roe < 0.15) AND (r.pb_ratio <= 1.0)) THEN 'VUNG_BAY_GIA_TRI_VALUE_TRAP'::text
            ELSE 'VUNG_DINH_GIA_CAO_OVERVALUED'::text
        END AS valuation_quadrant
   FROM (mart_camels.fact_quarterly_banking_ratios r
     JOIN master_data.dim_bank b ON ((r.bank_sk = b.bank_sk)))
  WHERE ((b.bank_sk > 0) AND (r.pb_ratio IS NOT NULL) AND (r.roe IS NOT NULL));;
