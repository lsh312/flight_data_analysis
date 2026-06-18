import unittest

import polars as pl

from analysis import (
    build_ticket_summary_enriched,
    build_flights_enriched,
    build_route_dimension,
    build_tickets_enriched,
    cabin_mix,
    fleet_utilization,
    revenue_by_route,
    route_efficiency,
)


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.routes = pl.DataFrame(
            {
                "route_code": ["R1", "R2"],
                "origin": ["MAD", "BCN"],
                "destination": ["LHR", "MAD"],
                "distance": [1250.0, 500.0],
                "flight_minutes": [150.0, 70.0],
            }
        )
        self.airports = pl.DataFrame(
            {
                "iata_code": ["MAD", "BCN", "LHR"],
                "airport": ["Adolfo Suarez Madrid-Barajas", "Barcelona El Prat", "Heathrow"],
                "city": ["Madrid", "Barcelona", "London"],
                "country": ["Spain", "Spain", "United Kingdom"],
                "continent": ["Europe", "Europe", "Europe"],
                "latitude": [40.5, 41.3, 51.5],
                "longitude": [-3.6, 2.1, -0.4],
                "airport_tax": [10.0, 9.0, 12.0],
            }
        )
        self.tickets = pl.DataFrame(
            {
                "ticket_id": ["T1", "T2", "T3"],
                "passenger_id": ["P1", "P2", "P3"],
                "flight_id": ["F1", "F1", "F2"],
                "route_code": ["R1", "R1", "R2"],
                "departure": ["2026-01-01 10:00:00", "2026-01-01 10:00:00", "2026-01-02 09:00:00"],
                "class": ["Economy", "Business", "Economy"],
                "price": [100.0, 300.0, 80.0],
                "airport_tax": [10.0, 10.0, 9.0],
                "local_tax": [5.0, 5.0, 4.0],
                "total_amount": [115.0, 315.0, 93.0],
            }
        )
        self.airplanes = pl.DataFrame(
            {
                "aircraft_registration": ["A1", "A2"],
                "model": ["A320", "E190"],
                "seats_business": [12.0, 8.0],
                "seats_premium": [24.0, 12.0],
                "seats_economy": [120.0, 80.0],
                "build_date": ["2020-01-01", "2019-01-01"],
                "fuel_gallons_hour": [750.0, 520.0],
                "maintenance_flight_hours": [1000.0, 700.0],
            }
        )
        self.flights = pl.DataFrame(
            {
                "flight_id": ["F1", "F2"],
                "route_code": ["R1", "R2"],
                "departure": ["2026-01-01 10:00:00", "2026-01-02 09:00:00"],
                "arrival": ["2026-01-01 12:30:00", "2026-01-02 10:10:00"],
                "airplane": ["A1", "A2"],
            }
        )

    def test_revenue_and_efficiency_outputs(self):
        route_dim = build_route_dimension(self.routes, self.airports)
        tickets = build_tickets_enriched(self.tickets, route_dim)

        revenue = revenue_by_route(tickets)
        self.assertEqual(revenue.sort("revenue", descending=True)["route_code"][0], "R1")

        cabin = cabin_mix(tickets)
        self.assertIn("BUSINESS", cabin["cabin_class"].to_list())

        efficiency = route_efficiency(tickets)
        self.assertIn("revenue_per_distance", efficiency.columns)

    def test_fleet_utilization_output(self):
        route_dim = build_route_dimension(self.routes, self.airports)
        tickets = build_tickets_enriched(self.tickets, route_dim)
        flights = build_flights_enriched(self.flights, route_dim, self.airplanes, tickets)
        fleet = fleet_utilization(flights)

        self.assertEqual(fleet["scheduled_flights"].sum(), 2)
        self.assertIn("avg_load_factor", fleet.columns)

    def test_aggregated_ticket_summary_outputs(self):
        route_dim = build_route_dimension(self.routes, self.airports)
        ticket_summary = pl.DataFrame(
            {
                "route_code": ["R1", "R1", "R2"],
                "departure_date": ["2026-01-01", "2026-01-01", "2026-01-02"],
                "departure_month": ["2026-01", "2026-01", "2026-01"],
                "cabin_class": ["ECONOMY", "BUSINESS", "ECONOMY"],
                "passenger_country": ["Spain", "Spain", "France"],
                "vip_segment": ["Non-VIP", "VIP", "Non-VIP"],
                "age_band": ["25-34", "35-49", "25-34"],
                "tickets": [10.0, 2.0, 5.0],
                "revenue": [1000.0, 800.0, 300.0],
                "avg_ticket_value": [100.0, 400.0, 60.0],
                "tax_amount": [150.0, 80.0, 45.0],
                "tax_share_sum": [1.5, 0.2, 0.75],
            }
        )
        tickets = build_ticket_summary_enriched(ticket_summary, route_dim)

        revenue = revenue_by_route(tickets)
        r1 = revenue.filter(pl.col("route_code") == "R1").row(0, named=True)
        self.assertEqual(r1["tickets"], 12.0)
        self.assertEqual(r1["revenue"], 1800.0)
        self.assertEqual(r1["avg_ticket_value"], 150.0)

        cabin = cabin_mix(tickets)
        economy = cabin.filter(pl.col("cabin_class") == "ECONOMY").row(0, named=True)
        self.assertEqual(economy["tickets"], 15.0)
        self.assertEqual(economy["revenue"], 1300.0)


if __name__ == "__main__":
    unittest.main()
