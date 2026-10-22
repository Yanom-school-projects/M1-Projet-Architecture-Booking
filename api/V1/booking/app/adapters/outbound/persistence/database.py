"""Connexion SQLAlchemy : détail d'implémentation de l'adaptateur de
persistance, jamais importé par domain/ ou application/. SQLite en dev,
Postgres en prod via DATABASE_URL — même code des deux côtés."""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# check_same_thread=False : nécessaire uniquement pour SQLite, dont les
# connexions sont par défaut réservées au thread qui les a ouvertes, ce qui
# casse avec le pool de threads de FastAPI/Starlette.
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
