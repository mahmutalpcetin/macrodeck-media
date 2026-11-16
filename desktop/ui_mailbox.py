"""Bounded latest-state mailbox between the device thread and Tk.

Frames and labels are state, not a playback queue. A slow/occluded desktop
window should render the latest state rather than retaining old bitmaps.
User commands use a separate FIFO and are never coalesced here.
"""
from collections import OrderedDict
from queue import Empty
from threading import Lock


class UiMailbox:
    def __init__(self):
        self._lock = Lock()
        self._pending = OrderedDict()

    def put(self, message):
        kind, value = message
        with self._lock:
            self._pending[kind] = value

    def get_nowait(self):
        with self._lock:
            if not self._pending:
                raise Empty
            return self._pending.popitem(last=False)

    def qsize(self):
        with self._lock:
            return len(self._pending)
