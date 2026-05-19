"""
Scraper for WSK race results.
Supports: b4sport HTML tables, maratonczyk.pl PDFs, zmierzymyczas.pl PDFs
"""
import io
import re
import logging
import unicodedata
from typing import List, Tuple

import httpx
import pdfplumber
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models import Runner, Result, ScrapeLog
from app.config import RACE_SOURCES

logger = logging.getLogger(__name__)

FEMALE_NAMES = {
    "Agata", "Agnieszka", "Aleksandra", "Alicja", "Alina", "Amelia", "Aneta",
    "Angelika", "Anita", "Anna", "Barbara", "Beata", "Bernadeta", "Bożena",
    "Celina", "Dagmara", "Danuta", "Daria", "Diana", "Dominika", "Dorota",
    "Edyta", "Elżbieta", "Emilia", "Ewa", "Ewelina", "Gabriela", "Grażyna",
    "Halina", "Hanna", "Helena", "Ilona", "Irena", "Iwona", "Izabela",
    "Izabella", "Jadwiga", "Janina", "Joanna", "Jolanta", "Julia", "Justyna",
    "Kamila", "Karolina", "Katarzyna", "Kinga", "Klaudia", "Kornelia",
    "Krystyna", "Laura", "Lidia", "Liliana", "Lucyna", "Magdalena", "Maja",
    "Małgorzata", "Marcela", "Maria", "Mariola", "Marlena", "Marta", "Martyna",
    "Marzena", "Milena", "Monika", "Nadia", "Natalia", "Nina", "Olga",
    "Oliwia", "Patrycja", "Paula", "Paulina", "Renata", "Roksana", "Romana",
    "Sandra", "Sara", "Sonia", "Sylwia", "Teresa", "Urszula", "Weronika",
    "Wiktoria", "Wioleta", "Wioletta", "Zofia", "Zuzanna", "Żaneta",
}


def normalize(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    ).lower()


def time_to_seconds(t: str) -> float | None:
    if not t or t == "DNF":
        return None

    t = re.sub(r"\.\d+$", "", t)
    parts = t.split(":")

    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
    except ValueError:
        return None

    return None


def detect_gender_by_name(name: str) -> str:
    parts = name.split()
    first_name = parts[1] if len(parts) > 1 else parts[0]
    first_name = first_name.capitalize()
    return "K" if first_name in FEMALE_NAMES else "M"


async def scrape_b4sport(url: str) -> List[Tuple]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("tr")
    runners = []

    for tr in rows:
        cells = [td.get_text(strip=True) for td in tr.select("td")]

        if len(cells) >= 11 and re.match(r"^\d+$", cells[0]):
            place = int(cells[0])
            name = cells[1]
            club = cells[3]
            city = cells[4]
            cat = cells[6]
            time = cells[10] or "DNF"
            gender = "K" if cat.startswith("K") or (
                len(cells) > 8 and cells[8].startswith("K")
            ) else "M"

            runners.append((place, name, club, city, cat, gender, time))

    return runners


async def scrape_maratonczyk_pdf(url: str) -> List[Tuple]:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
                "Accept": "application/pdf,text/html,*/*",
                "Referer": "https://www.maratonczyk.pl/"
            }
        )
        resp.raise_for_status()

    runners = []

    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        text = ""
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"

    pattern = re.compile(
        r"(\d{1,4})\s+(\d{1,4})\s+([A-ZŻŹĆŃÓŁŚĄĘ][A-ZŻŹĆŃÓŁŚĄĘa-zżźćńółśąę\-]+)\s+"
        r"([A-ZŻŹĆŃÓŁŚĄĘ][a-zżźćńółśąę\-]+)\s+(.*?)\s+"
        r"(\d+/[KM]\d+)\s+(\d{2}:\d{2}:\d{2})"
    )

    for m in pattern.finditer(text):
        place = int(m.group(1))
        name = f"{m.group(3)} {m.group(4)}"
        club_city = re.sub(r"\s+", " ", m.group(5)).strip()
        cat = m.group(6)
        gender = "K" if "/K" in cat else "M"
        time = m.group(7)

        club, city = "", ""
        parts = club_city.split(",")

        if len(parts) >= 2:
            club = ",".join(parts[:-1]).strip()
            city = parts[-1].strip()
        else:
            club = club_city

        runners.append((place, name, club, city, cat, gender, time))

    return runners


