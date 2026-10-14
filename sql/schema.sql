-- Star schema for UK Price Paid Data (PostgreSQL syntax).
-- The pipeline creates the same tables through SQLAlchemy (src/uk_property_pipeline/load.py),
-- so running this file by hand is optional. It is also mounted for reference.

CREATE TABLE IF NOT EXISTS dim_date (
    date_key              INTEGER      PRIMARY KEY,          -- YYYYMMDD
    date                  DATE         NOT NULL UNIQUE,
    year                  SMALLINT     NOT NULL,
    quarter               SMALLINT     NOT NULL,
    month                 SMALLINT     NOT NULL,
    month_name            VARCHAR(10)  NOT NULL,
    year_month            CHAR(7)      NOT NULL,             -- YYYY-MM
    day_of_month          SMALLINT     NOT NULL,
    day_name              VARCHAR(10)  NOT NULL,
    uk_financial_year     VARCHAR(7)   NOT NULL,             -- e.g. 2024/25 (Apr to Mar)
    uk_financial_quarter  SMALLINT     NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_property (
    property_key  BIGINT       PRIMARY KEY,                  -- hash of the natural key
    property_type VARCHAR(20)  NOT NULL,
    build_status  VARCHAR(20)  NOT NULL,
    is_new_build  BOOLEAN      NOT NULL,
    tenure        VARCHAR(20)  NOT NULL,
    UNIQUE (property_type, build_status, tenure)
);

CREATE TABLE IF NOT EXISTS dim_location (
    location_key      BIGINT       PRIMARY KEY,              -- hash of the natural key
    postcode          VARCHAR(10)  NOT NULL,                 -- 'UNKNOWN' when invalid or missing
    postcode_district VARCHAR(5)   NOT NULL,
    town_city         VARCHAR(100) NOT NULL,
    district          VARCHAR(100) NOT NULL,
    county            VARCHAR(100) NOT NULL,
    region            VARCHAR(40)  NOT NULL,
    UNIQUE (postcode, town_city, district, county)
);

CREATE TABLE IF NOT EXISTS fact_sales (
    transaction_id    VARCHAR(36)  PRIMARY KEY,
    price             BIGINT       NOT NULL CHECK (price > 0),
    date_key          INTEGER      NOT NULL REFERENCES dim_date (date_key),
    property_key      BIGINT       NOT NULL REFERENCES dim_property (property_key),
    location_key      BIGINT       NOT NULL REFERENCES dim_location (location_key),
    ppd_category_type CHAR(1),
    record_status     CHAR(1)      NOT NULL,
    is_valid_postcode BOOLEAN      NOT NULL,
    is_low_price      BOOLEAN      NOT NULL,
    is_iqr_outlier    BOOLEAN      NOT NULL,
    is_outlier        BOOLEAN      NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_fact_sales_date_key     ON fact_sales (date_key);
CREATE INDEX IF NOT EXISTS ix_fact_sales_property_key ON fact_sales (property_key);
CREATE INDEX IF NOT EXISTS ix_fact_sales_location_key ON fact_sales (location_key);
CREATE INDEX IF NOT EXISTS ix_fact_sales_is_outlier   ON fact_sales (is_outlier);
CREATE INDEX IF NOT EXISTS ix_dim_location_region     ON dim_location (region);
CREATE INDEX IF NOT EXISTS ix_dim_location_district   ON dim_location (district);
CREATE INDEX IF NOT EXISTS ix_dim_date_year_month     ON dim_date (year_month);
