# Power BI setup guide

You build the `.pbix` yourself. This guide gets the data in, the model right and the measures added. The page layouts are in `dashboard_spec.md`.

`.pbix` files are git-ignored. Do not commit them with data inside.

## 1. Prerequisites

- Power BI Desktop (Windows).
- The pipeline has run and loaded PostgreSQL: `python -m uk_property_pipeline.run_pipeline`.
- PostgreSQL is reachable (Docker: `docker compose up -d`, then host `localhost`, port `5432`).
- The Npgsql provider is needed by the PostgreSQL connector. If Power BI asks for it, install Npgsql from its GitHub releases (choose the GAC installation option).

## 2. Connect to PostgreSQL

1. Home > Get data > PostgreSQL database.
2. Server: `localhost:5432`. Database: `ukproperty` (the `POSTGRES_DB` value in your `.env`).
3. Data Connectivity mode: **Import** (about 3 million fact rows fit comfortably).
4. Enter the database user and password from your `.env` when prompted.
5. In the Navigator tick these:
   - Tables: `fact_sales`, `dim_date`, `dim_property`, `dim_location`
   - Views: `vw_monthly_avg_price_by_region`, `vw_price_by_property_type`, `vw_new_build_vs_existing`, `vw_top_20_districts_by_growth`, `vw_region_summary`
6. Click **Transform data** first and check the points below, then Close & Apply.

### Power Query checks

- `fact_sales[price]`: Whole number.
- `dim_date[date]`: Date.
- `fact_sales[date_key]`, `property_key`, `location_key` and the matching keys in the dimensions: Whole number. The keys are 52-bit hashes, which Power BI holds exactly.
- Remove columns you will not use (for example `ppd_category_type`) to keep the model small.

## 3. Relationships

Model view: make sure these exist (Power BI usually detects them; fix any that are wrong).

| From (many) | To (one) | Cardinality | Filter direction |
|---|---|---|---|
| `fact_sales[date_key]` | `dim_date[date_key]` | Many to one | Single |
| `fact_sales[property_key]` | `dim_property[property_key]` | Many to one | Single |
| `fact_sales[location_key]` | `dim_location[location_key]` | Many to one | Single |

The five `vw_*` tables are standalone. Do not relate them to the star schema. They are pre-aggregated, handy for simple visuals and for checking your DAX against SQL.

## 4. Date table

1. Select `dim_date` > Table tools > **Mark as date table** > choose `date`.
2. Sort `month_name` by `month` (Column tools > Sort by column).
3. Hide `date_key` and the three key columns on `fact_sales` from report view.

## 5. Add the measures

Follow `dax_measures.md`. Put them in a `_Measures` table. Set formats:

| Measure | Format |
|---|---|
| Average Price, Median Price | Currency, GBP, 0 decimals |
| Sales Volume | Whole number, thousands separator |
| YoY % | Percentage, 1 decimal |

## 6. Apply the theme

View > Themes > Browse for themes > pick `powerbi/theme.json`.

## 7. Build the pages

Follow `dashboard_spec.md` (3 pages, shared slicers for year, region and property type). Sync the slicers across pages (View > Sync slicers).

## 8. Save screenshots for the README

Take a screenshot of each page into `powerbi/screenshots/` using these names so the README links work:

- `01_overview.png`
- `02_regional.png`
- `03_property_types.png`

## Other databases

- **SQL Server**: use the SQL Server connector and set `DATABASE_URL` to an `mssql+pyodbc://` string. The views use `= FALSE`, which SQL Server does not accept; change them to `= 0` first.
- **SQLite**: no native Power BI connector. Use the SQLite ODBC driver or export the tables to CSV.

## Troubleshooting

- **Key columns look wrong or blank**: check they are Whole number, not Decimal.
- **Slow refresh**: remove unused columns from the model.
- **Numbers differ from SQL**: confirm your visuals use the measures (which exclude outliers) and not a raw sum of price.
