"""Mise à jour minimale du schéma au démarrage. `Base.metadata.create_all`
crée les tables absentes mais n'ajoute jamais de colonne à une table qui
existe déjà (base Neon en prod, booking.db en local) : les colonnes ajoutées
après coup sont listées ici et créées si besoin. Suffisant pour ce MVP ; à
remplacer par Alembic si le schéma continue d'évoluer."""

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .orm_models import CapacitySlotModel

logger = logging.getLogger("booking.migrations")

# (table, colonne, type SQL) : types compatibles SQLite et Postgres.
ADDED_COLUMNS = [
    ("reservations", "correlation_id", "VARCHAR(128)"),
    ("reservations", "payment_idempotency_key", "VARCHAR(64)"),
]


def add_missing_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table, column, sql_type in ADDED_COLUMNS:
        if table not in tables:
            continue
        existing = {col["name"] for col in inspector.get_columns(table)}
        if column in existing:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
        logger.info("Colonne %s.%s ajoutée au schéma existant", table, column)


def split_hourly_capacity(engine: Engine, now: datetime | None = None) -> int:
    """Passage de la capacité à l'heure au quart d'heure (v2.7.0).

    Avant, un créneau de capacité couvrait une heure (ligne à hh:00). Chaque
    ligne à venir reçoit ses trois quarts d'heure suivants (hh:15, hh:30,
    hh:45) avec la même allocation et le même nombre de places réservées :
    les réservations d'avant la v2.7.0 tombaient toutes sur des heures
    pleines, elles occupent donc chacun des quatre quarts d'heure.

    Ne fait rien dès qu'un quart d'heure existe déjà dans le calendrier à
    venir : la migration ne tourne qu'une fois, à la première mise en ligne.
    Renvoie le nombre de quarts d'heure créés."""
    current_hour = (now or datetime.utcnow()).replace(minute=0, second=0, microsecond=0)
    with Session(engine) as session:
        rows = session.query(CapacitySlotModel).filter(CapacitySlotModel.slot_start >= current_hour).all()
        if not rows or any(row.slot_start.minute != 0 for row in rows):
            return 0
        existing = {(row.place_type, row.slot_start) for row in rows}
        created = []
        for row in rows:
            for quarter in (1, 2, 3):
                slot_start = row.slot_start + timedelta(minutes=15 * quarter)
                if (row.place_type, slot_start) in existing:
                    continue
                created.append(
                    CapacitySlotModel(
                        id=str(uuid.uuid4()),
                        place_type=row.place_type,
                        slot_start=slot_start,
                        allocated=row.allocated,
                        booked=row.booked,
                    )
                )
        session.add_all(created)
        session.commit()
    logger.info("Capacité passée au quart d'heure : %s créneau(x) créé(s)", len(created))
    return len(created)
