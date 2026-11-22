-- ==============================================================================
-- VIEW: mart_sentiment.view_disclosure_feed
-- FILE: sql/views/05_view_news_sentiment_momentum.sql
-- ==============================================================================

CREATE OR REPLACE VIEW mart_sentiment.view_disclosure_feed AS
SELECT f.fact_id,
    b.ticker,
    b.short_name AS bank_name,
    b.tier_group,
    d.full_date,
    f.date_sk,
    f.article_external_id,
    f.title,
    f.source_name,
    f.source_url,
    f.is_official_disclosure,
    f.category_code,
    f.category_name,
    f.sentiment_score,
    f.sentiment_label,
    f.attachment_pdf_url,
        CASE
            WHEN (f.attachment_pdf_url IS NOT NULL) THEN true
            ELSE false
        END AS has_attachment_pdf
   FROM ((mart_sentiment.fact_media_sentiment_daily f
     JOIN master_data.dim_bank b ON ((f.bank_sk = b.bank_sk)))
     JOIN master_data.dim_date d ON ((f.date_sk = d.date_sk)));;
