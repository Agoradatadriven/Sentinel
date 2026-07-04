"""Gym logic: compliance status, the Hevy 'PREVIOUS' lookup, and session summary math."""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import GYM_COMPLETED, GYM_INCOMPLETE, GYM_MISSING
from ..models import GymExercise, GymLog


def compute_status(duration_minutes: int, exercise_count: int, required_hours: float) -> str:
    if exercise_count == 0 and duration_minutes == 0:
        return GYM_MISSING
    if duration_minutes >= required_hours * 60 and exercise_count > 0:
        return GYM_COMPLETED
    return GYM_INCOMPLETE


def previous_for_exercise(db: Session, user_id: int, exercise_name: str, before: date) -> dict | None:
    """Last session's top set for an exercise — the grayed-out Hevy 'PREVIOUS' reference."""
    row = db.execute(
        select(GymExercise)
        .join(GymLog, GymExercise.gym_log_id == GymLog.id)
        .where(
            GymLog.user_id == user_id,
            GymExercise.exercise_name == exercise_name,
            GymLog.date < before,
        )
        .order_by(GymLog.date.desc(), GymExercise.id.desc())
    ).scalars().first()
    if not row:
        return None
    return {
        "date": row.log.date.isoformat() if row.log else None,
        "weight": row.weight_value,
        "unit": row.weight_unit,
        "reps": row.reps,
        "sets": row.sets,
        "display": f"{row.weight_value:g} {row.weight_unit} × {row.reps}" if row.weight_value else f"{row.reps} reps",
    }


def session_summary(log: GymLog) -> dict:
    """Duration, total sets, total volume (kg), PR count, muscle activation breakdown."""
    total_sets = 0
    total_volume = 0.0
    prs = 0
    muscles: dict[str, int] = {}
    for ex in log.exercises:
        try:
            sets = json.loads(ex.sets_json or "[]")
        except (ValueError, TypeError):
            sets = []
        if sets:
            for s in sets:
                total_sets += 1
                total_volume += float(s.get("kg", 0) or 0) * float(s.get("reps", 0) or 0)
                if s.get("pr"):
                    prs += 1
        else:
            total_sets += ex.sets or 0
            total_volume += (ex.weight_value or 0) * (ex.reps or 0) * (ex.sets or 1)
        if ex.muscle_group:
            muscles[ex.muscle_group] = muscles.get(ex.muscle_group, 0) + max(1, ex.sets or 1)
    return {
        "duration_minutes": log.duration_minutes,
        "total_sets": total_sets,
        "total_volume_kg": round(total_volume, 1),
        "new_prs": prs,
        "day_type": log.day_type,
        "muscle_activation": muscles,
    }
