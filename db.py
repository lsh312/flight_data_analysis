from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from urllib.parse import quote_plus

import polars as pl
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


PROJECT_TABLES: dict[str, list[str]] = {
    "TICKETS": [
        "TICKET_ID",
        "PASSENGER_ID",
        "FLIGHT_ID",
        "ROUTE_CODE",
        "DEPARTURE",
        "CLASS",
        "PRICE",
        "AIRPORT_TAX",
        "LOCAL_TAX",
        "TOTAL_AMOUNT",
    ],
    "ROUTES": [
        "ROUTE_CODE",
        "ORIGIN",
        "DESTINATION",
        "PARENT_ROUTE",
        "LEG_NUMBER",
        "DISTANCE",
        "FLIGHT_MINUTES",
    ],
    "AIRPORTS": [
        "IATA_CODE",
        "AIRPORT",
        "CITY",
        "COUNTRY",
        "CONTINENT",
        "TIMEZONE",
        "LATITUDE",
        "LONGITUDE",
        "AIRPORT_TAX",
    ],
    "FLIGHTS": [
        "FLIGHT_ID",
        "FLIGHT_LEG",
        "FREQUENCY",
        "ROUTE_CODE",
        "DEPARTURE",
        "ARRIVAL",
        "AIRPLANE",
        "PRICE_ECONOMY",
        "PRICE_PREMIUM",
        "PRICE_BUSINESS",
    ],
    "AIRPLANES": [
        "AIRCRAFT_REGISTRATION",
        "MODEL",
        "SEATS_BUSINESS",
        "SEATS_PREMIUM",
        "SEATS_ECONOMY",
        "BUILD_DATE",
        "FUEL_GALLONS_HOUR",
        "MAINTENANCE_TAKEOFFS",
        "MAINTENANCE_FLIGHT_HOURS",
        "TOTAL_FLIGHT_DISTANCE",
    ],
    "PASSENGERS": [
        "ID",
        "GENDER",
        "BIRTH_DATE",
        "COUNTRY",
        "VIPCARD",
    ],
}

SUMMARY_DIMENSION_TABLES: dict[str, list[str]] = {
    table: columns
    for table, columns in PROJECT_TABLES.items()
    if table not in {"TICKETS", "PASSENGERS"}
}


_IDENTIFIER_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    database: str
    username: str
    password: str
    schema: str

    @classmethod
    def from_env(cls) -> "DbConfig":
        load_dotenv()

        username = os.getenv("DB_USERNAME", "attgrp7")
        schema = os.getenv("DB_SCHEMA", username).upper().strip()

        return cls(
            host=os.getenv("DB_HOST", "52.211.123.34"),
            port=int(os.getenv("DB_PORT", "25010")),
            database=os.getenv("DB_NAME", "ATTPLANE"),
            username=username,
            password=os.getenv("DB_PASSWORD", "bigdata"),
            schema=schema,
        )

    @property
    def safe_summary(self) -> dict[str, str | int]:
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "username": self.username,
            "schema": self.schema,
            "password": "***",
        }


def validate_identifier(value: str) -> str:
    cleaned = value.upper().strip()
    if not _IDENTIFIER_RE.match(cleaned):
        raise ValueError(f"Unsafe DB2 identifier: {value!r}")
    return cleaned


def make_engine(config: DbConfig | None = None) -> Engine:
    config = config or DbConfig.from_env()
    username = quote_plus(config.username)
    password = quote_plus(config.password)
    url = (
        f"db2+ibm_db://{username}:{password}"
        f"@{config.host}:{config.port}/{config.database}"
    )
    return create_engine(url, pool_pre_ping=True)


