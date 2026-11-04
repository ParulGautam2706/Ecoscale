import copy

from sqlalchemy.orm import Session

from app.core.defaults import DEFAULT_SETTINGS
from app.models.entities import AppSetting


def get_all(db: Session) -> dict:
    out = copy.deepcopy(DEFAULT_SETTINGS)
    for row in db.query(AppSetting).all():
        if row.key in out and isinstance(out[row.key], dict):
            out[row.key].update(row.value)
    return out


def update(db: Session, key: str, value: dict) -> dict:
    if key not in DEFAULT_SETTINGS:
        raise ValueError(f"unknown settings group '{key}'")
    unknown = set(value) - set(DEFAULT_SETTINGS[key])
    if unknown:
        raise ValueError(f"unknown keys for '{key}': {sorted(unknown)}")
    if key == "weights":
        if any(v < 0 for v in value.values()):
            raise ValueError("weights must be >= 0")
        merged = {**DEFAULT_SETTINGS["weights"], **get_all(db)["weights"], **value}
        total = sum(merged.values())
        if total <= 0:
            raise ValueError("weights must not all be zero")
        value = {k: v / total for k, v in merged.items()}   # normalised to sum 1
    row = db.get(AppSetting, key)
    current = dict(row.value) if row else {}
    current.update(value)
    if row:
        row.value = current
    else:
        db.add(AppSetting(key=key, value=current))
    db.commit()
    return get_all(db)[key]
