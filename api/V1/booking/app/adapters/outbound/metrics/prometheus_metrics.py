"""Adaptateur Prometheus du port BusinessMetrics : chaque opération incrémente
parking_operations_total{service="booking", operation=..., result=...}."""

from app.metrics import PARKING_OPERATIONS
from app.ports.metrics import BusinessMetrics

SERVICE_NAME = "booking"


class PrometheusBusinessMetrics(BusinessMetrics):
    def record(self, operation: str, result: str) -> None:
        PARKING_OPERATIONS.labels(service=SERVICE_NAME, operation=operation, result=result).inc()


# Sans état (les compteurs sont globaux au process) : une instance suffit.
business_metrics = PrometheusBusinessMetrics()
