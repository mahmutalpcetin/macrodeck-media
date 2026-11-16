import bootstrap
import asyncio
from datetime import datetime, timezone
import time
from model import Track

# Windows GSMTC PlaybackStatus.PLAYING (stable public enum value).
PLAYING_STATUS = 4


def source_label(source):
    name = str(source or "").lower()
    for token,label in [('applemusic','APPLE MUSIC'),('spotify','SPOTIFY'),('msedge','EDGE'),('chrome','CHROME'),('firefox','FIREFOX'),('brave','BRAVE')]:
        if token in name:return label
    return 'MEDYA'


def select_session(sessions, current=None, previous=None):
    def key(session):return session.source_app_user_model_id
    def playing(session):
        try:return session.get_playback_info().playback_status == PLAYING_STATUS
        except Exception:return False
    sessions=list(sessions)
    active=[s for s in sessions if playing(s)]
    if current is not None and playing(current) and any(key(s)==key(current) for s in active):
        return current
    for preferred in (previous,):
        if preferred is not None:
            match=next((s for s in active if key(s)==key(preferred)),None)
            if match is not None:return match
    if active:return active[0]
    for preferred in (previous,current):
        if preferred is not None:
            match=next((s for s in sessions if key(s)==key(preferred)),None)
            if match is not None:return match
    return sessions[0] if sessions else None


class MediaReader:
    def __init__(self):
        self.manager = None
        self.session = None
        self.pinned_source = None
        self.sources = []
        self.cover_key = None
        self.cover = None
        self.cover_at = 0

    def cycle_source(self):
        choices = [None] + list(dict.fromkeys(self.sources))
        if self.pinned_source not in choices:
            self.pinned_source = None; self.session = None
            return None
        index = choices.index(self.pinned_source)
        self.pinned_source = choices[(index+1)%len(choices)]
        self.session = None
        return self.pinned_source

    def choose_session(self,sessions,current=None):
        sessions=list(sessions)
        self.sources=[s.source_app_user_model_id for s in sessions]
        if self.pinned_source is not None:
            sessions=[s for s in sessions if s.source_app_user_model_id==self.pinned_source]
        return select_session(sessions,current if self.pinned_source is None else None,self.session)

    async def control(self,action):
        return await self.control_for(self.session,action)

    async def control_for(self,session,action):
        """Never reselect a different application while executing a user command."""
        methods = {"previous": "try_skip_previous_async", "next": "try_skip_next_async",
                   "play_pause": "try_toggle_play_pause_async"}
        if action not in methods:
            raise ValueError("Geçersiz medya komutu.")
        if session is None:
            raise RuntimeError("Önce bir müzik veya video aç.")
        controls = session.get_playback_info().controls
        capability = {'previous':'is_previous_enabled','next':'is_next_enabled','play_pause':'is_play_pause_toggle_enabled'}[action]
        if not getattr(controls,capability,True):
            raise RuntimeError("Bu kaynak seçilen medya komutunu desteklemiyor.")
        accepted = await asyncio.wait_for(getattr(session, methods[action])(), timeout=3)
        if not accepted:
            raise RuntimeError("Medya kaynağı bu komutu kabul etmedi.")
        return True

    async def read(self):
        from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
        from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status
        from winsdk.windows.storage.streams import Buffer, InputStreamOptions, DataReader
        if self.manager is None:
            self.manager = await Manager.request_async()
        session=self.choose_session(self.manager.get_sessions(),self.manager.get_current_session())
        if session is None:
            self.session = None; self.cover = None; self.cover_key = None
            return Track(title=(source_label(self.pinned_source)+" bekleniyor") if self.pinned_source else "Medya bekleniyor",artist="Bu kaynağı aç veya kaynak seç" if self.pinned_source else "Müzik veya video aç",source=self.pinned_source or "",supported_actions=())
        requested_source = self.pinned_source
        props = await session.try_get_media_properties_async()
        playback = session.get_playback_info()
        timeline = session.get_timeline_properties()
        playing = playback.playback_status == Status.PLAYING
        start = timeline.start_time.total_seconds()
        position = max(0, timeline.position.total_seconds() - start)
        duration = max(0, timeline.end_time.total_seconds() - start)
        if playing and timeline.last_updated_time:
            updated = timeline.last_updated_time
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            # Implausible timestamps should not jump the progress to the end.
            delta = (datetime.now(timezone.utc) - updated).total_seconds()
            if 0 <= delta < 86400:
                position += delta * (playback.playback_rate or 1)
        if duration:
            position = min(duration, position)
        key = (session.source_app_user_model_id, props.title, props.artist, props.album_title)
        if key != self.cover_key or (self.cover is None and time.monotonic() - self.cover_at > 20):
            self.cover = None; self.cover_key = key; self.cover_at = time.monotonic()
            if props.thumbnail:
                stream = None
                try:
                    stream = await props.thumbnail.open_read_async()
                    length = min(stream.size, 4_000_000)
                    if stream.size <= 4_000_000 and length:
                        result = await stream.read_async(Buffer(length), length, InputStreamOptions.READ_AHEAD)
                        reader = DataReader.from_buffer(result)
                        data = bytearray(result.length)
                        reader.read_bytes(data)
                        self.cover = bytes(data)
                        reader.close()
                except Exception:
                    self.cover = None
                finally:
                    if stream is not None:
                        stream.close()
        if requested_source != self.pinned_source:
            return Track(source=self.pinned_source or "",supported_actions=())
        self.session = session
        controls = playback.controls
        supported = tuple(action for action,cap in [('previous','is_previous_enabled'),('play_pause','is_play_pause_toggle_enabled'),('next','is_next_enabled')] if getattr(controls,cap,False))
        return Track(title=props.title or "Parça bilgisi bekleniyor", artist=props.artist or source_label(session.source_app_user_model_id),
                     album=props.album_title or "", source=session.source_app_user_model_id,
                     playing=playing, position=position, duration=duration,
                     available=True, cover=self.cover, supported_actions=supported)

    async def safe_read(self):
        try:
            return await asyncio.wait_for(self.read(), timeout=5)
        except Exception:
            self.session=None;self.manager=None;self.cover=None;self.cover_key=None
            raise


# Backward-compatible name for existing project tools.
AppleMusicReader = MediaReader


class DisplayedControls:
    """Physical controls follow the last acknowledged on-device media frame."""
    def __init__(self,reader):
        self.reader=reader;self.session=None;self.transitioning=False
    def commit(self,session):
        self.session=session;self.transitioning=False
    async def control(self,action):
        if self.transitioning:raise RuntimeError('Kaynak değişiyor, kısa bir an bekle.')
        return await self.reader.control_for(self.session,action)
