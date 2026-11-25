"""Mise à jour minimale du schéma au démarrage. `Base.metadata.create_all`
crée les tables absentes mais n'ajoute jamais de colonne à une table qui
existe déjà (base Neon en prod, booking.db en local) : les colonnes ajoutées
après coup sont listées ici et créées si besoin. Suffisant pour ce MVP ; à
remplacer par Alembic si le schéma continue d'évoluer."""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

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
