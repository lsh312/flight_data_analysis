# Take-Home Analytics Test: Airline Operations Dashboard

## Context

You have been shortlisted for a junior data analyst / analytics engineer role at a regional airline group. The hiring team wants to evaluate how you approach a realistic business analytics problem: connecting to an operational database, preparing analytical datasets, and building a dashboard that communicates useful insights.

Your task is to build an interactive dashboard using **Python**, **Polars**, and **Streamlit**. The source data is stored in a DB2 database containing airline operations, route, fleet, passenger, and ticketing data.

This is an open-ended take-home test. You are expected to make reasonable analytical choices, document assumptions, and explain the business value of your dashboard.

---

## Database Access

Use the following DB2 database connection details.

```text
Host:      52.211.123.34
Port:      25010
Database:  ATTPLANE
Driver:    IBM DB2
```

Each group should connect with its assigned user:

```text
Username:  attgrp1, attgrp2, ..., attgrp8
Password:  bigdata
```

Example SQLAlchemy connection URL:

```python
db2+ibm_db://attgrp1:bigdata@52.211.123.34:25010/ATTPLANE
```

Use your assigned schema when querying tables. For example, group 1 should read from:

```sql
ATTGRP1.FLIGHTS
ATTGRP1.TICKETS
ATTGRP1.ROUTES
```

Group 2 should use `ATTGRP2`, and so on.

---

## Available Data

The database contains one schema per group. The core tables are:

| Table | Business Meaning | Example Columns |
|---|---|---|
| `AIRPLANES` | Fleet inventory and aircraft operational characteristics | `AIRCRAFT_REGISTRATION`, `MODEL`, `SEATS_BUSINESS`, `SEATS_PREMIUM`, `SEATS_ECONOMY`, `BUILD_DATE`, `FUEL_GALLONS_HOUR`, `MAINTENANCE_FLIGHT_HOURS`, `TOTAL_FLIGHT_DISTANCE` |
| `AIRPORTS` | Airport reference data and geographic/tax information | `IATA_CODE`, `AIRPORT`, `CITY`, `COUNTRY`, `CONTINENT`, `TIMEZONE`, `LATITUDE`, `LONGITUDE`, `AIRPORT_TAX` |
| `FLIGHTS` | Scheduled flight legs and ticket prices by cabin | `FLIGHT_ID`, `FLIGHT_LEG`, `FREQUENCY`, `ROUTE_CODE`, `DEPARTURE`, `ARRIVAL`, `AIRPLANE`, `PRICE_ECONOMY`, `PRICE_PREMIUM`, `PRICE_BUSINESS` |
| `PASSENGERS` | Passenger master data | `ID`, `FIRSTNME`, `LASTNAME`, `GENDER`, `BIRTH_DATE`, `COUNTRY`, `VIPCARD` |
| `ROUTES` | Route network and flight duration/distance | `ROUTE_CODE`, `ORIGIN`, `DESTINATION`, `PARENT_ROUTE`, `LEG_NUMBER`, `DISTANCE`, `FLIGHT_MINUTES` |
| `TICKETS` | Ticket sales and realized revenue | `TICKET_ID`, `PASSENGER_ID`, `FLIGHT_ID`, `ROUTE_CODE`, `DEPARTURE`, `CLASS`, `SEAT`, `PRICE`, `AIRPORT_TAX`, `LOCAL_TAX`, `TOTAL_AMOUNT` |

Some schemas may also expose staff or crew tables. You may use them if available, but they are not required.

---

## Required Technical Stack

Your solution must use:

- **Polars** for data loading, cleaning, joining, feature engineering, and analytics.
- **Streamlit** for the dashboard interface.
- **Plotly**, Altair, or Streamlit native charts for visualizations.
- SQLAlchemy + DB2 driver, or another reliable Python DB2 connection method, for database access.

You may use Pandas only for comparison or for compatibility with a library that strictly requires it. The analytical transformations must be implemented in Polars.

---

## Assignment

Build a Streamlit dashboard that helps airline management understand the business and operational performance of the airline network.

Your dashboard should answer at least **three** business questions using the database tables. It should include interactive filters and clear visualizations.

Minimum requirements:

- Connect to the DB2 database and read the relevant tables.
- Use Polars to clean and prepare the data.
- Join at least two tables.
- Create at least three analytical outputs.
- Include at least two interactive dashboard filters.
- Include at least three charts or visual summaries.
- Include a short written explanation of the insights and assumptions.

Recommended project structure:

```text
group_<N>_plane_dashboard/
├── app.py
├── analysis.py
├── db.py
├── data/
│   └── prepared_*.parquet
├── requirements.txt
└── README.md
```

You may either query the database directly from Streamlit or prepare Parquet files first. For performance, the recommended workflow is:

1. Connect to DB2 in a notebook or script.
2. Read and prepare the required datasets with Polars.
3. Save cleaned or aggregated datasets as Parquet.
4. Build the Streamlit app using the Parquet outputs.

