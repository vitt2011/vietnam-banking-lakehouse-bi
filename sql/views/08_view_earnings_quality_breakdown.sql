-- ==============================================================================
-- VIEW: mart_camels.view_earnings_quality_breakdown
-- FILE: sql/views/08_view_earnings_quality_breakdown.sql
-- ==============================================================================

CREATE OR REPLACE VIEW mart_camels.view_earnings_quality_breakdown AS
SELECT b.bank_sk,
    b.ticker,
    b.short_name,
    b.tier_group,
    f.fiscal_year,
    f.fiscal_quarter,
    f.period_date_sk,
    f.net_interest_income AS nii,
    f.net_fee_income AS nfi,
    COALESCE(f.net_gain_fx, (0)::numeric) AS net_gain_fx,
    COALESCE(f.net_gain_securities, (0)::numeric) AS net_gain_securities,
    COALESCE(f.other_operating_income_residual, ((f.total_operating_income - f.net_interest_income) - f.net_fee_income)) AS other_operating_income_residual,
    f.total_operating_income AS toi,
    f.general_and_admin_expenses AS opex,
    (f.total_operating_income - f.general_and_admin_expenses) AS ppop,
    COALESCE(f.provision_expense, (0)::numeric) AS provision_expense,
    f.net_profit_before_tax AS pbt,
    f.net_profit_after_tax AS npat,
    r.net_interest_margin AS nim,
    r.cost_to_income_ratio AS cir,
    r.credit_cost_ratio,
    r.roe,
    r.roa
   FROM ((mart_camels.fact_quarterly_financial_statements f
     JOIN master_data.dim_bank b ON ((f.bank_sk = b.bank_sk)))
     LEFT JOIN mart_camels.fact_quarterly_banking_ratios r ON (((f.bank_sk = r.bank_sk) AND (f.fiscal_year = r.fiscal_year) AND (f.fiscal_quarter = r.fiscal_quarter))))
  WHERE (b.bank_sk > 0);;
