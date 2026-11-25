"""Configuration du logging de Booking : console (lue par Render) et, si
log_dir est renseigné, un fichier par jour avec purge automatique des
fichiers plus vieux que log_retention_days."""

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

from app.config import settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_FILE_NAME = "booking.log"


def _daily_file_handler(formatter: logging.Formatter) -> logging.Handler | None:
    """Fichier du jour : booking.log, archivé en booking.AAAA-MM-JJ.log à minuit.
    Renvoie None si le dossier n'est pas accessible : un problème de logs ne
    doit jamais empêcher le service de démarrer."""
    try:
        os.makedirs(settings.log_dir, exist_ok=True)
        handler = TimedRotatingFileHandler(
            os.path.join(settings.log_dir, LOG_FILE_NAME),
            when="midnight",
            backupCount=settings.log_retention_days,
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"Logs fichier désactivés ({exc}), console uniquement", file=sys.stderr)
        return None

    handler.suffix = "%Y-%m-%d"
    # booking.log.2026-11-24 -> booking.2026-11-24.log : forme que la purge
    # de TimedRotatingFileHandler (backupCount) sait reconnaître.
    handler.namer = lambda name: name.replace("booking.log.", "booking.") + ".log"
    handler.setFormatter(formatter)
    return handler


def setup_logging() -> None:
    """Configure le logging pour l'application Booking.

    - Niveau de log configurable par variable d'environnement LOG_LEVEL.
    - Log vers la console (Render) et vers un fichier journalier (LOG_DIR,
      vide = console uniquement).
    - Format : timestamp | niveau | logger | message
    """
    formatter = logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    handlers: list[logging.Handler] = [console]

    if settings.log_dir:
        file_handler = _daily_file_handler(formatter)
        if file_handler:
            handlers.append(file_handler)

    root = logging.getLogger()
    root.handlers[:] = handlers
    level = logging.getLevelNamesMapping().get(settings.log_level.upper())
    if level is not None:
        root.setLevel(level)
    else:
        root.setLevel(logging.INFO)
        logging.getLogger("booking").warning("LOG_LEVEL=%r inconnu, niveau INFO utilisé", settings.log_level)

    # Les logs d'uvicorn (accès HTTP, erreurs serveur) passent par les mêmes
    # handlers que ceux de l'application.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
