"""Réveil d'un service hébergé sur le plan gratuit de Render : après une
période d'inactivité, son premier appel peut prendre 30 à 60 s. N'importe
quelle réponse HTTP suffit à le réveiller, même une 404."""

import logging

import httpx

logger = logging.getLogger("booking.wake_up")


async def wake_up(base_url: str, timeout: float) -> None:
    if not base_url:
        return
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            await client.get(f"{base_url}/health")
    except httpx.HTTPError as exc:
        # Pas bloquant : l'appel réel qui suit dira si le service répond.
        logger.warning("Réveil de %s sans réponse : %r", base_url, exc)
