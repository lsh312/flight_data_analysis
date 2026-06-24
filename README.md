# Airline Operations Dashboard

Streamlit dashboard for the ATTPLANE DB2 airline database. The project uses DB2 for source data, Polars for cleaning and analytics, Parquet for reusable prepared data, and Plotly/Streamlit for the dashboard.

## Group Details

- Group: 7
- Database schema: `ATTGRP7`
- Group members: Jan Wejchert, Lea Sarouphim Hochar, Sacha Huberty, Romain Gelin

## Business Questions

1. Which routes, cabins, and departure periods generate the most revenue?
2. Which routes are strongest or weakest in commercial efficiency, using revenue per distance and ticket value per minute?
3. How is the fleet being used, and which aircraft show high scheduled use, fuel exposure, or maintenance indicators?
4. Which passenger segments and tax-heavy routes deserve management attention?

## Project Structure

```text
group_7_plane_dashboard/
├── app.py                  # Streamlit dashboard
├── analysis.py             # Polars cleaning, joins, metrics, and aggregations
├── db.py                   # DB2 connection and safe table reads
├── prepare_data.py         # One-command DB2 to Parquet preparation
├── data/                   # Prepared Parquet files after running prepare_data.py
├── tests/                  # Small Polars logic tests with synthetic data
├── requirements.txt
├── TEAM_HANDOFF.md
└── presentation_outline.md
```

## Setup

Recommended Python version: 3.10 to 3.12 for DB2 extraction. Python 3.13 can run the dashboard code, but the IBM DB2 driver may fail on macOS depending on the installed C++ runtime.

```bash
cd "group_7_plane_dashboard"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```
'''Powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python.exe -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
'''

The default `.env.example` is already set for group 7 and available in the repository.

## Prepare Data

```bash
python prepare_data.py
```
'''powershell
python prepare_data.py
'''

This reads the required DB2 tables, normalizes DB2 column names, joins routes/airports/flights/airplanes, and writes prepared Parquet files into `data/`. Because the tickets table is very large, the default preparation does not download every ticket row. It asks DB2 to build monthly ticket summaries by route and cabin first, then saves the smaller analytical datasets as Parquet.

The extraction prints table-by-table and batch-by-batch progress. For very large summary results, tune the fetch size with:

```powershell
python prepare_data.py --batch-size 200000
```

Larger batches can be faster but use more memory. Use a smaller value if the machine starts swapping or feels slow.

To force the original row-level extraction, use:

```powershell
python prepare_data.py --raw-tickets
```

If the command fails with an `ibm_db` import error on macOS, run the project from the course-provided notebook environment or a Python 3.10-3.12 environment where this succeeds:

```bash
python -c "import ibm_db"
```
'''powershell
python -c "import ibm_db"
'''

Generated outputs include:

- `fleet_utilization.parquet`
- `flights_enriched.parquet`
- `generated_findings.md`
- `passenger_segments.parquet`
- `revenue_by_month.parquet`
- `revenue_by_route.parquet`
- `route_dimension.parquet`
- `route_efficiency.parquet`
- `tax_by_route.parquet`
- `tickets_enriched.parquet`

## Run Dashboard

```bash
streamlit run app.py
```
'''powershell
streamlit run app.py
'''

The dashboard uses the prepared Parquet files, so it does not reconnect to DB2 on every filter change.

## Key Findings

- Top revenue route is Naples → Las Vegas (R573) with 610,931 tickets and 1,033,938,168 total revenue.
- ECONOMY is the largest cabin by revenue, contributing 77.0% of filtered ticket revenue.
- Highest yield route by revenue per distance is London → Manchester at 172,419.30 revenue units per distance unit.
- Most scheduled aircraft is IE19325 (BOMBARDIER CRJ-900) with 23,448 assigned flights.
- Highest average tax share appears on London → Manchester, where taxes average 42.8% of ticket value.

## Assumptions and Limitations

- `TOTAL_AMOUNT` is treated as realized ticket revenue.
- `AIRPORT_TAX + LOCAL_TAX` is treated as the ticket tax burden.
- Load factor is estimated from tickets sold divided by aircraft seat capacity. It is a proxy because no no-show or seat inventory table is provided.
- Fuel consumption is estimated from aircraft fuel gallons per hour multiplied by route flight hours.
- Passenger analysis is aggregated and excludes personally identifiable details.
- The dashboard uses prepared Parquet files for performance and reproducibility.

## Tests

```bash
python -m unittest discover -s tests
```
'''powershell
python -m unittest discover -s tests
'''

The tests validate the main Polars joins and aggregations with a small synthetic dataset.
