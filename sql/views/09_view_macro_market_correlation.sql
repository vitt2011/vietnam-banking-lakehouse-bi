-- ==============================================================================
-- VIEW: mart_technical.view_macro_market_correlation
-- FILE: sql/views/09_view_macro_market_correlation.sql
-- ==============================================================================

CREATE OR REPLACE VIEW mart_technical.view_macro_market_correlation AS
WITH vnindex AS (
         SELECT fact_macro_indicators.date_sk,
            fact_macro_indicators.value AS vnindex_close
           FROM mart_technical.fact_macro_indicators
          WHERE ((fact_macro_indicators.indicator_code)::text = 'INDEX_VNINDEX_CLOSE'::text)
        ), sbv_rate AS (
         SELECT fact_macro_indicators.date_sk,
            fact_macro_indicators.value AS sbv_refinancing_rate
           FROM mart_technical.fact_macro_indicators
          WHERE ((fact_macro_indicators.indicator_code)::text = 'SBV_REFINANCING_RATE'::text)
        ), usdvnd AS (
         SELECT fact_macro_indicators.date_sk,
            fact_macro_indicators.value AS usdvnd_rate
           FROM mart_technical.fact_macro_indicators
          WHERE ((fact_macro_indicators.indicator_code)::text = 'USDVND_RATE'::text)
        )
 SELECT b.ticker,
    b.tier_group,
    d.full_date,
    f.date_sk,
    f.close_price,
    f.return_daily_pct,
    f.volume,
    v.vnindex_close,
    s.sbv_refinancing_rate,
    u.usdvnd_rate
   FROM (((((mart_technical.fact_daily_market_ohlcv f
     JOIN master_data.dim_bank b ON ((f.bank_sk = b.bank_sk)))
     JOIN master_data.dim_date d ON ((f.date_sk = d.date_sk)))
     LEFT JOIN vnindex v ON ((f.date_sk = v.date_sk)))
     LEFT JOIN sbv_rate s ON ((f.date_sk = s.date_sk)))
     LEFT JOIN usdvnd u ON ((f.date_sk = u.date_sk)));;
