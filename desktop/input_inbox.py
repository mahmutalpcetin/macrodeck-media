"""Event-loop-local device input queue with coalesced drag positions."""
import asyncio
from collections import deque


class InputInbox:
    def __init__(self, limit=128):
        self.items = deque()
        self.ready = asyncio.Event()
        self.limit = limit
        self.dropped = 0

    def push(self, source, event):
        move = event.get("type") == "touch" and event.get("phase") == "move"
        if move and self.items:
            previous_source, previous = self.items[-1]
            if previous_source is source and previous.get("type") == "touch" and previous.get("phase") == "move":
                self.items[-1] = (source, event)
                return
        if len(self.items) >= self.limit:
            # Prefer deleting an obsolete drag position over a press/release.
            index = next((i for i, (_, item) in enumerate(self.items)
                          if item.get("type") == "touch" and item.get("phase") == "move"), None)
            if index is not None:
                del self.items[index]
            elif move:
                self.dropped += 1
                return
            else:
                self.items.popleft()
            self.dropped += 1
        self.items.append((source, event))
        self.ready.set()

    async def get(self):
        while not self.items:
            self.ready.clear()
            await self.ready.wait()
        return self.items.popleft()
