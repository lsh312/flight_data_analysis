from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Mapping

import polars as pl


MONEY_COLUMNS = ["price", "airport_tax", "local_tax", "total_amount"]
NUMERIC_COLUMNS = [
    "distance",
    "flight_minutes",
    "seats_business",
    "seats_premium",
    "seats_economy",
    "fuel_gallons_hour",
    "maintenance_takeoffs",
    "maintenance_flight_hours",
    "total_flight_distance",
]


def _existing(df: pl.DataFrame, columns: Iterable[str]) -> list[str]:
    return [column for column in columns if column in df.columns]


def _rename_existing(df: pl.DataFrame, mapping: Mapping[str, str]) -> pl.DataFrame:
    return df.rename({old: new for old, new in mapping.items() if old in df.columns})


def _clean_strings(df: pl.DataFrame) -> pl.DataFrame:
    expressions = []
    for column, dtype in df.schema.items():
        if dtype == pl.String:
            expressions.append(pl.col(column).str.strip_chars().alias(column))
    return df.with_columns(expressions) if expressions else df


def _cast_numbers(df: pl.DataFrame, columns: Iterable[str]) -> pl.DataFrame:
    expressions = [
        pl.col(column).cast(pl.Float64, strict=False).alias(column)
        for column in columns
        if column in df.columns
    ]
    return df.with_columns(expressions) if expressions else df


def _parse_temporal(df: pl.DataFrame, columns: Iterable[str]) -> pl.DataFrame:
    expressions = []
    for column in columns:
        if column not in df.columns:
            continue
        dtype = df.schema[column]
        dtype_name = str(dtype)
        if dtype == pl.String:
            expressions.append(
                pl.coalesce(
                    pl.col(column).str.strptime(
                        pl.Datetime, "%Y-%m-%d %H:%M:%S%.f", strict=False
                    ),
                    pl.col(column).str.strptime(
                        pl.Datetime, "%Y-%m-%d %H:%M:%S", strict=False
                    ),
                    pl.col(column).str.strptime(
                        pl.Datetime, "%Y-%m-%dT%H:%M:%S%.f", strict=False
                    ),
                    pl.col(column).str.strptime(
                        pl.Datetime, "%Y-%m-%dT%H:%M:%S", strict=False
                    ),
                    pl.col(column)
                    .str.strptime(pl.Date, "%Y-%m-%d", strict=False)
                    .cast(pl.Datetime),
                ).alias(column)
            )
        elif dtype == pl.Date:
            expressions.append(pl.col(column).cast(pl.Datetime).alias(column))
        elif "Datetime" in dtype_name:
            expressions.append(pl.col(column).alias(column))
    return df.with_columns(expressions) if expressions else df


def _safe_divide(numerator: pl.Expr, denominator: pl.Expr) -> pl.Expr:
    return pl.when(denominator.is_not_null() & (denominator != 0)).then(
        numerator / denominator
    ).otherwise(None)


def clean_table(df: pl.DataFrame) -> pl.DataFrame:
    df = _clean_strings(df)
    df = _cast_numbers(df, MONEY_COLUMNS + NUMERIC_COLUMNS)
    df = _parse_temporal(
        df,
        ["departure", "departure_date", "arrival", "birth_date", "build_date"],
    )
    return df


def _is_aggregated_tickets(tickets: pl.DataFrame) -> bool:
    return "tickets" in tickets.columns and "revenue" in tickets.columns


def _ticket_count_expr(tickets: pl.DataFrame) -> pl.Expr:
    if _is_aggregated_tickets(tickets):
        return pl.col("tickets").sum().alias("tickets")
    return pl.len().alias("tickets")


def _ticket_revenue_expr(tickets: pl.DataFrame) -> pl.Expr:
    if _is_aggregated_tickets(tickets):
        return pl.col("revenue").sum().alias("revenue")
    return pl.col("total_amount").sum().alias("revenue")


