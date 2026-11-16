"""Remember automatic mode or the user-selected Windows media source ID."""
import json
from pathlib import Path
from storage import atomic_json

class SourceSettings:
    def __init__(self,path):self.path=Path(path)
    def load(self):
        try:
            value=json.loads(self.path.read_text(encoding='utf-8'))['source']
            if value is None or isinstance(value,str) and 0 < len(value) <= 512:return value
        except (OSError,ValueError,KeyError,TypeError):pass
        return None
    def save(self,value):
        if value is not None and (not isinstance(value,str) or not 0 < len(value) <= 512):
            raise ValueError('Invalid source ID')
        atomic_json(self.path,{'source':value})
