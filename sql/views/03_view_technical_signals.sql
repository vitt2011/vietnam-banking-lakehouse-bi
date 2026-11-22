-- ==============================================================================
-- VIEW: mart_technical.view_technical_market_daily
-- FILE: sql/views/03_view_technical_signals.sql
-- ==============================================================================

CREATE OR REPLACE VIEW mart_technical.view_technical_market_daily AS
SELECT b.ticker,
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
    round(avg(f.close_price) OVER (PARTITION BY f.bank_sk ORDER BY f.date_sk ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 2) AS sma_20,
    round(avg(f.close_price) OVER (PARTITION BY f.bank_sk ORDER BY f.date_sk ROWS BETWEEN 49 PRECEDING AND CURRENT ROW), 2) AS sma_50,
    round(avg(f.close_price) OVER (PARTITION BY f.bank_sk ORDER BY f.date_sk ROWS BETWEEN 199 PRECEDING AND CURRENT ROW), 2) AS sma_200,
    round(avg(f.volume) OVER (PARTITION BY f.bank_sk ORDER BY f.date_sk ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 0) AS avg_volume_20d,
        CASE
            WHEN (avg(f.volume) OVER (PARTITION BY f.bank_sk ORDER BY f.date_sk ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) > (0)::numeric) THEN round(((f.volume)::numeric / avg(f.volume) OVER (PARTITION BY f.bank_sk ORDER BY f.date_sk ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)), 2)
            ELSE 1.0
        END AS volume_surge_ratio
   FROM ((mart_technical.fact_daily_market_ohlcv f
     JOIN master_data.dim_bank b ON ((f.bank_sk = b.bank_sk)))
     JOIN master_data.dim_date d ON ((f.date_sk = d.date_sk)));;
