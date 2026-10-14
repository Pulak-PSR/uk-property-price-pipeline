-- Reporting views for Power BI. Outlier-flagged rows are excluded from price statistics.
-- Written to run on PostgreSQL and SQLite. Statements are separated by semicolons.

DROP VIEW IF EXISTS vw_monthly_avg_price_by_region;
CREATE VIEW vw_monthly_avg_price_by_region AS
SELECT
    d.year_month,
    d.year,
    d.month,
    l.region,
    COUNT(*)                          AS sales_count,
    ROUND(AVG(f.price), 0)            AS avg_price,
    MIN(f.price)                      AS min_price,
    MAX(f.price)                      AS max_price
FROM fact_sales f
JOIN dim_date d     ON d.date_key = f.date_key
JOIN dim_location l ON l.location_key = f.location_key
WHERE f.is_outlier = FALSE
GROUP BY d.year_month, d.year, d.month, l.region;

DROP VIEW IF EXISTS vw_price_by_property_type;
CREATE VIEW vw_price_by_property_type AS
SELECT
    d.year,
    p.property_type,
    COUNT(*)                          AS sales_count,
    ROUND(AVG(f.price), 0)            AS avg_price,
    MIN(f.price)                      AS min_price,
    MAX(f.price)                      AS max_price
FROM fact_sales f
JOIN dim_date d     ON d.date_key = f.date_key
JOIN dim_property p ON p.property_key = f.property_key
WHERE f.is_outlier = FALSE
GROUP BY d.year, p.property_type;

DROP VIEW IF EXISTS vw_new_build_vs_existing;
CREATE VIEW vw_new_build_vs_existing AS
SELECT
    d.year,
    d.quarter,
    p.build_status,
    COUNT(*)                          AS sales_count,
    ROUND(AVG(f.price), 0)            AS avg_price
FROM fact_sales f
JOIN dim_date d     ON d.date_key = f.date_key
JOIN dim_property p ON p.property_key = f.property_key
WHERE f.is_outlier = FALSE
  AND p.build_status IN ('New Build', 'Existing')
GROUP BY d.year, d.quarter, p.build_status;

-- Year-on-year growth in average price by district for the latest year in the data.
-- Districts need at least 100 sales in both years to avoid noisy small samples.
DROP VIEW IF EXISTS vw_top_20_districts_by_growth;
CREATE VIEW vw_top_20_districts_by_growth AS
WITH yearly AS (
    SELECT
        l.district,
        d.year,
        COUNT(*)       AS sales_count,
        AVG(f.price)   AS avg_price
    FROM fact_sales f
    JOIN dim_date d     ON d.date_key = f.date_key
    JOIN dim_location l ON l.location_key = f.location_key
    WHERE f.is_outlier = FALSE
      AND l.district <> 'UNKNOWN'
    GROUP BY l.district, d.year
),
with_prev AS (
    SELECT
        district,
        year,
        sales_count,
        avg_price,
        LAG(avg_price)   OVER (PARTITION BY district ORDER BY year) AS prev_avg_price,
        LAG(sales_count) OVER (PARTITION BY district ORDER BY year) AS prev_sales_count
    FROM yearly
),
growth AS (
    SELECT
        district,
        year,
        sales_count,
        ROUND(avg_price, 0)      AS avg_price,
        ROUND(prev_avg_price, 0) AS prev_avg_price,
        ROUND(100.0 * (avg_price - prev_avg_price) / prev_avg_price, 2) AS yoy_growth_pct
    FROM with_prev
    WHERE prev_avg_price IS NOT NULL
      AND sales_count >= 100
      AND prev_sales_count >= 100
      AND year = (SELECT MAX(year) FROM yearly)
),
ranked AS (
    SELECT
        g.*,
        ROW_NUMBER() OVER (ORDER BY yoy_growth_pct DESC) AS growth_rank
    FROM growth g
)
SELECT growth_rank, district, year, sales_count, prev_avg_price, avg_price, yoy_growth_pct
FROM ranked
WHERE growth_rank <= 20;

-- Region summary for the map page.
DROP VIEW IF EXISTS vw_region_summary;
CREATE VIEW vw_region_summary AS
SELECT
    l.region,
    d.year,
    COUNT(*)                          AS sales_count,
    ROUND(AVG(f.price), 0)            AS avg_price
FROM fact_sales f
JOIN dim_date d     ON d.date_key = f.date_key
JOIN dim_location l ON l.location_key = f.location_key
WHERE f.is_outlier = FALSE
GROUP BY l.region, d.year;