async def scrape_zmierzymyczas_pdf(url: str) -> List[Tuple]:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    runners = []

    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        text = ""
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"

    pattern = re.compile(
        r"(\d{1,4})\s+(\d{1,5})\s+([A-ZŻŹĆŃÓŁŚĄĘa-zżźćńółśąę\-]+)\s+"
        r"([A-ZŻŹĆŃÓŁŚĄĘa-zżźćńółśąę\-]+)\s+(.*?)\s+"
        r"(\d{2}:\d{2}:\d{2})\s+(\d+)"
    )

    for m in pattern.finditer(text):
        place = int(m.group(1))
        surname = m.group(3)
        first = m.group(4)
        name = f"{surname.upper()} {first.capitalize()}"
        club_city = re.sub(r"\s+", " ", m.group(5)).strip()
        time = m.group(6)
        gender = detect_gender_by_name(name)

        club, city = "", ""
        parts = club_city.split(",")

        if len(parts) >= 2:
            club = ",".join(parts[:-1]).strip()
            city = parts[-1].strip()
        else:
            club = club_city

        runners.append((place, name, club, city, "", gender, time))

    return runners


async def scrape_race(race_id: str, db: Session) -> int:
    cfg = RACE_SOURCES.get(race_id)

    if not cfg or not cfg["source_url"]:
        return 0

    url = cfg["source_url"]
    source_type = cfg["source_type"]

    logger.info(f"SCRAPE START race_id={race_id}, url={url}, source_type={source_type}")

    try:
        if source_type == "html":
            raw = await scrape_b4sport(url)
        elif source_type == "pdf" and "maratonczyk" in url:
            raw = await scrape_maratonczyk_pdf(url)
        elif source_type == "pdf":
            raw = await scrape_zmierzymyczas_pdf(url)
        else:
            return 0

        logger.info(f"SCRAPE RAW race_id={race_id}, rows={len(raw)}")

    except Exception as e:
        logger.error(f"Scrape error for {race_id}: {e}")
        db.add(ScrapeLog(race_id=race_id, status="error", message=str(e)))
        db.commit()
        raise

    count = 0
    seen_results = set()

    for place, name, club, city, cat, gender, time_str in raw:
        norm_name = normalize(name)
        unique_key = (race_id, norm_name)

        if unique_key in seen_results:
            logger.warning(
                f"Duplicate result skipped race_id={race_id}, "
                f"name={name}, place={place}"
            )
            continue

        seen_results.add(unique_key)

        runner = db.query(Runner).filter(
            Runner.name_normalized == norm_name
        ).first()

        if not runner:
            runner = Runner(
                name=name,
                name_normalized=norm_name,
                gender=gender,
                club=club,
                city=city,
            )
            db.add(runner)
            db.flush()
        else:
            if gender == "K":
                runner.gender = "K"

            if club and not runner.club:
                runner.club = club

            if city and not runner.city:
                runner.city = city

        existing = db.query(Result).filter(
            Result.runner_id == runner.id,
            Result.race_id == race_id
        ).first()

        if existing:
            existing.place = place
            existing.category = cat
            existing.time_str = time_str
            existing.time_seconds = time_to_seconds(time_str)
        else:
            db.add(Result(
                runner_id=runner.id,
                race_id=race_id,
                place=place,
                category=cat,
                time_str=time_str,
                time_seconds=time_to_seconds(time_str),
            ))

        count += 1

    db.add(ScrapeLog(
        race_id=race_id,
        status="success",
        runners_count=count
    ))

    db.commit()

    logger.info(f"Scraped {race_id}: {count} runners")

    return count


async def scrape_all(db: Session) -> dict:
    results = {}

    for race_id, cfg in RACE_SOURCES.items():
        if cfg["source_url"]:
            try:
                count = await scrape_race(race_id, db)
                results[race_id] = {
                    "status": "ok",
                    "count": count
                }
            except Exception as e:
                db.rollback()
                results[race_id] = {
                    "status": "error",
                    "message": str(e)
                }

    return results
