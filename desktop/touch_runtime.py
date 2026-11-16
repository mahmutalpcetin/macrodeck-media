"""Touch state, calibration and media dispatch, independent of GUI/serial I/O."""
import json
import logging
import time
from touch import validate_calibration, fit_calibration, verify_corner, position, hit_test
from rendering import render, render_calibration, safe_seconds
from storage import atomic_json


class TouchRuntime:
    def __init__(self, path, notice=lambda message: None, feedback=lambda action: None, navigate=None, motion=None, dispatch=None):
        self.dispatch=dispatch
        self.motion = motion
        self.navigate = navigate
        self.path = path; self.notice = notice; self.feedback = feedback
        self.coefficients = None; self.calibration = None; self.shown_at = None
        self.last_id = 0; self.last_action_at = 0; self.last_action_event_ms=None
        try:
            self.coefficients = validate_calibration(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            pass

    def reset_connection(self):
        self.last_id = 0; self.last_action_event_ms=None; self.last_action_at=0; self.cancel()

    def start(self):
        self.calibration = []; self.shown_at = None
        self.notice("Dört hedefin ortasına sırayla basıp parmağını kaldır.")

    def cancel(self):
        self.calibration = None; self.shown_at = None

    def image(self, track):
        index = len(self.calibration) if self.calibration is not None else None
        key = (index,) if index is not None else (track.title,track.artist,track.album,track.source,
               track.playing,track.available,track.demo,track.supported_actions,int(safe_seconds(track.position)),int(safe_seconds(track.duration)),track.cover)
        if key != getattr(self,'_image_key',None):
            self._image_cache = render_calibration(index) if index is not None else render(track)
            self._image_key = key
        return self._image_cache, index

    def frame_sent(self, index):
        if index is not None and self.calibration is not None and len(self.calibration) == index and self.shown_at is None:
            self.shown_at = time.monotonic()

    async def handle(self, event, reader, demo=False):
        event_id = event.get("id")
        if type(event_id) is not int or event_id <= self.last_id:
            return
        self.last_id = event_id
        rx, ry = event.get("raw_x"), event.get("raw_y")
        if type(rx) is not int or type(ry) is not int or not (0 <= rx <= 4095 and 0 <= ry <= 4095):
            return
        now = time.monotonic()
        if now - event.get("received_at", 0) > 2.5:
            return
        phase=event.get('phase','down')
        if phase not in ('down','move','up'):return
        if phase != 'down':
            if self.calibration is None and self.coefficients is not None and not demo and self.motion is not None:
                x,y=position(self.coefficients,rx,ry)
                await self.motion(x,y,phase)
            return
        if self.calibration is not None:
            if self.shown_at is None or event["received_at"] < self.shown_at:
                return
            self.calibration.append((rx, ry)); self.shown_at = None
            if len(self.calibration) == 4:
                try:
                    candidate = fit_calibration(self.calibration[:3])
                    if not verify_corner(candidate, self.calibration[3]):
                        raise ValueError("Son hedef eşleşmedi; merkezlere yeniden bas.")
                    atomic_json(self.path,candidate)
                    self.coefficients = candidate; self.calibration = None
                    self.notice("Dokunmatik ayarı kaydedildi. Medya düğmeleri hazır.")
                except (ValueError, OSError) as exc:
                    self.calibration = []; self.notice(str(exc))
            return
        if self.coefficients is None:
            self.notice("Önce ‘Dokunmatik ayarla’ düğmesini kullan."); return
        stamp=event.get('event_ms')
        valid_stamp=type(stamp) is int and 0<=stamp<=0xffffffff
        elapsed=((stamp-self.last_action_event_ms)&0xffffffff)/1000 if valid_stamp and self.last_action_event_ms is not None else now-self.last_action_at
        if demo or elapsed<0.12:return
        x,y = position(self.coefficients,rx,ry)
        if self.navigate is not None and await self.navigate(x,y):
            self.last_action_at = now
            self.last_action_event_ms=stamp if valid_stamp else None
            return
        action = hit_test(x,y)
        if action is None:
            return
        self.last_action_at = now
        self.last_action_event_ms=stamp if valid_stamp else None
        self.feedback(action)
        try:
            dispatched = time.monotonic()
            if self.dispatch is not None:
                self.dispatch(reader,action)
                logging.getLogger('macrodeck').info('Dokunmatik medya komutu sıraya alındı: %s',action)
            else:
                await reader.control(action)
                logging.getLogger("macrodeck").info("Dokunmatik medya komutu: %s | Windows yaniti %.0f ms",
                                                   action, (time.monotonic()-dispatched)*1000)
        except Exception as exc:
            self.notice(str(exc))
            logging.getLogger("macrodeck").warning("Medya komutu kabul edilmedi: %s", exc)
