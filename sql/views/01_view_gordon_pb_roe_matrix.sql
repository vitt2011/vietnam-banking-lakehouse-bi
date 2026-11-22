-- ==============================================================================
-- VIEW: mart_valuation.view_gordon_pb_roe_matrix
-- FILE: sql/views/01_view_gordon_pb_roe_matrix.sql
-- ==============================================================================

CREATE OR REPLACE VIEW mart_valuation.view_gordon_pb_roe_matrix AS
SELECT b.bank_sk,
    b.ticker,
    b.short_name,
    b.tier_group,
    r.fiscal_year,
    r.fiscal_quarter,
    r.pb_ratio,
    r.roe,
    (r.roe / NULLIF(r.pb_ratio, (0)::numeric)) AS roe_to_pb_efficiency,
        CASE
            WHEN ((r.roe >= 0.18) AND (r.pb_ratio <= 1.2)) THEN 'VÙNG KIM CƯƠNG (RẺ & TỐT)'::text
            WHEN ((r.roe >= 0.18) AND (r.pb_ratio > 1.2)) THEN 'ĐẮT XẮT RA MIẾNG (TỐT & ĐẮT)'::text
            WHEN ((r.roe < 0.18) AND (r.pb_ratio <= 1.2)) THEN 'BẪY GIÁ RẺ (RẺ & YẾU)'::text
            ELSE 'RỦI RO CAO (YẾU & ĐẮT)'::text
        END AS gordon_quadrant,
        CASE
            WHEN ((r.roe >= 0.18) AND (r.pb_ratio <= 1.2)) THEN 'VÙNG KIM CƯƠNG (RẺ & TỐT)'::text
            WHEN ((r.roe >= 0.18) AND (r.pb_ratio > 1.2)) THEN 'ĐẮT XẮT RA MIẾNG (TỐT & ĐẮT)'::text
            WHEN ((r.roe < 0.18) AND (r.pb_ratio <= 1.2)) THEN 'BẪY GIÁ RẺ (RẺ & YẾU)'::text
            ELSE 'RỦI RO CAO (YẾU & ĐẮT)'::text
        END AS gordon_zone
   FROM (mart_camels.fact_quarterly_banking_ratios r
     JOIN master_data.dim_bank b ON ((r.bank_sk = b.bank_sk)));;
