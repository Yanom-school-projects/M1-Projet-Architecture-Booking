"""Configuration commune des tests.

Les variables d'environnement sont fixées AVANT tout import de `app` : la
configuration (app/config.py) et la connexion à la base sont lues une seule
fois, au premier import. Les tests utilisent donc une base SQLite jetable,
une clé d'API connue et aucun service extérieur (bus, Parking, suivi du
paiement en tâche de fond désactivés).

Les variables d'environnement passent devant le fichier .env local : un
.env de développement ne change rien aux tests."""

import os
import tempfile
from pathlib import Path

API_KEY = "cle-de-test"

_tmp_dir = Path(tempfile.mkdtemp(prefix="booking-tests-"))
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{(_tmp_dir / 'test.db').as_posix()}",
        "API_KEY": API_KEY,
        "CLOUDAMQP_URL": "",
        "PARKING_SERVICE_URL": "",
        "LOG_DIR": "",
        # Pas de boucle de suivi du paiement après POST /reservations : les
        # tests font avancer le paiement eux-mêmes (voir FakePayment).
        "PAYMENT_POLL_TIMEOUT_SECONDS": "0",
    }
)

import pytest  # noqa: E402

from app.adapters.outbound.persistence.database import Base, engine  # noqa: E402
from app.adapters.outbound.persistence.unit_of_work import SqlAlchemyUnitOfWork  # noqa: E402
from app.application.reservation_service import ReservationService  # noqa: E402
from app.config import settings  # noqa: E402
from tests.fakes import Fakes  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    """Base vide à chaque test : aucun test ne dépend d'un autre."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def uow():
    unit_of_work = SqlAlchemyUnitOfWork()
    yield unit_of_work
    unit_of_work.close()


@pytest.fixture
def fakes() -> Fakes:
    return Fakes()


@pytest.fixture
def service(uow, fakes) -> ReservationService:
    """ReservationService réel, branché sur la base de test et sur de faux
    Vehicles / Pricing / Payment / bus d'événements."""
    return ReservationService(
        uow=uow,
        vehicles=fakes.vehicles,
        pricing=fakes.pricing,
        payment=fakes.payment,
        events=fakes.events,
        settings=settings,
        metrics=fakes.metrics,
    )


@pytest.fixture
def app(fakes):
    """L'application FastAPI réelle (routes, sécurité, middlewares, métriques
    Prometheus), avec le ReservationService branché sur les faux services."""
    from fastapi import Depends

    from app.adapters.inbound.http.dependencies import get_reservation_service, get_unit_of_work
    from app.adapters.outbound.metrics.prometheus_metrics import business_metrics
    from app.main import app as fastapi_app

    def service_with_fakes(uow=Depends(get_unit_of_work)) -> ReservationService:
        return ReservationService(
            uow=uow,
            vehicles=fakes.vehicles,
            pricing=fakes.pricing,
            payment=fakes.payment,
            events=fakes.events,
            settings=settings,
            metrics=business_metrics,
        )

    fastapi_app.dependency_overrides[get_reservation_service] = service_with_fakes
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def anonymous(app):
    """Client HTTP sans clé d'API. raise_server_exceptions=False : une erreur
    500 est renvoyée comme le verrait un vrai client, au lieu d'être levée."""
    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def client(app):
    """Client HTTP qui envoie la bonne clé d'API, comme le front ou Access."""
    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False, headers={"X-API-Key": API_KEY}) as test_client:
        yield test_client