---

## Business Dashboard Examples

The examples below are realistic given the available tables. You do not need to implement all of them. Choose a coherent dashboard concept and go deep enough to produce useful insights.

### Example 1: Revenue Performance Dashboard

Business question:

> Which routes, cabins, and departure periods generate the most revenue?

Relevant tables:

- `TICKETS`
- `ROUTES`
- `AIRPORTS`
- optionally `FLIGHTS`

Possible metrics:

- Total revenue: `sum(TOTAL_AMOUNT)`
- Ticket volume: `count(TICKET_ID)`
- Average ticket value: `mean(TOTAL_AMOUNT)`
- Revenue by cabin class: `CLASS`
- Revenue by route: `ROUTE_CODE`, `ORIGIN`, `DESTINATION`
- Monthly or weekly revenue trend using `DEPARTURE`

Possible filters:

- Cabin class
- Origin airport
- Destination airport
- Date range
- Continent or country

Possible charts:

- Bar chart: top 10 routes by total revenue
- Line chart: revenue over time
- Stacked bar chart: revenue by cabin class
- Map: revenue by origin or destination airport

Business interpretation examples:

- Identify routes that generate high revenue but low passenger volume, suggesting premium pricing.
- Compare economy, premium, and business cabin contribution.
- Detect seasonal demand patterns by departure month.

---

### Example 2: Network and Route Efficiency Dashboard

Business question:

> Which routes are most important to the network, and how efficient are they in terms of distance, duration, and commercial performance?

Relevant tables:

- `ROUTES`
- `FLIGHTS`
- `TICKETS`
- `AIRPORTS`

Possible metrics:

- Number of scheduled flights per route
- Number of tickets sold per route
- Average flight duration: `FLIGHT_MINUTES`
- Route distance: `DISTANCE`
- Revenue per kilometer or mile: `sum(TOTAL_AMOUNT) / DISTANCE`
- Average fare per flight minute: `mean(TOTAL_AMOUNT) / FLIGHT_MINUTES`

Possible filters:

- Origin continent
- Destination continent
- Minimum route distance
- Route code
- Flight frequency

Possible charts:

- Scatter plot: route distance vs. average ticket value
- Bar chart: routes with highest revenue per distance
- Heatmap-style table: origin city to destination city performance
- Map: route network using airport latitude and longitude

Business interpretation examples:

- Identify short routes with strong revenue yield.
- Identify long routes with low average fare or weak demand.
- Recommend routes for pricing review or capacity adjustment.

---

### Example 3: Fleet Utilization and Capacity Dashboard

Business question:

> How is the aircraft fleet being used, and where might there be capacity or maintenance risks?

Relevant tables:

- `AIRPLANES`
- `FLIGHTS`
- `ROUTES`
- optionally `TICKETS`

Possible metrics:

- Flights per aircraft: `count(FLIGHT_ID)` grouped by `AIRPLANE`
- Assigned route distance per aircraft
- Aircraft seat capacity: `SEATS_BUSINESS + SEATS_PREMIUM + SEATS_ECONOMY`
- Fuel consumption estimate: `FUEL_GALLONS_HOUR * flight hours`
- Maintenance indicators: `MAINTENANCE_TAKEOFFS`, `MAINTENANCE_FLIGHT_HOURS`
- Aircraft age using `BUILD_DATE`

Possible filters:

- Aircraft model
- Aircraft registration
- Capacity range
- Build year
- Maintenance flight-hour threshold

Possible charts:

- Bar chart: flights or total scheduled distance by aircraft
- Scatter plot: aircraft age vs. maintenance flight hours
- Table: aircraft with high takeoffs or high maintenance hours
- Histogram: seat capacity distribution by aircraft model

Business interpretation examples:

- Find aircraft that are heavily used relative to the rest of the fleet.
- Compare fuel consumption by model.
- Highlight aircraft that may need operational review due to high takeoffs or flight hours.

---

### Example 4: Passenger and Customer Segmentation Dashboard

Business question:

> What passenger segments are most valuable, and how do they differ by geography or cabin class?

Relevant tables:

- `PASSENGERS`
- `TICKETS`
- `ROUTES`
- `AIRPORTS`

Possible metrics:

- Revenue by passenger country
- Ticket count per passenger
- Average spend per passenger
- VIP vs. non-VIP revenue contribution using `VIPCARD`
- Cabin class preference by passenger segment
- Passenger age bands using `BIRTH_DATE`

Possible filters:

- Passenger country
- VIP status
- Cabin class
- Age band
- Route or continent

Possible charts:

- Bar chart: top passenger countries by revenue
- Donut or bar chart: VIP vs. non-VIP revenue
- Box plot: ticket value distribution by cabin class
- Table: highest-value passenger segments

Business interpretation examples:

