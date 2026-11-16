"""Interaction timing independent of media/serial I/O."""
class InteractionState:
    def __init__(self, now, idle_seconds=60):
        self.idle_seconds=idle_seconds
        self.last_activity=now
        self.idle=False

    def touch(self, now):
        was_idle=self.idle
        self.last_activity=now
        self.idle=False
        return was_idle

    def update(self, playing, now, volume_active=False):
        if playing or volume_active:self.last_activity=now
        self.idle=not playing and not volume_active and self.idle_seconds>0 and now-self.last_activity >= self.idle_seconds
        return self.idle
