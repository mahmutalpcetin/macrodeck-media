"""Saved host-side brightness; UI keeps a visible minimum to avoid lockout."""
import json
from pathlib import Path
from storage import atomic_json

def validate_brightness(value):
    if type(value) is not int or not 5 <= value <= 100:
        raise ValueError('Parlaklık 5–100 arasında olmalı.')
    return value

class BrightnessSettings:
    def __init__(self,path):self.path=Path(path)
    def load(self):
        try:return validate_brightness(json.loads(self.path.read_text(encoding='utf-8'))['brightness'])
        except (OSError,ValueError,KeyError,TypeError):return 100
    def save(self,value):
        value=validate_brightness(value)
        atomic_json(self.path,{'brightness':value})


class BrightnessDrag:
    """Capture only slider-origin gestures; movement never becomes a media tap."""
    def __init__(self):self.active=False
    @staticmethod
    def level(x):return max(5,min(100,round(5+(x-20)/280*95)))
    def begin(self,x,y):
        self.active=20 <= x <= 300 and 100 <= y <= 145
        return self.level(x) if self.active else None
    def move(self,x,y,phase):
        if not self.active:return None
        value=self.level(x)
        if phase=='up':self.active=False
        return value


def effective_brightness(preferred, idle, dim_percent=15):
    """Standby dimming never changes the saved user preference."""
    preferred=validate_brightness(preferred)
    if type(dim_percent) is not int or not 5 <= dim_percent <= 50:raise ValueError("Invalid standby brightness")
    return min(preferred,dim_percent) if idle else preferred
