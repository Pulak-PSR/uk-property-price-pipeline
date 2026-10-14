# DAX measures

Create these in a dedicated `_Measures` table (Home > Enter data, create an empty table, then add the measures).
Table and column names assume the model described in `README_powerbi.md`: `fact_sales`, `dim_date`, `dim_property`, `dim_location`.

All price measures exclude outlier-flagged sales. The flag is a column on `fact_sales`, so the filter sits inside each measure and users can still see the raw rows if they want.

## Base measures

```dax
Sales Volume =
CALCULATE ( COUNTROWS ( fact_sales ), fact_sales[is_outlier] = FALSE () )
```

```dax
Average Price =
CALCULATE ( AVERAGE ( fact_sales[price] ), fact_sales[is_outlier] = FALSE () )
```

```dax
Median Price =
CALCULATE ( MEDIAN ( fact_sales[price] ), fact_sales[is_outlier] = FALSE () )
```

```dax
Total Sales Value =
CALCULATE ( SUM ( fact_sales[price] ), fact_sales[is_outlier] = FALSE () )
```

```dax
Outliers Flagged =
CALCULATE ( COUNTROWS ( fact_sales ), fact_sales[is_outlier] = TRUE () )
```

## Time intelligence

`dim_date` must be marked as a date table (Table tools > Mark as date table > `date`).

```dax
Avg Price Prior Year =
CALCULATE ( [Average Price], SAMEPERIODLASTYEAR ( dim_date[date] ) )
```

```dax
Average Price YoY % =
VAR Current = [Average Price]
VAR Prior = [Avg Price Prior Year]
RETURN
    IF ( NOT ISBLANK ( Prior ) && Prior <> 0, DIVIDE ( Current - Prior, Prior ) )
```

Format as percentage with one decimal.

```dax
Sales Volume YoY % =
VAR Prior =
    CALCULATE ( [Sales Volume], SAMEPERIODLASTYEAR ( dim_date[date] ) )
RETURN
    IF ( NOT ISBLANK ( Prior ), DIVIDE ( [Sales Volume] - Prior, Prior ) )
```

## 3-month moving average

Use with `dim_date[year_month]` or `dim_date[date]` on the axis. This version averages the last three months of the average price.

```dax
Average Price 3M Moving Avg =
VAR LastDate = MAX ( dim_date[date] )
VAR Window =
    DATESINPERIOD ( dim_date[date], EOMONTH ( LastDate, 0 ), -3, MONTH )
RETURN
    CALCULATE ( [Average Price], Window )
```

Note: this is a rolling 3-month average of all sales in the window (volume weighted). If you prefer the mean of three monthly averages, use:

```dax
Average Price 3M Avg of Months =
AVERAGEX (
    DATESINPERIOD ( dim_date[date], EOMONTH ( MAX ( dim_date[date] ), 0 ), -3, MONTH ),
    CALCULATE ( [Average Price] )
)
```

## Ranking

```dax
Region Price Rank =
RANKX (
    ALL ( dim_location[region] ),
    [Average Price],
    ,
    DESC,
    DENSE
)
```

Use it in the regional table next to `Average Price`. Because `ALL ( dim_location[region] )` ignores the region filter, the rank stays correct when a row is shown in a table.

```dax
District Price Rank in Region =
RANKX (
    ALLSELECTED ( dim_location[district] ),
    [Average Price],
    ,
    DESC,
    DENSE
)
```

## Helper measures for titles and tooltips

```dax
Selected Region Label =
IF (
    HASONEVALUE ( dim_location[region] ),
    VALUES ( dim_location[region] ),
    "All regions"
)
```

`dim_date` covers whole calendar years, so `MAX ( dim_date[date] )` would be 31 December of the last year. Use the date of the latest actual sale instead:

```dax
Latest Sale Date =
CALCULATE ( MAX ( dim_date[date] ), CROSSFILTER ( fact_sales[date_key], dim_date[date_key], BOTH ) )
```
