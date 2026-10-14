# Data Quality Report

Generated: 2026-10-14 05:41

**Note: generated from a SAMPLE run, not the full dataset.**

## Row counts

| Metric | Rows | % of input |
|---|---:|---:|
| Rows in | 50,000 | 100% |
| Rows out | 50,000 | 100.000% |
| Dropped: missing transaction id, price or date | 0 | 0.000% |
| Dropped: non-positive price | 0 | 0.000% |
| Dropped: record_status = D (deleted) | 0 | 0.000% |
| Duplicates removed (same transaction_id) | 0 | 0.000% |
| Change records (C) applied | 0 | 0.000% |

## Validity and outliers (flagged, not removed)

| Metric | Rows |
|---|---:|
| Invalid / missing postcodes | 125 |
| Price below minimum threshold | 132 |
| Log-price IQR outliers | 285 |
| Total outlier-flagged rows | 285 |

Log-price IQR fence: £15,545 to £5,186,448.

## Null counts per column

| Column | Before cleaning | After cleaning |
|---|---:|---:|
| transaction_id | 0 | 0 |
| price | 0 | 0 |
| date_of_transfer | 0 | 0 |
| postcode | 125 | 125 |
| property_type | 0 | 0 |
| old_new | 0 | 0 |
| duration | 0 | 0 |
| paon | 0 | 0 |
| saon | 44,017 | 44,017 |
| street | 828 | 828 |
| locality | 30,875 | 30,875 |
| town_city | 0 | 0 |
| district | 0 | 0 |
| county | 0 | 0 |
| ppd_category_type | 0 | 0 |
| record_status | 0 | 0 |

Empty strings count as null. Optional address fields such as `saon` and `locality` are legitimately empty for many properties. Missing town, district and county are filled with `UNKNOWN` after cleaning.

## Price summary (cleaned data)

- Date range: 2025-01-01 to 2025-12-31
- Mean: £401,898, median: £285,500
- Min: £100, max: £793,020,000
