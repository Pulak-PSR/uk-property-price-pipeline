# Data Quality Report

Generated: 2026-10-14 05:50

## Row counts

| Metric | Rows | % of input |
|---|---:|---:|
| Rows in | 2,767,042 | 100% |
| Rows out | 2,767,042 | 100.000% |
| Dropped: missing transaction id, price or date | 0 | 0.000% |
| Dropped: non-positive price | 0 | 0.000% |
| Dropped: record_status = D (deleted) | 0 | 0.000% |
| Duplicates removed (same transaction_id) | 0 | 0.000% |
| Change records (C) applied | 0 | 0.000% |

## Validity and outliers (flagged, not removed)

| Metric | Rows |
|---|---:|
| Invalid / missing postcodes | 7,428 |
| Price below minimum threshold | 8,872 |
| Log-price IQR outliers | 17,609 |
| Total outlier-flagged rows | 17,609 |

Log-price IQR fence: £13,675 to £5,594,203.

## Null counts per column

| Column | Before cleaning | After cleaning |
|---|---:|---:|
| transaction_id | 0 | 0 |
| price | 0 | 0 |
| date_of_transfer | 0 | 0 |
| postcode | 7,426 | 7,426 |
| property_type | 0 | 0 |
| old_new | 0 | 0 |
| duration | 0 | 0 |
| paon | 0 | 0 |
| saon | 2,408,353 | 2,408,353 |
| street | 45,378 | 45,378 |
| locality | 1,713,523 | 1,713,523 |
| town_city | 0 | 0 |
| district | 0 | 0 |
| county | 0 | 0 |
| ppd_category_type | 0 | 0 |
| record_status | 0 | 0 |

Empty strings count as null. Optional address fields such as `saon` and `locality` are legitimately empty for many properties. Missing town, district and county are filled with `UNKNOWN` after cleaning.

## Price summary (cleaned data)

- Date range: 2023-01-01 to 2025-12-31
- Mean: £398,989, median: £280,000
- Min: £1, max: £793,020,000
