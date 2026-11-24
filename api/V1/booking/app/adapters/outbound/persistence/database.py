"""Connexion SQLAlchemy : détail d'implémentation de l'adaptateur de
persistance, jamais importé par domain/ ou application/. SQLite en dev,
Postgres en prod via DATABASE_URL — même code des deux côtés."""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings


def _normalize_url(url: str) -> str:
    # Neon/Render donnent une URL `postgresql://` (ou `postgres://`) : sans
    # précision, SQLAlchemy chercherait psycopg2. On force psycopg 3, pour
    # pouvoir coller l'URL du fournisseur telle quelle dans DATABASE_URL.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


database_url = _normalize_url(settings.database_url)

# check_same_thread=False : nécessaire uniquement pour SQLite, dont les
# connexions sont par défaut réservées au thread qui les a ouvertes, ce qui
# casse avec le pool de threads de FastAPI/Starlette.
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
# pool_pre_ping : Neon met la base en veille après quelques minutes
# d'inactivité et coupe les connexions ; on vérifie chaque connexion du pool
# avant de s'en servir plutôt que d'échouer sur une connexion morte.
engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
