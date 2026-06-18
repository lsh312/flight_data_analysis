from __future__ import annotations

from datetime import date
from pathlib import Path

import plotly.express as px
import polars as pl
import streamlit as st

from analysis import (
    cabin_mix,
    filter_flights,
    filter_tickets,
    fleet_by_model,
    fleet_utilization,
    load_prepared_data,
    overview_metrics,
    passenger_segments,
    revenue_by_month,
    revenue_by_route,
    route_efficiency,
    summarize_key_findings,
    tax_by_route,
)


DATA_DIR = Path(__file__).parent / "data"


st.set_page_config(
    page_title="Airline Operations Dashboard",
    layout="wide",
)


@st.cache_data(show_spinner=False)
def load_data() -> dict[str, pl.DataFrame]:
    return load_prepared_data(DATA_DIR)


def to_pandas(df: pl.DataFrame):
    return df.to_pandas()


def format_money(value: float) -> str:
    return f"{value:,.0f}"


def format_number(value: float) -> str:
    return f"{value:,.0f}"


def format_percent(value: float) -> str:
    return f"{value:.1%}"


def option_list(df: pl.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return []
    return (
        df.select(pl.col(column).drop_nulls().unique().sort())
        .to_series()
        .cast(pl.Utf8)
        .to_list()
    )


def empty_state() -> None:
    st.title("Airline Operations Dashboard")
    st.error("Prepared Parquet files are missing.")
    st.code(
        "python -m venv .venv\n"
        "source .venv/bin/activate\n"
        "python -m pip install -r requirements.txt\n"
        "cp .env.example .env\n"
        "python prepare_data.py\n"
        "streamlit run app.py",
        language="bash",
    )
    st.stop()


try:
    data = load_data()
except FileNotFoundError:
    empty_state()

tickets = data["tickets_enriched"]
flights = data["flights_enriched"]

st.title("Airline Operations Dashboard")
st.caption("Revenue, network efficiency, and fleet utilization for the ATTPLANE airline database.")

date_bounds = tickets.select(
    pl.col("departure_date").min().alias("min_date"),
    pl.col("departure_date").max().alias("max_date"),
).row(0, named=True)
min_date: date = date_bounds["min_date"]
max_date: date = date_bounds["max_date"]

with st.sidebar:
    st.header("Filters")
    selected_range = st.date_input(
        "Departure date",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
    else:
        start_date, end_date = min_date, max_date

    cabin_options = option_list(tickets, "cabin_class")
    selected_cabins = st.multiselect(
        "Cabin class",
        cabin_options,
        default=cabin_options,
    )

    origin_continents = option_list(tickets, "origin_continent")
    selected_origin_continents = st.multiselect(
        "Origin continent",
        origin_continents,
        default=origin_continents,
    )

    destination_continents = option_list(tickets, "destination_continent")
    selected_destination_continents = st.multiselect(
        "Destination continent",
        destination_continents,
        default=destination_continents,
    )

    route_options = option_list(tickets, "route_code")
    selected_routes = st.multiselect("Route code", route_options)

    max_distance = float(tickets.select(pl.col("distance").max()).item() or 0)
    min_distance = st.slider(
        "Minimum route distance",
        min_value=0,
        max_value=int(max_distance),
        value=0,
        step=max(1, int(max_distance / 100)) if max_distance else 1,
    )

    model_options = option_list(flights, "model")
    selected_models = st.multiselect(
        "Aircraft model",
        model_options,
        default=model_options,
    )

filtered_tickets = filter_tickets(
    tickets,
    start_date=start_date,
    end_date=end_date,
    cabin_classes=selected_cabins,
    origin_continents=selected_origin_continents,
    destination_continents=selected_destination_continents,
    routes=selected_routes,
    min_distance=float(min_distance),
)
filtered_flights = filter_flights(
    flights,
    origin_continents=selected_origin_continents,
    destination_continents=selected_destination_continents,
    models=selected_models,
)

if filtered_tickets.is_empty():
    st.warning("No tickets match the selected filters.")
    st.stop()

metrics = overview_metrics(filtered_tickets, filtered_flights)

kpi_1, kpi_2, kpi_3, kpi_4, kpi_5 = st.columns(5)
kpi_1.metric("Total revenue", format_money(metrics["revenue"]))
kpi_2.metric("Tickets sold", format_number(metrics["tickets"]))
kpi_3.metric("Avg ticket value", format_money(metrics["avg_ticket_value"]))
kpi_4.metric("Routes", format_number(metrics["routes"]))
kpi_5.metric("Avg tax share", format_percent(metrics["avg_tax_share"]))

for finding in summarize_key_findings(filtered_tickets, filtered_flights):
    st.info(finding)

revenue_tab, network_tab, fleet_tab, segment_tab, data_tab = st.tabs(
    ["Revenue", "Network efficiency", "Fleet", "Segments and taxes", "Data"]
)

with revenue_tab:
    left, right = st.columns([1.15, 0.85])

    monthly = revenue_by_month(filtered_tickets)
    with left:
        fig = px.line(
            to_pandas(monthly),
            x="departure_month",
            y="revenue",
            color="cabin_class",
            markers=True,
            title="Revenue trend by cabin",
            labels={
                "departure_month": "Departure month",
                "revenue": "Revenue",
                "cabin_class": "Cabin",
            },
        )
        st.plotly_chart(fig, use_container_width=True)

    cabin = cabin_mix(filtered_tickets)
    with right:
        fig = px.bar(
            to_pandas(cabin),
            x="cabin_class",
            y="revenue",
            color="cabin_class",
            title="Revenue mix by cabin",
            labels={
                "cabin_class": "Cabin",
                "revenue": "Revenue",
                "tickets": "Tickets",
            },
            hover_data=["tickets", "avg_ticket_value", "revenue_share"],
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    top_routes = revenue_by_route(filtered_tickets, top_n=12)
    fig = px.bar(
        to_pandas(top_routes.sort("revenue")),
        x="revenue",
        y="route_label",
        orientation="h",
        title="Top routes by revenue",
        labels={"route_label": "Route", "revenue": "Revenue"},
        hover_data=["tickets", "avg_ticket_value", "origin_continent", "destination_continent"],
    )
    st.plotly_chart(fig, use_container_width=True)

with network_tab:
    efficiency = route_efficiency(filtered_tickets)
    scatter_source = efficiency.filter(
        pl.col("distance").is_not_null()
        & pl.col("avg_ticket_value").is_not_null()
        & pl.col("revenue_per_distance").is_not_null()
    )
    fig = px.scatter(
        to_pandas(scatter_source),
        x="distance",
        y="avg_ticket_value",
        size="revenue",
        color="revenue_per_distance",
        hover_name="route_label",
        title="Route distance vs. average ticket value",
        labels={
            "distance": "Distance",
            "avg_ticket_value": "Average ticket value",
            "revenue_per_distance": "Revenue per distance",
            "revenue": "Revenue",
        },
    )
    st.plotly_chart(fig, use_container_width=True)

    top_yield = efficiency.head(15)
    fig = px.bar(
        to_pandas(top_yield.sort("revenue_per_distance")),
        x="revenue_per_distance",
        y="route_label",
        orientation="h",
        title="Highest revenue per distance",
        labels={"route_label": "Route", "revenue_per_distance": "Revenue per distance"},
        hover_data=["tickets", "revenue", "avg_ticket_value"],
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        to_pandas(
            efficiency.select(
                [
                    "route_code",
                    "route_label",
                    "tickets",
                    "revenue",
                    "avg_ticket_value",
                    "distance",
                    "flight_minutes",
                    "revenue_per_distance",
                    "avg_ticket_value_per_minute",
                ]
            ).head(50)
        ),
        use_container_width=True,
        hide_index=True,
    )

with fleet_tab:
    filtered_fleet = fleet_utilization(filtered_flights)
    if filtered_fleet.is_empty():
        st.warning("No flights match the selected aircraft filters.")
    else:
        top_aircraft = filtered_fleet.head(15)
        fig = px.bar(
            to_pandas(top_aircraft.sort("scheduled_flights")),
            x="scheduled_flights",
            y="airplane",
            color="model" if "model" in top_aircraft.columns else None,
            orientation="h",
            title="Aircraft by scheduled flights",
            labels={"scheduled_flights": "Scheduled flights", "airplane": "Aircraft"},
            hover_data=[
                column
                for column in [
                    "tickets_sold",
                    "ticket_revenue",
                    "seat_capacity",
                    "avg_load_factor",
                    "assigned_distance",
                ]
                if column in top_aircraft.columns
            ],
        )
        st.plotly_chart(fig, use_container_width=True)

        model_summary = fleet_by_model(filtered_flights)
        if not model_summary.is_empty():
            fig = px.scatter(
                to_pandas(model_summary),
                x="avg_seat_capacity",
                y="avg_load_factor",
                size="scheduled_flights",
                color="model",
                title="Aircraft model capacity and estimated load factor",
                labels={
                    "avg_seat_capacity": "Average seat capacity",
                    "avg_load_factor": "Estimated load factor",
                    "scheduled_flights": "Scheduled flights",
                },
            )
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            to_pandas(filtered_fleet.head(50)),
            use_container_width=True,
            hide_index=True,
        )

with segment_tab:
    left, right = st.columns(2)
    segment_summary = passenger_segments(filtered_tickets)
    if not segment_summary.is_empty():
        segment_columns = [
            column for column in ["vip_segment", "age_band", "cabin_class"] if column in segment_summary.columns
        ]
        display_summary = (
            segment_summary.lazy()
            .group_by(segment_columns)
            .agg(
                pl.col("tickets").sum().alias("tickets"),
                pl.col("revenue").sum().alias("revenue"),
                pl.col("avg_ticket_value").mean().alias("avg_ticket_value"),
            )
            .sort("revenue", descending=True)
            .collect()
        )
        with left:
            fig = px.bar(
                to_pandas(display_summary.head(20)),
                x=segment_columns[0],
                y="revenue",
                color=segment_columns[-1],
                title="Passenger segment revenue",
                labels={"revenue": "Revenue"},
                hover_data=["tickets", "avg_ticket_value"],
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        with left:
            st.warning("Passenger segment fields are unavailable in this schema.")

    taxes = tax_by_route(filtered_tickets, top_n=15)
    with right:
        fig = px.bar(
            to_pandas(taxes.sort("avg_tax_share")),
            x="avg_tax_share",
            y="route_label",
            orientation="h",
            title="Routes with highest average tax share",
            labels={"avg_tax_share": "Average tax share", "route_label": "Route"},
            hover_data=["tickets", "revenue", "tax_amount"],
        )
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        to_pandas(tax_by_route(filtered_tickets).head(50)),
        use_container_width=True,
        hide_index=True,
    )

with data_tab:
    route_summary = revenue_by_route(filtered_tickets)
    st.download_button(
        "Download route summary CSV",
        data=route_summary.write_csv(),
        file_name="route_summary.csv",
        mime="text/csv",
    )
    st.dataframe(to_pandas(route_summary.head(100)), use_container_width=True, hide_index=True)