- Identify countries or customer segments that drive premium revenue.
- Compare VIP and non-VIP buying behavior.
- Detect whether certain markets over-index in business or premium cabin purchases.

Privacy note:

Do not display personally identifiable passenger details such as email, phone, passport, or full name in the dashboard unless there is a clear analytical reason. Prefer aggregated views.

---

### Example 5: Airport and Tax Impact Dashboard

Business question:

> How do airport taxes and geography affect ticket prices and route economics?

Relevant tables:

- `AIRPORTS`
- `ROUTES`
- `TICKETS`
- optionally `FLIGHTS`

Possible metrics:

- Average airport tax by airport, country, or continent
- Average ticket tax: `AIRPORT_TAX + LOCAL_TAX`
- Tax as percentage of total ticket amount
- Revenue by origin or destination airport
- Ticket volume by airport

Possible filters:

- Continent
- Country
- Origin airport
- Destination airport
- Tax percentage range

Possible charts:

- Map: airport tax by geography
- Bar chart: airports with highest average taxes
- Scatter plot: tax percentage vs. total ticket amount
- Table: routes with highest tax burden

Business interpretation examples:

- Identify airports where tax burden may affect customer price sensitivity.
- Compare high-tax routes with ticket volume and revenue.
- Recommend routes where fare strategy should consider local tax effects.

---

## Expected Analytics Quality

Your Polars code should be readable, efficient, and reproducible.

Strong submissions will:

- Use explicit column selection rather than loading unnecessary data.
- Normalize DB2 column names into Python-friendly names.
- Use Polars expressions instead of row-by-row Python loops.
- Use `.lazy()` for larger transformation pipelines where appropriate.
- Sort grouped results before displaying top-N outputs.
- Handle nulls intentionally.
- Use clear function names for reusable transformations.
- Save prepared datasets to Parquet if the dashboard becomes slow.

Example Polars pattern:

```python
revenue_by_route = (
    tickets
    .lazy()
    .join(routes.lazy(), on="route_code", how="left")
    .group_by("route_code", "origin", "destination")
    .agg(
        pl.len().alias("tickets"),
        pl.col("total_amount").sum().alias("revenue"),
        pl.col("total_amount").mean().alias("avg_ticket_value"),
    )
    .sort("revenue", descending=True)
    .collect()
)
```

---

## Dashboard Requirements

Your Streamlit dashboard should be usable by a business stakeholder.

It should include:

- A clear title and short description.
- Sidebar filters.
- At least three visual sections.
- Key metrics at the top, such as total revenue, ticket count, average ticket value, number of routes, or number of aircraft.
- Clear chart titles and axis labels.
- A data preview or downloadable summary table.
- A short explanation of the main findings.

Avoid:

- Showing raw database dumps as the main dashboard.
- Charts without business interpretation.
- Hardcoding only one route, one class, or one date unless clearly justified.
- Using personally identifiable passenger information unnecessarily.

---

## Deliverables

Submit a single ZIP file named:

```text
group_<N>_plane_dashboard.zip
```

The ZIP should contain:

```text
group_<N>_plane_dashboard/
├── app.py
├── analysis.py or notebook.ipynb
├── db.py or connection instructions
├── requirements.txt
├── README.md
└── data/                         # optional prepared Parquet files
```

Your `README.md` must include:

- Project title.
- Group members.
- Which database schema you used.
- How to install dependencies.
- How to run the dashboard.
- Which business questions your dashboard answers.
- Three to five key findings.
- Any known limitations or assumptions.

---

## Evaluation Criteria

| Area | Weight | What We Look For |
|---|---:|---|
| Database access and reproducibility | 15% | Clear connection process, schema selection, reproducible setup |
| Polars usage | 25% | Clean joins, aggregations, expressions, lazy pipelines where useful |
| Business insight | 25% | Meaningful questions, relevant metrics, useful interpretation |
| Dashboard usability | 20% | Clear layout, filters, readable charts, stakeholder-friendly design |
| Code quality | 10% | Organized files, reusable functions, clear naming, no unnecessary complexity |
| Communication | 5% | Concise README, assumptions, limitations, presentation clarity |

---

## Presentation

Each group will give a short live demo.

Suggested structure:

1. One minute: business problem and dashboard audience.
2. Two minutes: data sources and preparation.
3. Five minutes: dashboard walkthrough and key insights.
4. Two minutes: limitations and recommended next steps.

Be prepared to answer:

- Why did you choose these metrics?
- Which tables did you join and why?
- What assumptions did you make?
- What would you improve with more time?
- How would this dashboard help a business stakeholder make a decision?

---

## Practical Tips

- Start by listing available tables and inspecting schemas.
- Read small samples before loading full tables.
- Build and test analytics in a notebook before moving logic into Streamlit.
- Cache data loads in Streamlit with `@st.cache_data`.
- Prefer Parquet files for prepared datasets.
- Keep passenger-level data aggregated unless individual records are required.
- Make sure every chart answers a business question.

