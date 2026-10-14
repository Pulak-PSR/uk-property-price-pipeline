# Dashboard specification

Canvas: 16:9 (1280 x 720). Theme: `theme.json`. Font: Segoe UI. Light grey page background, visuals on white cards with a thin border.

## Slicers (synced across all pages)

Place them in a top strip on each page (height about 56 px).

| Slicer | Field | Style |
|---|---|---|
| Year | `dim_date[year]` | Tile / button, multi-select |
| Region | `dim_location[region]` | Dropdown, multi-select, search on |
| Property type | `dim_property[property_type]` | Tile / button, multi-select |

Add a "Reset" bookmark button on the right of the strip.

## Page 1: Overview

Purpose: how big is the market and where are prices heading.

| Visual | Fields | Notes |
|---|---|---|
| KPI card: Average Price | `[Average Price]` | Subtitle: `[Average Price YoY %]` |
| KPI card: Median Price | `[Median Price]` | |
| KPI card: Sales Volume | `[Sales Volume]` | Subtitle: `[Sales Volume YoY %]` |
| KPI card: Total Sales Value | `[Total Sales Value]` | Display unit: billions |
| Line chart (wide) | X: `dim_date[year_month]`; Y: `[Average Price]`, `[Average Price 3M Moving Avg]` | Moving average as a dashed line |
| Column chart | X: `dim_date[year_month]`; Y: `[Sales Volume]` | Aligned under the line chart to show seasonality |
| Text box | `[Latest Sale Date]` | Footer: "Source: HM Land Registry Price Paid Data, OGL v3.0" |

Layout: four KPI cards across the top (below the slicers), the line chart under them taking about two thirds of the width, volume columns beneath it.

## Page 2: Regional

Purpose: compare regions geographically and in detail.

| Visual | Fields | Notes |
|---|---|---|
| Filled map (or Shape map) | Location: `dim_location[region]`; Colour saturation: `[Average Price]` | Bing may not recognise region names such as "East of England". If it does not, use a bar chart sorted by price instead |
| Table | `dim_location[region]`, `[Average Price]`, `[Median Price]`, `[Sales Volume]`, `[Average Price YoY %]`, `[Region Price Rank]` | Data bars on Average Price; conditional icons on YoY % |
| Bar chart | Y: `vw_top_20_districts_by_growth[district]`; X: `yoy_growth_pct` | Standalone view, ranked, already filtered to districts with 100+ sales in both years |
| Line chart | X: `dim_date[year_month]`; Y: `[Average Price]`; Legend: `dim_location[region]` | Responds to the region slicer |

Cross-filtering: clicking a region on the map filters the table and the line chart.

## Page 3: Property type and new build

Purpose: what kind of home sells, and how new builds compare.

| Visual | Fields | Notes |
|---|---|---|
| Clustered column | X: `dim_property[property_type]`; Y: `[Average Price]`; Legend: `dim_date[year]` | |
| Donut | Legend: `dim_property[property_type]`; Values: `[Sales Volume]` | Show percentage labels |
| Line chart | X: `dim_date[year_month]`; Y: `[Average Price]`; Legend: `dim_property[build_status]` | New Build vs Existing (filter out Unknown) |
| Matrix | Rows: `dim_property[property_type]`; Columns: `dim_property[tenure]`; Values: `[Average Price]` | Freehold vs leasehold. Heatmap conditional formatting |
| KPI card | `[New Build Premium %]` | Measure below |

```dax
New Build Premium % =
VAR NewBuild = CALCULATE ( [Average Price], dim_property[build_status] = "New Build" )
VAR Existing = CALCULATE ( [Average Price], dim_property[build_status] = "Existing" )
RETURN DIVIDE ( NewBuild - Existing, Existing )
```

## Design rules

- One accent colour (dark blue) for emphasis; orange only for the moving average or a highlight.
- Titles say what the visual shows, with the unit in the subtitle.
- Hide visual headers; keep tooltips on.
- Sort bars descending; label units once, not on every axis tick.
- Check the report at 100% zoom and in the mobile layout view.

## Accessibility

- Add alt text to each visual (Format > General > Alt text).
- Do not rely on colour alone: data bars and icons accompany colour scales.
