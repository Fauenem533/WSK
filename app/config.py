import os
from datetime import timedelta

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./wsk.db")
SECRET_KEY = os.getenv("SECRET_KEY", "wsk-dev-secret-change-in-production-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = timedelta(days=30)

SCRAPE_INTERVAL_HOURS = int(os.getenv("SCRAPE_INTERVAL_HOURS", "6"))

RACE_SOURCES = {
    "pol": {
        "name": "Półmaraton Komandosa",
        "dist": "21.1 km",
        "date": "2026-02-14",
        "loc": "Warszawa",
        "source_type": "pdf",
        "source_url": "https://www.maratonczyk.pl/wyniki_2026/17_polmaraton_komandosa_2026.pdf",
    },
    "set": {
        "name": "Setka Komandosa",
        "dist": "100 km",
        "date": "2026-03-20",
        "loc": "Lubliniec",
        "source_type": "pdf",
        "source_url": "https://www.zmierzymyczas.pl/images/wyniki/20260321_całość.oficjalne.pdf",
    },
    "cw": {
        "name": "Ćwierćmaraton Komandosa",
        "dist": "10.55 km",
        "date": "2026-05-16",
        "loc": "Słupsk",
        "source_type": "html",
        "source_url": "https://wyniki.b4sport.pl/12-cwiercmaraton-komandosa/e7316.html",
    },
    "bonk": {
        "name": "BONK Komandosa",
        "dist": "50 km",
        "date": "2026-10-10",
        "loc": "Lubliniec",
        "source_type": None,
        "source_url": None,
    },
    "mar": {
        "name": "Maraton Komandosa",
        "dist": "42.2 km",
        "date": "2026-11-28",
        "loc": "Lubliniec",
        "source_type": None,
        "source_url": None,
    },
}