def _avg_ticket_value_expr(tickets: pl.DataFrame) -> pl.Expr:
    if _is_aggregated_tickets(tickets):
        return _safe_divide(pl.col("revenue").sum(), pl.col("tickets").sum()).alias(
            "avg_ticket_value"
        )
    return pl.col("total_amount").mean().alias("avg_ticket_value")


def _tax_amount_expr(tickets: pl.DataFrame) -> pl.Expr:
    if _is_aggregated_tickets(tickets):
        return pl.col("tax_amount").sum().alias("tax_amount")
    return pl.col("tax_amount").sum().alias("tax_amount")


def _avg_tax_share_expr(tickets: pl.DataFrame) -> pl.Expr:
    if _is_aggregated_tickets(tickets) and "tax_share_sum" in tickets.columns:
        return _safe_divide(pl.col("tax_share_sum").sum(), pl.col("tickets").sum()).alias(
            "avg_tax_share"
        )
    return pl.col("tax_share").mean().alias("avg_tax_share")


def build_route_dimension(routes: pl.DataFrame, airports: pl.DataFrame) -> pl.DataFrame:
    routes = clean_table(routes)
    airports = clean_table(airports)

    airport_columns = _existing(
        airports,
        [
            "iata_code",
            "airport",
            "city",
            "country",
            "continent",
            "timezone",
            "latitude",
            "longitude",
            "airport_tax",
        ],
    )
    airports = airports.select(airport_columns).unique(subset=["iata_code"])

    origin_airports = _rename_existing(
        airports,
        {
            "iata_code": "origin",
            "airport": "origin_airport",
            "city": "origin_city",
            "country": "origin_country",
            "continent": "origin_continent",
            "timezone": "origin_timezone",
            "latitude": "origin_latitude",
            "longitude": "origin_longitude",
            "airport_tax": "origin_airport_tax_ref",
        }
    )
    destination_airports = _rename_existing(
        airports,
        {
            "iata_code": "destination",
            "airport": "destination_airport",
            "city": "destination_city",
            "country": "destination_country",
            "continent": "destination_continent",
            "timezone": "destination_timezone",
            "latitude": "destination_latitude",
            "longitude": "destination_longitude",
            "airport_tax": "destination_airport_tax_ref",
        }
    )

    return (
        routes.lazy()
        .with_columns(
            pl.col("route_code").cast(pl.Utf8),
            pl.col("origin").cast(pl.Utf8),
            pl.col("destination").cast(pl.Utf8),
        )
        .join(origin_airports.lazy(), on="origin", how="left")
        .join(destination_airports.lazy(), on="destination", how="left")
        .with_columns(
            (
                pl.coalesce(pl.col("origin_city"), pl.col("origin"))
                + pl.lit(" -> ")
                + pl.coalesce(pl.col("destination_city"), pl.col("destination"))
            ).alias("route_label"),
            _safe_divide(pl.col("flight_minutes"), pl.lit(60)).alias("flight_hours"),
        )
        .collect()
    )


