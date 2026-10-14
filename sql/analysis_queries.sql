-- Example analytical queries against the star schema (PostgreSQL / SQLite compatible unless noted).
-- Outlier-flagged sales are excluded so a handful of extreme prices do not distort averages.

-- 1. Headline numbers: total sales, average price and price range
SELECT COUNT(*)            AS sales,
       ROUND(AVG(price))   AS avg_price,
       MIN(price)          AS min_price,
       MAX(price)          AS max_price
FROM fact_sales
WHERE is_outlier = FALSE;

-- 2. Average price and volume by region, most expensive first
SELECT l.region,
       COUNT(*)          AS sales,
       ROUND(AVG(f.price)) AS avg_price
FROM fact_sales f
JOIN dim_location l ON l.location_key = f.location_key
WHERE f.is_outlier = FALSE
GROUP BY l.region
ORDER BY avg_price DESC;

-- 3. Year-on-year change in national average price
WITH yearly AS (
    SELECT d.year, AVG(f.price) AS avg_price
    FROM fact_sales f
    JOIN dim_date d ON d.date_key = f.date_key
    WHERE f.is_outlier = FALSE
    GROUP BY d.year
)
SELECT year,
       ROUND(avg_price)                                                         AS avg_price,
       ROUND(100.0 * (avg_price - LAG(avg_price) OVER (ORDER BY year))
             / LAG(avg_price) OVER (ORDER BY year), 2)                          AS yoy_pct
FROM yearly
ORDER BY year;

-- 4. Seasonality: which calendar month has the most sales?
SELECT d.month, d.month_name,
       COUNT(*)            AS sales,
       ROUND(AVG(f.price)) AS avg_price
FROM fact_sales f
JOIN dim_date d ON d.date_key = f.date_key
WHERE f.is_outlier = FALSE
GROUP BY d.month, d.month_name
ORDER BY d.month;

-- 5. Premium paid for new builds over existing homes, by property type
SELECT p.property_type,
       ROUND(AVG(CASE WHEN p.is_new_build THEN f.price END)) AS new_build_avg,
       ROUND(AVG(CASE WHEN NOT p.is_new_build THEN f.price END)) AS existing_avg,
       ROUND(100.0 * (AVG(CASE WHEN p.is_new_build THEN f.price END)
                    / AVG(CASE WHEN NOT p.is_new_build THEN f.price END) - 1), 1) AS premium_pct
FROM fact_sales f
JOIN dim_property p ON p.property_key = f.property_key
WHERE f.is_outlier = FALSE
  AND p.build_status IN ('New Build', 'Existing')
GROUP BY p.property_type
ORDER BY premium_pct DESC;

-- 6. Freehold vs leasehold average price within each property type
SELECT p.property_type, p.tenure,
       COUNT(*)            AS sales,
       ROUND(AVG(f.price)) AS avg_price
FROM fact_sales f
JOIN dim_property p ON p.property_key = f.property_key
WHERE f.is_outlier = FALSE
  AND p.tenure IN ('Freehold', 'Leasehold')
GROUP BY p.property_type, p.tenure
ORDER BY p.property_type, p.tenure;

-- 7. Ten most expensive postcode districts (at least 50 sales)
SELECT l.postcode_district,
       MIN(l.region)       AS region,
       COUNT(*)            AS sales,
       ROUND(AVG(f.price)) AS avg_price
FROM fact_sales f
JOIN dim_location l ON l.location_key = f.location_key
WHERE f.is_outlier = FALSE
  AND l.postcode_district <> 'UNKNOWN'
GROUP BY l.postcode_district
HAVING COUNT(*) >= 50
ORDER BY avg_price DESC
LIMIT 10;

-- 8. Rank districts within their region by average price (window function)
WITH district_avg AS (
    SELECT l.region, l.district,
           COUNT(*)          AS sales,
           AVG(f.price)      AS avg_price
    FROM fact_sales f
    JOIN dim_location l ON l.location_key = f.location_key
    WHERE f.is_outlier = FALSE
    GROUP BY l.region, l.district
    HAVING COUNT(*) >= 100
)
SELECT region, district, sales, ROUND(avg_price) AS avg_price,
       RANK() OVER (PARTITION BY region ORDER BY avg_price DESC) AS rank_in_region
FROM district_avg
ORDER BY region, rank_in_region
LIMIT 50;

-- 9. 3-month moving average of the national monthly average price
WITH monthly AS (
    SELECT d.year_month, AVG(f.price) AS avg_price
    FROM fact_sales f
    JOIN dim_date d ON d.date_key = f.date_key
    WHERE f.is_outlier = FALSE
    GROUP BY d.year_month
)
SELECT year_month,
       ROUND(avg_price) AS avg_price,
       ROUND(AVG(avg_price) OVER (ORDER BY year_month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)) AS moving_avg_3m
FROM monthly
ORDER BY year_month;

-- 10. UK financial year (Apr to Mar) totals
SELECT d.uk_financial_year,
       COUNT(*)            AS sales,
       ROUND(AVG(f.price)) AS avg_price,
       SUM(f.price)        AS total_value
FROM fact_sales f
JOIN dim_date d ON d.date_key = f.date_key
WHERE f.is_outlier = FALSE
GROUP BY d.uk_financial_year
ORDER BY d.uk_financial_year;

-- 11. Data-quality check: share of sales flagged as outliers or with invalid postcodes
SELECT ROUND(100.0 * SUM(CASE WHEN is_outlier THEN 1 ELSE 0 END) / COUNT(*), 3)           AS outlier_pct,
       ROUND(100.0 * SUM(CASE WHEN is_valid_postcode THEN 0 ELSE 1 END) / COUNT(*), 3)    AS invalid_postcode_pct
FROM fact_sales;
