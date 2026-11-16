"""Small, validated UI preferences stored atomically beside the application."""
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from storage import atomic_json


@dataclass(frozen=True)
class UiSettings:
    idle_seconds: int = 60
    dim_enabled: bool = True
    dim_percent: int = 15

    @classmethod
    def validate(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Geçersiz ekran ayarı")
        delay = value.get("idle_seconds", 60)
        dim = value.get("dim_enabled", True)
        percent = value.get("dim_percent", 15)
        if type(delay) is not int or delay not in (0, 30, 60, 120, 300):
            raise ValueError("Geçersiz bekleme süresi")
        if type(dim) is not bool or type(percent) is not int or not 5 <= percent <= 50:
            raise ValueError("Bekleme parlaklığı %5–50 arasında olmalı")
        return cls(delay, dim, percent)


def load_ui_settings(path):
    try:
        return UiSettings.validate(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return UiSettings()


def save_ui_settings(path, settings):
    settings = UiSettings.validate(asdict(settings))
    atomic_json(path,asdict(settings))