def build_tickets_enriched(
    tickets: pl.DataFrame,
    route_dim: pl.DataFrame,
    passengers: pl.DataFrame | None = None,
) -> pl.DataFrame:
    tickets = clean_table(tickets)
    if "total_amount" not in tickets.columns:
        tickets = tickets.with_columns(
            (
                pl.col("price").fill_null(0)
                + pl.col("airport_tax").fill_null(0)
                + pl.col("local_tax").fill_null(0)
            ).alias("total_amount")
        )

    base = (
        tickets.lazy()
        .with_columns(
            pl.col("route_code").cast(pl.Utf8),
            pl.col("ticket_id").cast(pl.Utf8),
            pl.col("passenger_id").cast(pl.Utf8),
            pl.col("flight_id").cast(pl.Utf8),
            pl.col("class")
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.to_uppercase()
            .replace_strict(
                {
                    "E": "ECONOMY",
                    "ECON": "ECONOMY",
                    "ECONOMY": "ECONOMY",
                    "P": "PREMIUM",
                    "PREMIUM": "PREMIUM",
                    "PREMIUM ECONOMY": "PREMIUM",
                    "B": "BUSINESS",
                    "BUS": "BUSINESS",
                    "BUSINESS": "BUSINESS",
                },
                default=pl.col("class").cast(pl.Utf8).str.to_uppercase(),
            )
            .alias("cabin_class"),
            (pl.col("airport_tax").fill_null(0) + pl.col("local_tax").fill_null(0)).alias(
                "tax_amount"
            ),
        )
        .with_columns(
            _safe_divide(pl.col("tax_amount"), pl.col("total_amount")).alias(
                "tax_share"
            ),
            pl.col("departure").alias("ticket_departure"),
            pl.col("departure").dt.date().alias("departure_date"),
            pl.col("departure").dt.strftime("%Y-%m").alias("departure_month"),
            pl.col("departure").dt.year().alias("departure_year"),
        )
        .join(route_dim.lazy(), on="route_code", how="left")
    )

    if passengers is not None and not passengers.is_empty():
        passenger_columns = _existing(
            passengers,
            ["id", "gender", "birth_date", "country", "vipcard"],
        )
        passenger_dim = (
            clean_table(passengers)
            .select(passenger_columns)
            .rename(
                {
                    "id": "passenger_id",
                    "gender": "passenger_gender",
                    "birth_date": "passenger_birth_date",
                    "country": "passenger_country",
                    "vipcard": "vip_card",
                }
            )
            .with_columns(pl.col("passenger_id").cast(pl.Utf8))
        )
        base = base.join(passenger_dim.lazy(), on="passenger_id", how="left")

    result = base.collect()

    if "passenger_birth_date" in result.columns:
        result = result.with_columns(
            (pl.col("departure_year") - pl.col("passenger_birth_date").dt.year()).alias(
                "passenger_age"
            )
        ).with_columns(
            pl.when(pl.col("passenger_age") < 25)
            .then(pl.lit("Under 25"))
            .when(pl.col("passenger_age") < 35)
            .then(pl.lit("25-34"))
            .when(pl.col("passenger_age") < 50)
            .then(pl.lit("35-49"))
            .when(pl.col("passenger_age") < 65)
            .then(pl.lit("50-64"))
            .when(pl.col("passenger_age").is_not_null())
            .then(pl.lit("65+"))
            .otherwise(pl.lit("Unknown"))
            .alias("age_band")
        )

    if "vip_card" in result.columns:
        result = result.with_columns(
            pl.when(
                pl.col("vip_card")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_uppercase()
                .is_in(["Y", "YES", "TRUE", "1", "VIP"])
            )
            .then(pl.lit("VIP"))
            .otherwise(pl.lit("Non-VIP"))
            .alias("vip_segment")
        )

    return result


def build_ticket_summary_enriched(
    ticket_summary: pl.DataFrame,
    route_dim: pl.DataFrame,
) -> pl.DataFrame:
    summary = clean_table(ticket_summary)
    return (
        summary.lazy()
        .with_columns(
            pl.col("route_code").cast(pl.Utf8),
            pl.col("departure_date").dt.date().alias("departure_date"),
            pl.col("departure_month").cast(pl.Utf8),
            pl.col("cabin_class").cast(pl.Utf8),
            pl.col("tickets").cast(pl.Float64, strict=False),
            pl.col("revenue").cast(pl.Float64, strict=False),
            pl.col("avg_ticket_value").cast(pl.Float64, strict=False),
            pl.col("tax_amount").cast(pl.Float64, strict=False),
            pl.col("tax_share_sum").cast(pl.Float64, strict=False),
            _safe_divide(pl.col("tax_share_sum"), pl.col("tickets")).alias("tax_share"),
        )
        .join(route_dim.lazy(), on="route_code", how="left")
        .collect()
    )


