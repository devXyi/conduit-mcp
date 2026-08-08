"""In-memory event storage for Streamable HTTP session resumability."""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass, field

from mcp.server.streamable_http import EventCallback, EventId, EventMessage, EventStore, StreamId
from mcp.types import JSONRPCMessage


@dataclass
class _StreamLog:
    events: deque[tuple[int, JSONRPCMessage | None]] = field(default_factory=deque)
    next_seq: int = 0


class InMemoryEventStore(EventStore):
    """A bounded, per-stream event log. Oldest events/streams are evicted first."""

    def __init__(self, max_events_per_stream: int = 1000, max_streams: int = 1000) -> None:
        self.max_events_per_stream = max_events_per_stream
        self.max_streams = max_streams
        self._streams: OrderedDict[StreamId, _StreamLog] = OrderedDict()

    async def store_event(self, stream_id: StreamId, message: JSONRPCMessage | None) -> EventId:
        log = self._streams.get(stream_id)
        if log is None:
            if len(self._streams) >= self.max_streams:
                self._streams.popitem(last=False)
            log = _StreamLog()
            self._streams[stream_id] = log
        else:
            self._streams.move_to_end(stream_id)
        seq = log.next_seq
        log.next_seq += 1
        log.events.append((seq, message))
        if len(log.events) > self.max_events_per_stream:
            log.events.popleft()
        return f"{stream_id}:{seq}"

    async def replay_events_after(self, last_event_id: EventId, send_callback: EventCallback) -> StreamId | None:
        stream_id, sep, seq_str = last_event_id.rpartition(":")
        if not sep or not seq_str.isdigit():
            return None
        log = self._streams.get(stream_id)
        if log is None:
            return None
        last_seq = int(seq_str)
        for seq, message in log.events:
            if seq <= last_seq or message is None:
                continue
            await send_callback(EventMessage(message=message, event_id=f"{stream_id}:{seq}"))
        return stream_id
