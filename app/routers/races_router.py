import unicodedata
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Runner, Result, User, Favorite
from app.auth import get_current_user
from app.config import RACE_SOURCES

router = APIRouter(prefix="/api", tags=["races"])


def normalize(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    ).lower()


# --- Races metadata ---

@router.get("/races")
def list_races():
    return [
        {
            "id": rid,
            "name": r["name"],
            "dist": r["dist"],
            "date": r["date"],
            "loc": r["loc"],
            "has_results": r["source_url"] is not None,
        }
        for rid, r in RACE_SOURCES.items()
    ]


# --- Results for a single race ---

@router.get("/results/{race_id}")
def get_results(
    race_id: str,
    gender: Optional[str] = Query(None, regex="^[KM]$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(Result).join(Runner).filter(Result.race_id == race_id)
    if gender:
        q = q.filter(Runner.gender == gender)

    total = q.count()
    q = q.order_by(Result.place)
    results = q.offset((page - 1) * per_page).limit(per_page).all()

    return {
        "race": RACE_SOURCES.get(race_id, {}),
        "total": total,
        "page": page,
        "per_page": per_page,
        "results": [
            {
                "place": r.place,
                "name": r.runner.name,
                "club": r.runner.club,
                "city": r.runner.city,
                "gender": r.runner.gender,
                "category": r.category,
                "time": r.time_str,
                "runner_id": r.runner_id,
            }
            for r in results
        ],
        "counts": {
            "total": db.query(Result).filter(Result.race_id == race_id).count(),
            "M": db.query(Result).join(Runner).filter(Result.race_id == race_id, Runner.gender == "M").count(),
            "K": db.query(Result).join(Runner).filter(Result.race_id == race_id, Runner.gender == "K").count(),
        },
    }


# --- Search runners ---

@router.get("/runners/search")
def search_runners(
    q: str = Query(..., min_length=3),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    norm_q = normalize(q)
    runners = (
        db.query(Runner)
        .filter(Runner.name_normalized.contains(norm_q))
        .limit(50)
        .all()
    )

    fav_ids = set()
    if user:
        fav_ids = {f.runner_id for f in user.favorites}

    done_races = [rid for rid, r in RACE_SOURCES.items() if r["source_url"]]

    return [
        {
            "id": r.id,
            "name": r.name,
            "club": r.club,
            "city": r.city,
            "gender": r.gender,
            "is_favorite": r.id in fav_ids,
            "races_count": len([res for res in r.results if res.time_str != "DNF"]),
            "total_races": len(done_races),
        }
        for r in runners
    ]


# --- Runner profile ---

@router.get("/runners/{runner_id}")
def get_runner(
    runner_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    runner = db.query(Runner).filter(Runner.id == runner_id).first()
    if not runner:
        return {"error": "Nie znaleziono zawodnika"}

    is_fav = False
    if user:
        is_fav = db.query(Favorite).filter(
            Favorite.user_id == user.id, Favorite.runner_id == runner_id
        ).first() is not None

    races = {}
    for res in runner.results:
        races[res.race_id] = {
            "place": res.place,
            "time": res.time_str,
            "category": res.category,
        }

    total_seconds = sum(
        res.time_seconds for res in runner.results
        if res.time_seconds is not None and res.time_str != "DNF"
    )
    completed = sum(1 for res in runner.results if res.time_str != "DNF")

    return {
        "id": runner.id,
        "name": runner.name,
        "club": runner.club,
        "city": runner.city,
        "gender": runner.gender,
        "is_favorite": is_fav,
        "races": races,
        "completed_races": completed,
        "total_seconds": total_seconds,
    }


# --- Global ranking ---

@router.get("/ranking")
def get_ranking(
    gender: Optional[str] = Query(None, regex="^[KM]$"),
    min_races: int = Query(1, ge=1, le=5),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = (
        db.query(
            Runner.id,
            Runner.name,
            Runner.club,
            Runner.gender,
            func.count(Result.id).label("race_count"),
            func.sum(Result.time_seconds).label("total_time"),
        )
        .join(Result)
        .filter(Result.time_str != "DNF", Result.time_seconds.isnot(None))
    )
    if gender:
        q = q.filter(Runner.gender == gender)

    q = q.group_by(Runner.id).having(func.count(Result.id) >= min_races)
    total = q.count()
    q = q.order_by(func.count(Result.id).desc(), func.sum(Result.time_seconds).asc())
    entries = q.offset((page - 1) * per_page).limit(per_page).all()

    def fmt_time(s):
        if not s:
            return "DNF"
        s = int(s)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "entries": [
            {
                "rank": (page - 1) * per_page + i + 1,
                "runner_id": e.id,
                "name": e.name,
                "club": e.club,
                "gender": e.gender,
                "race_count": e.race_count,
                "total_time": fmt_time(e.total_time),
                "total_seconds": e.total_time,
            }
            for i, e in enumerate(entries)
        ],
    }


# --- Favorites ---

@router.post("/favorites/{runner_id}")
def add_favorite(runner_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return {"error": "Zaloguj się"}
    existing = db.query(Favorite).filter(
        Favorite.user_id == user.id, Favorite.runner_id == runner_id
    ).first()
    if existing:
        return {"ok": True, "action": "already_exists"}
    fav = Favorite(user_id=user.id, runner_id=runner_id)
    db.add(fav)
    db.commit()
    return {"ok": True, "action": "added"}


@router.delete("/favorites/{runner_id}")
def remove_favorite(runner_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return {"error": "Zaloguj się"}
    fav = db.query(Favorite).filter(
        Favorite.user_id == user.id, Favorite.runner_id == runner_id
    ).first()
    if fav:
        db.delete(fav)
        db.commit()
    return {"ok": True, "action": "removed"}


@router.get("/favorites")
def list_favorites(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return []
    return [
        {
            "runner_id": f.runner_id,
            "name": f.runner.name,
            "club": f.runner.club,
            "gender": f.runner.gender,
        }
        for f in user.favorites
    ]


# --- History ---

HISTORY = {
    "Półmaraton": {2025: "Andrzej Starżyński 1:19:42", 2024: "Andrzej Starżyński 1:18:12", 2023: "Andrzej Starżyński 1:22:05", 2022: "Andrzej Starżyński 1:19:38", 2021: "Adam Struk 1:25:31", 2020: "COVID", 2019: "Andrzej Starżyński 1:21:33"},
    "Setka": {2025: "Adam Dawid 9:01:12", 2024: "Adam Dawid 8:49:22", 2023: "Adam Dawid 9:14:33", 2022: "Adam Dawid 9:32:00", 2021: "Adam Dawid 9:46:44", 2020: "COVID", 2019: "Adam Dawid 10:23:55"},
    "Ćwierćmaraton": {2025: "Patryk Sowiński 0:46:22", 2024: "Patryk Sowiński 0:45:50", 2023: "Patryk Sowiński 0:47:10", 2022: "Patryk Sowiński 0:46:54"},
    "BONK": {2025: "Adam Dawid 3:15:22", 2024: "Adam Dawid 3:12:44", 2023: "Sebastian Grabarczyk 3:28:15"},
    "Maraton": {2025: "Andrzej Starżyński 2:48:12", 2024: "Andrzej Starżyński 2:47:22", 2023: "Maciej Dutkiewicz 2:55:30"},
}

HISTORY_K = {
    "Półmaraton": {2025: "Agnieszka Kobus 1:42:15", 2024: "Agnieszka Kobus 1:40:55", 2023: "Katarzyna Mańczak 1:47:22"},
    "Setka": {2025: "Katarzyna Mańczak 12:22:33", 2024: "Katarzyna Mańczak 12:05:44"},
    "Ćwierćmaraton": {2025: "Agnieszka Kobus 0:55:12", 2024: "Agnieszka Kobus 0:54:30"},
    "BONK": {2025: "Katarzyna Mańczak 4:15:22"},
    "Maraton": {2025: "Agnieszka Kobus 3:22:15"},
}


@router.get("/history")
def get_history(gender: str = Query("M", regex="^[KM]$")):
    hist = HISTORY_K if gender == "K" else HISTORY
    result = {}
    for race_name, years in hist.items():
        result[race_name] = []
        for year, val in sorted(years.items(), reverse=True):
            if val == "COVID":
                result[race_name].append({"year": year, "name": "Odwołany (COVID)", "time": ""})
            else:
                parts = val.rsplit(" ", 1)
                result[race_name].append({"year": year, "name": parts[0], "time": parts[1]})
    return result
