from dataclasses import dataclass, field

ACTION_NAMES = ["Devre dışı"] + [f"F{i}" for i in range(13, 25)] + [
    "Önceki parça", "Sonraki parça", "Oynat / duraklat", "Sistem sesini kapat",
    "Ses artır", "Ses azalt",
]
DEFAULT_CONFIG = {"keys": [1, 2, 13, 14, 3, 4], "invert": False, "steps": 4}


def validate_config(value):
    keys = value.get("keys")
    if not isinstance(keys, list) or len(keys) != 6 or any(type(k) is not int or not 0 <= k <= 18 for k in keys):
        raise ValueError("Altı tuş için geçerli işlev seçilmelidir.")
    if type(value.get("invert")) is not bool or type(value.get("steps")) is not int or value["steps"] not in (2, 4):
        raise ValueError("Geçersiz encoder ayarı.")
    return {"keys": keys[:], "invert": value["invert"], "steps": value["steps"]}


@dataclass
class Track:
    title: str = "Medya bekleniyor"
    artist: str = "Müzik veya video aç"
    album: str = ""
    source: str = ""
    playing: bool = False
    position: float = 0
    duration: float = 0
    available: bool = False
    cover: bytes | None = field(default=None, repr=False)
    demo: bool = False
    supported_actions: tuple = ("previous","play_pause","next")

    def summary(self):
        return {k: v for k, v in vars(self).items() if k != "cover"} | {"cover_bytes": len(self.cover or b"")}