def build_flights_enriched(
    flights: pl.DataFrame,
    route_dim: pl.DataFrame,
    airplanes: pl.DataFrame,
    tickets_enriched: pl.DataFrame,
) -> pl.DataFrame:
    flights = clean_table(flights)
    airplanes = clean_table(airplanes)

    if {"tickets_sold", "ticket_revenue"}.issubset(tickets_enriched.columns):
        ticket_by_flight = tickets_enriched.select(
            pl.col("flight_id").cast(pl.Utf8),
            pl.col("tickets_sold").cast(pl.Float64, strict=False),
            pl.col("ticket_revenue").cast(pl.Float64, strict=False),
        )
    else:
        ticket_by_flight = (
            tickets_enriched.lazy()
            .group_by("flight_id")
            .agg(
                pl.len().alias("tickets_sold"),
                pl.col("total_amount").sum().alias("ticket_revenue"),
            )
            .collect()
        )

    airplane_dim = airplanes.rename({"aircraft_registration": "airplane"})
    if "build_date" in airplane_dim.columns:
        current_year = date.today().year
        airplane_dim = airplane_dim.with_columns(
            (pl.lit(current_year) - pl.col("build_date").dt.year()).alias(
                "aircraft_age_years"
            )
        )

    return (
        flights.lazy()
        .with_columns(
            pl.col("flight_id").cast(pl.Utf8),
            pl.col("route_code").cast(pl.Utf8),
            pl.col("airplane").cast(pl.Utf8),
            pl.col("departure").alias("flight_departure"),
            pl.col("arrival").alias("flight_arrival"),
        )
        .join(
            route_dim.lazy().select(
                _existing(
                    route_dim,
                    [
                        "route_code",
                        "origin",
                        "destination",
                        "route_label",
                        "distance",
                        "flight_minutes",
                        "flight_hours",
                        "origin_continent",
                        "destination_continent",
                    ],
                )
            ),
            on="route_code",
            how="left",
        )
        .join(airplane_dim.lazy(), on="airplane", how="left")
        .join(ticket_by_flight.lazy(), on="flight_id", how="left")
        .with_columns(
            (
                pl.col("seats_business").fill_null(0)
                + pl.col("seats_premium").fill_null(0)
                + pl.col("seats_economy").fill_null(0)
            ).alias("seat_capacity"),
            pl.col("tickets_sold").fill_null(0),
            pl.col("ticket_revenue").fill_null(0),
        )
        .with_columns(
            _safe_divide(pl.col("tickets_sold"), pl.col("seat_capacity")).alias(
                "estimated_load_factor"
            ),
            (pl.col("fuel_gallons_hour") * pl.col("flight_hours")).alias(
                "estimated_fuel_gallons"
            ),
        )
        .collect()
    )