def snake_case(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def normalize_column_names(df: pl.DataFrame) -> pl.DataFrame:
    return df.rename({column: snake_case(column) for column in df.columns})


def test_connection(engine: Engine) -> bool:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT 1 AS ok FROM SYSIBM.SYSDUMMY1")).fetchone()
    return row is not None and row[0] == 1


def list_tables(engine: Engine, schema: str) -> list[str]:
    schema = validate_identifier(schema)
    query = text(
        """
        SELECT TABNAME
        FROM SYSCAT.TABLES
        WHERE TABSCHEMA = :schema
          AND TYPE = 'T'
        ORDER BY TABNAME
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(query, {"schema": schema}).fetchall()
    return [str(row[0]).strip() for row in rows]


def list_columns(engine: Engine, schema: str, table: str) -> list[str]:
    schema = validate_identifier(schema)
    table = validate_identifier(table)
    query = text(
        """
        SELECT COLNAME
        FROM SYSCAT.COLUMNS
        WHERE TABSCHEMA = :schema
          AND TABNAME = :table
        ORDER BY COLNO
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(query, {"schema": schema, "table": table}).fetchall()
    return [str(row[0]).strip() for row in rows]


def estimate_table_rows(engine: Engine, schema: str, table: str) -> int | None:
    schema = validate_identifier(schema)
    table = validate_identifier(table)
    query = text(
        """
        SELECT CARD
        FROM SYSCAT.TABLES
        WHERE TABSCHEMA = :schema
          AND TABNAME = :table
          AND TYPE = 'T'
        """
    )
    with engine.connect() as conn:
        row = conn.execute(query, {"schema": schema, "table": table}).fetchone()
    if row is None or row[0] is None or int(row[0]) < 0:
        return None
    return int(row[0])


def _format_rows(value: int | None) -> str:
    return "unknown rows" if value is None else f"about {value:,} rows"


def read_table(
    engine: Engine,
    schema: str,
    table: str,
    columns: list[str] | None = None,
    batch_size: int = 100_000,
    progress: Callable[[str], None] | None = None,
) -> pl.DataFrame:
    schema = validate_identifier(schema)
    table = validate_identifier(table)
    progress = progress or (lambda message: None)

    started_at = perf_counter()
    progress(f"{table}: checking available columns...")
    available_columns = set(list_columns(engine, schema, table))

    if columns is None:
        selected_columns = sorted(available_columns)
    else:
        selected_columns = [
            validate_identifier(column)
            for column in columns
            if validate_identifier(column) in available_columns
        ]

    if not selected_columns:
        raise ValueError(f"No requested columns found in {schema}.{table}")

    estimated_rows = estimate_table_rows(engine, schema, table)
    progress(
        f"{table}: reading {len(selected_columns)} columns, {_format_rows(estimated_rows)} "
        f"(batch size {batch_size:,})..."
    )

    select_clause = ", ".join(f'"{column}"' for column in selected_columns)
    query = f'SELECT {select_clause} FROM "{schema}"."{table}"'

    with engine.connect() as conn:
        if batch_size > 0:
            batches = pl.read_database(
                query=query,
                connection=conn,
                iter_batches=True,
                batch_size=batch_size,
            )
            frames: list[pl.DataFrame] = []
            rows_read = 0
            for batch_number, batch in enumerate(batches, start=1):
                frames.append(batch)
                rows_read += batch.height
                progress(
                    f"{table}: batch {batch_number:,} loaded "
                    f"({rows_read:,} rows so far)..."
                )
            df = pl.concat(frames, how="vertical") if frames else pl.DataFrame()
        else:
            df = pl.read_database(query=query, connection=conn)

    elapsed = perf_counter() - started_at
    progress(f"{table}: finished {df.height:,} rows in {elapsed:,.1f}s.")
    return normalize_column_names(df)


def read_query(
    engine: Engine,
    query: str,
    label: str,
    batch_size: int = 100_000,
    progress: Callable[[str], None] | None = None,
) -> pl.DataFrame:
    progress = progress or (lambda message: None)
    started_at = perf_counter()
    progress(f"{label}: running query (batch size {batch_size:,})...")

    with engine.connect() as conn:
        if batch_size > 0:
            batches = pl.read_database(
                query=query,
                connection=conn,
                iter_batches=True,
                batch_size=batch_size,
            )
            frames: list[pl.DataFrame] = []
            rows_read = 0
            for batch_number, batch in enumerate(batches, start=1):
                frames.append(batch)
                rows_read += batch.height
                progress(
                    f"{label}: batch {batch_number:,} loaded "
                    f"({rows_read:,} rows so far)..."
                )
            df = pl.concat(frames, how="vertical") if frames else pl.DataFrame()
        else:
            df = pl.read_database(query=query, connection=conn)

    elapsed = perf_counter() - started_at
    progress(f"{label}: finished {df.height:,} rows in {elapsed:,.1f}s.")
    return normalize_column_names(df)


def ticket_summary_query(schema: str) -> str:
    schema = validate_identifier(schema)
    return f"""
        SELECT
            t."ROUTE_CODE",
            MIN(DATE(t."DEPARTURE")) AS "DEPARTURE_DATE",
            VARCHAR_FORMAT(t."DEPARTURE", 'YYYY-MM') AS "DEPARTURE_MONTH",
            CASE
                WHEN UPPER(TRIM(t."CLASS")) IN ('E', 'ECON', 'ECONOMY') THEN 'ECONOMY'
                WHEN UPPER(TRIM(t."CLASS")) IN ('P', 'PREMIUM', 'PREMIUM ECONOMY') THEN 'PREMIUM'
                WHEN UPPER(TRIM(t."CLASS")) IN ('B', 'BUS', 'BUSINESS') THEN 'BUSINESS'
                ELSE UPPER(TRIM(t."CLASS"))
            END AS "CABIN_CLASS",
            COUNT(*) AS "TICKETS",
            SUM(t."TOTAL_AMOUNT") AS "REVENUE",
            AVG(t."TOTAL_AMOUNT") AS "AVG_TICKET_VALUE",
            SUM(COALESCE(t."AIRPORT_TAX", 0) + COALESCE(t."LOCAL_TAX", 0)) AS "TAX_AMOUNT",
            SUM(
                CASE
                    WHEN t."TOTAL_AMOUNT" IS NOT NULL AND t."TOTAL_AMOUNT" <> 0
                    THEN (COALESCE(t."AIRPORT_TAX", 0) + COALESCE(t."LOCAL_TAX", 0)) / t."TOTAL_AMOUNT"
                    ELSE NULL
                END
            ) AS "TAX_SHARE_SUM"
        FROM "{schema}"."TICKETS" t
        GROUP BY
            t."ROUTE_CODE",
            VARCHAR_FORMAT(t."DEPARTURE", 'YYYY-MM'),
            CASE
                WHEN UPPER(TRIM(t."CLASS")) IN ('E', 'ECON', 'ECONOMY') THEN 'ECONOMY'
                WHEN UPPER(TRIM(t."CLASS")) IN ('P', 'PREMIUM', 'PREMIUM ECONOMY') THEN 'PREMIUM'
                WHEN UPPER(TRIM(t."CLASS")) IN ('B', 'BUS', 'BUSINESS') THEN 'BUSINESS'
                ELSE UPPER(TRIM(t."CLASS"))
            END
    """


def ticket_by_flight_query(schema: str) -> str:
    schema = validate_identifier(schema)
    return f"""
        SELECT
            "FLIGHT_ID",
            COUNT(*) AS "TICKETS_SOLD",
            SUM("TOTAL_AMOUNT") AS "TICKET_REVENUE"
        FROM "{schema}"."TICKETS"
        GROUP BY "FLIGHT_ID"
    """


def read_project_summary_tables(
    engine: Engine,
    schema: str,
    batch_size: int = 100_000,
    progress: Callable[[str], None] | None = None,
) -> dict[str, pl.DataFrame]:
    progress = progress or (lambda message: None)
    tables = read_project_tables(
        engine,
        schema,
        table_columns=SUMMARY_DIMENSION_TABLES,
        batch_size=batch_size,
        progress=progress,
    )
    tables["ticket_summary"] = read_query(
        engine,
        ticket_summary_query(schema),
        "TICKET_SUMMARY",
        batch_size=batch_size,
        progress=progress,
    )
    tables["ticket_by_flight"] = read_query(
        engine,
        ticket_by_flight_query(schema),
        "TICKET_BY_FLIGHT",
        batch_size=batch_size,
        progress=progress,
    )
    return tables


def read_project_tables(
    engine: Engine,
    schema: str,
    table_columns: dict[str, list[str]] | None = None,
    batch_size: int = 100_000,
    progress: Callable[[str], None] | None = None,
) -> dict[str, pl.DataFrame]:
    table_columns = table_columns or PROJECT_TABLES
    progress = progress or (lambda message: None)

    progress(f"{schema}: listing available tables...")
    available_tables = set(list_tables(engine, schema))
    missing = sorted(set(table_columns) - available_tables)
    if missing:
        raise RuntimeError(
            f"Missing required tables in {schema}: {', '.join(missing)}"
        )

    tables: dict[str, pl.DataFrame] = {}
    total_tables = len(table_columns)
    for index, (table, columns) in enumerate(table_columns.items(), start=1):
        progress(f"[{index}/{total_tables}] Starting {schema}.{table}")
        tables[table.lower()] = read_table(
            engine,
            schema,
            table,
            columns,
            batch_size=batch_size,
            progress=progress,
        )
    return tables
