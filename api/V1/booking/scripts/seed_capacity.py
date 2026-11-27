"""Seed de la capacité réservable pour le dev/test local, en attendant que le
vrai service Parking (source normale de ces allocations, via POST /v2/booking/capacity-slots/sync)
soit disponible. Alloue une capacité horaire, pour chaque type de place, sur
les prochains jours.

Usage :
    python scripts/seed_capacity.py
    python scripts/seed_capacity.py --days 7 --api-url http://localhost:8000

Route protégée : la clé est lue dans API_KEY (ou --api-key).
"""

import argparse
import os
from datetime import datetime, timedelta, timezone

import httpx

# Répartition arbitraire pour le dev, à ajuster librement.
DEFAULT_CAPACITY = {
    "STANDARD": 10,
    "XL": 3,
    "HANDICAPPED": 2,
    "ELECTRIC": 3,
    "TWO_WHEELS": 5,
}


def seed(api_url: str, days: int, api_key: str) -> None:
    # Naïf en UTC, comme le reste du service (voir app/services/reservation_service.py).
    start_hour = datetime.now(timezone.utc).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    total_hours = days * 24

    headers = {"X-API-Key": api_key} if api_key else {}
    with httpx.Client(timeout=5.0, headers=headers) as client:
        for h in range(total_hours):
            slot_start = start_hour + timedelta(hours=h)
            for place_type, allocated in DEFAULT_CAPACITY.items():
                resp = client.put(
                    f"{api_url}/v2/booking/capacity-slots/{place_type}/{slot_start.isoformat()}",
                    json={"allocated": allocated},
                )
                resp.raise_for_status()

    print(f"Capacité allouée sur {total_hours}h ({days} jour(s)) à partir de {start_hour.isoformat()}.")
    print(f"Répartition : {DEFAULT_CAPACITY}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=2, help="Nombre de jours à semer (défaut : 2).")
    parser.add_argument("--api-url", default="http://localhost:8000", help="URL de l'API Booking.")
    parser.add_argument(
        "--api-key", default=os.environ.get("API_KEY", ""), help="Clé d'API de Booking (défaut : $API_KEY)."
    )
    args = parser.parse_args()
    seed(args.api_url, args.days, args.api_key)