def build_prepared_datasets(raw_tables: Mapping[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    route_dim = build_route_dimension(raw_tables["routes"], raw_tables["airports"])
    if "ticket_summary" in raw_tables:
        tickets_enriched = build_ticket_summary_enriched(
            raw_tables["ticket_summary"],
            route_dim,
        )
        flight_ticket_source = raw_tables["ticket_by_flight"]
    else:
        tickets_enriched = build_tickets_enriched(
            raw_tables["tickets"],
            route_dim,
            raw_tables.get("passengers"),
        )
        flight_ticket_source = tickets_enriched

    flights_enriched = build_flights_enriched(
        raw_tables["flights"],
        route_dim,
        raw_tables["airplanes"],
        flight_ticket_source,
    )

    return {
        "route_dimension": route_dim,
        "tickets_enriched": tickets_enriched,
        "flights_enriched": flights_enriched,
        "revenue_by_month": revenue_by_month(tickets_enriched),
        "revenue_by_route": revenue_by_route(tickets_enriched),
        "route_efficiency": route_efficiency(tickets_enriched),
        "fleet_utilization": fleet_utilization(flights_enriched),
        "passenger_segments": passenger_segments(tickets_enriched),
        "tax_by_route": tax_by_route(tickets_enriched),
    }


def load_prepared_data(data_dir: str | Path = "data") -> dict[str, pl.DataFrame]:
    data_path = Path(data_dir)
    required = ["tickets_enriched", "flights_enriched"]
    missing = [name for name in required if not (data_path / f"{name}.parquet").exists()]
    if missing:
        raise FileNotFoundError(
            "Missing prepared data files: "
            + ", ".join(f"{name}.parquet" for name in missing)
        )

    return {
        path.stem: pl.read_parquet(path)
        for path in sorted(data_path.glob("*.parquet"))
    }


def filter_tickets(
    tickets: pl.DataFrame,
    start_date: date | datetime | None = None,
    end_date: date | datetime | None = None,
    cabin_classes: list[str] | None = None,
    origin_continents: list[str] | None = None,
    destination_continents: list[str] | None = None,
    routes: list[str] | None = None,
    min_distance: float | None = None,
) -> pl.DataFrame:
    query = tickets.lazy()

    if start_date is not None:
        query = query.filter(pl.col("departure_date") >= start_date)
    if end_date is not None:
        query = query.filter(pl.col("departure_date") <= end_date)
    if cabin_classes:
        query = query.filter(pl.col("cabin_class").is_in(cabin_classes))
    if origin_continents:
        query = query.filter(pl.col("origin_continent").is_in(origin_continents))
    if destination_continents:
        query = query.filter(pl.col("destination_continent").is_in(destination_continents))
    if routes:
        query = query.filter(pl.col("route_code").is_in(routes))
    if min_distance is not None:
        query = query.filter(pl.col("distance").fill_null(0) >= min_distance)

    return query.collect()


def filter_flights(
    flights: pl.DataFrame,
    origin_continents: list[str] | None = None,
    destination_continents: list[str] | None = None,
    models: list[str] | None = None,
) -> pl.DataFrame:
    query = flights.lazy()
    if origin_continents:
        query = query.filter(pl.col("origin_continent").is_in(origin_continents))
    if destination_continents:
        query = query.filter(pl.col("destination_continent").is_in(destination_continents))
    if models and "model" in flights.columns:
        query = query.filter(pl.col("model").is_in(models))
    return query.collect()


def overview_metrics(tickets: pl.DataFrame, flights: pl.DataFrame | None = None) -> dict[str, float]:
    if _is_aggregated_tickets(tickets):
        ticket_metrics = tickets.select(
            pl.col("revenue").sum().alias("revenue"),
            pl.col("tickets").sum().alias("tickets"),
            _safe_divide(pl.col("revenue").sum(), pl.col("tickets").sum()).alias(
                "avg_ticket_value"
            ),
            pl.col("route_code").n_unique().alias("routes"),
            _safe_divide(pl.col("tax_share_sum").sum(), pl.col("tickets").sum()).alias(
                "avg_tax_share"
            ),
        ).row(0, named=True)
    else:
        ticket_metrics = tickets.select(
            pl.col("total_amount").sum().alias("revenue"),
            pl.len().alias("tickets"),
            pl.col("total_amount").mean().alias("avg_ticket_value"),
            pl.col("route_code").n_unique().alias("routes"),
            pl.col("tax_share").mean().alias("avg_tax_share"),
        ).row(0, named=True)

    metrics = {key: float(value or 0) for key, value in ticket_metrics.items()}
    if flights is not None and not flights.is_empty():
        flight_metrics = flights.select(
            pl.len().alias("scheduled_flights"),
            pl.col("airplane").n_unique().alias("aircraft"),
            pl.col("estimated_load_factor").mean().alias("avg_load_factor"),
        ).row(0, named=True)
        metrics.update({key: float(value or 0) for key, value in flight_metrics.items()})

    return metrics


def revenue_by_month(tickets: pl.DataFrame) -> pl.DataFrame:
    return (
        tickets.lazy()
        .group_by("departure_month", "cabin_class")
        .agg(
            _ticket_revenue_expr(tickets),
            _ticket_count_expr(tickets),
        )
        .sort(["departure_month", "cabin_class"])
        .collect()
    )


def cabin_mix(tickets: pl.DataFrame) -> pl.DataFrame:
    return (
        tickets.lazy()
        .group_by("cabin_class")
        .agg(
            _ticket_count_expr(tickets),
            _ticket_revenue_expr(tickets),
            _avg_ticket_value_expr(tickets),
        )
        .with_columns(
            _safe_divide(pl.col("revenue"), pl.col("revenue").sum()).alias(
                "revenue_share"
            )
        )
        .sort("revenue", descending=True)
        .collect()
    )


def revenue_by_route(tickets: pl.DataFrame, top_n: int | None = None) -> pl.DataFrame:
    result = (
        tickets.lazy()
        .group_by(
            [
                "route_code",
                "route_label",
                "origin",
                "destination",
                "origin_country",
                "destination_country",
                "origin_continent",
                "destination_continent",
            ]
        )
        .agg(
            _ticket_count_expr(tickets),
            _ticket_revenue_expr(tickets),
            _avg_ticket_value_expr(tickets),
            _tax_amount_expr(tickets),
        )
        .sort("revenue", descending=True)
        .collect()
    )
    return result.head(top_n) if top_n else result


def route_efficiency(tickets: pl.DataFrame, top_n: int | None = None) -> pl.DataFrame:
    result = (
        tickets.lazy()
        .group_by(
            [
                "route_code",
                "route_label",
                "origin",
                "destination",
                "distance",
                "flight_minutes",
                "origin_continent",
                "destination_continent",
            ]
        )
        .agg(
            _ticket_count_expr(tickets),
            _ticket_revenue_expr(tickets),
            _avg_ticket_value_expr(tickets),
        )
        .with_columns(
            _safe_divide(pl.col("revenue"), pl.col("distance")).alias(
                "revenue_per_distance"
            ),
            _safe_divide(pl.col("avg_ticket_value"), pl.col("distance")).alias(
                "avg_ticket_value_per_distance"
            ),
            _safe_divide(pl.col("avg_ticket_value"), pl.col("flight_minutes")).alias(
                "avg_ticket_value_per_minute"
            ),
        )
        .sort("revenue_per_distance", descending=True, nulls_last=True)
        .collect()
    )
    return result.head(top_n) if top_n else result


def fleet_utilization(flights: pl.DataFrame, top_n: int | None = None) -> pl.DataFrame:
    grouping = ["airplane"]
    if "model" in flights.columns:
        grouping.append("model")

    aggregations = [
        pl.len().alias("scheduled_flights"),
        pl.col("distance").sum().alias("assigned_distance"),
        pl.col("ticket_revenue").sum().alias("ticket_revenue"),
        pl.col("tickets_sold").sum().alias("tickets_sold"),
        pl.col("seat_capacity").max().alias("seat_capacity"),
        pl.col("estimated_load_factor").mean().alias("avg_load_factor"),
        pl.col("estimated_fuel_gallons").sum().alias("estimated_fuel_gallons"),
    ]

    for optional_column in [
        "aircraft_age_years",
        "maintenance_takeoffs",
        "maintenance_flight_hours",
        "total_flight_distance",
    ]:
        if optional_column in flights.columns:
            aggregations.append(pl.col(optional_column).max().alias(optional_column))

    result = (
        flights.lazy()
        .group_by(grouping)
        .agg(aggregations)
        .sort("scheduled_flights", descending=True)
        .collect()
    )
    return result.head(top_n) if top_n else result


def fleet_by_model(flights: pl.DataFrame) -> pl.DataFrame:
    if "model" not in flights.columns:
        return pl.DataFrame()

    return (
        flights.lazy()
        .group_by("model")
        .agg(
            pl.col("airplane").n_unique().alias("aircraft"),
            pl.len().alias("scheduled_flights"),
            pl.col("seat_capacity").mean().alias("avg_seat_capacity"),
            pl.col("estimated_load_factor").mean().alias("avg_load_factor"),
            pl.col("estimated_fuel_gallons").sum().alias("estimated_fuel_gallons"),
        )
        .sort("scheduled_flights", descending=True)
        .collect()
    )


def passenger_segments(tickets: pl.DataFrame) -> pl.DataFrame:
    grouping = []
    for column in ["passenger_country", "vip_segment", "age_band", "cabin_class"]:
        if column in tickets.columns:
            grouping.append(column)

    if not grouping:
        return pl.DataFrame()

    return (
        tickets.lazy()
        .group_by(grouping)
        .agg(
            _ticket_count_expr(tickets),
            _ticket_revenue_expr(tickets),
            _avg_ticket_value_expr(tickets),
        )
        .sort("revenue", descending=True)
        .collect()
    )


def tax_by_route(tickets: pl.DataFrame, top_n: int | None = None) -> pl.DataFrame:
    result = (
        tickets.lazy()
        .group_by(["route_code", "route_label", "origin", "destination"])
        .agg(
            _ticket_count_expr(tickets),
            _ticket_revenue_expr(tickets),
            _tax_amount_expr(tickets),
            _avg_tax_share_expr(tickets),
        )
        .sort("avg_tax_share", descending=True, nulls_last=True)
        .collect()
    )
    return result.head(top_n) if top_n else result


def write_prepared_datasets(
    datasets: Mapping[str, pl.DataFrame],
    data_dir: str | Path = "data",
) -> None:
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    for name, df in datasets.items():
        df.write_parquet(
            data_path / f"{name}.parquet",
            compression="zstd",
            statistics=True,
        )


def summarize_key_findings(tickets: pl.DataFrame, flights: pl.DataFrame) -> list[str]:
    findings: list[str] = []

    route_summary = revenue_by_route(tickets, top_n=1)
    if not route_summary.is_empty():
        row = route_summary.row(0, named=True)
        findings.append(
            f"Top revenue route is {row['route_label']} ({row['route_code']}) "
            f"with {row['tickets']:,.0f} tickets and {row['revenue']:,.0f} total revenue."
        )

    cabin_summary = cabin_mix(tickets)
    if not cabin_summary.is_empty():
        row = cabin_summary.row(0, named=True)
        findings.append(
            f"{row['cabin_class']} is the largest cabin by revenue, contributing "
            f"{row['revenue_share']:.1%} of filtered ticket revenue."
        )

    efficiency_summary = route_efficiency(tickets, top_n=1)
    if not efficiency_summary.is_empty():
        row = efficiency_summary.row(0, named=True)
        findings.append(
            f"Highest yield route by revenue per distance is {row['route_label']} "
            f"at {row['revenue_per_distance']:,.2f} revenue units per distance unit."
        )

    fleet_summary = fleet_utilization(flights, top_n=1)
    if not fleet_summary.is_empty():
        row = fleet_summary.row(0, named=True)
        label = row["airplane"]
        if "model" in row and row["model"]:
            label = f"{label} ({row['model']})"
        findings.append(
            f"Most scheduled aircraft is {label} with "
            f"{row['scheduled_flights']:,.0f} assigned flights."
        )

    tax_summary = tax_by_route(tickets, top_n=1)
    if not tax_summary.is_empty():
        row = tax_summary.row(0, named=True)
        findings.append(
            f"Highest average tax share appears on {row['route_label']}, "
            f"where taxes average {row['avg_tax_share']:.1%} of ticket value."
        )

    return findings
