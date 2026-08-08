"""Unit tests for conduit.resumability.InMemoryEventStore — pure logic, no I/O."""

from __future__ import annotations

import pytest
from mcp_types import JSONRPCNotification

from conduit.resumability import InMemoryEventStore


def _msg(method: str) -> JSONRPCNotification:
    return JSONRPCNotification(jsonrpc="2.0", method=method)


class Collector:
    """An async callback that records every EventMessage it's given."""

    def __init__(self) -> None:
        self.received: list = []

    async def __call__(self, event_message) -> None:
        self.received.append(event_message)

    @property
    def methods(self) -> list[str]:
        return [em.message.method for em in self.received]


@pytest.fixture
def store():
    return InMemoryEventStore(max_events_per_stream=5, max_streams=3)


async def test_replay_returns_only_events_strictly_after_last_seen():
    store = InMemoryEventStore()
    ids = [await store.store_event("s1", _msg(f"m{i}")) for i in range(5)]

    collector = Collector()
    stream = await store.replay_events_after(ids[1], collector)

    assert stream == "s1"
    assert collector.methods == ["m2", "m3", "m4"]


async def test_replay_from_latest_event_yields_nothing():
    store = InMemoryEventStore()
    ids = [await store.store_event("s1", _msg(f"m{i}")) for i in range(3)]

    collector = Collector()
    stream = await store.replay_events_after(ids[-1], collector)

    assert stream == "s1"
    assert collector.received == []


async def test_replay_unknown_stream_returns_none():
    store = InMemoryEventStore()
    await store.store_event("s1", _msg("m0"))

    collector = Collector()
    result = await store.replay_events_after("unknown-stream:0", collector)

    assert result is None
    assert collector.received == []


@pytest.mark.parametrize("bad_id", ["not-a-valid-id", "", "s1", "s1:not-a-number"])
async def test_replay_malformed_event_id_returns_none(bad_id):
    store = InMemoryEventStore()
    collector = Collector()
    assert await store.replay_events_after(bad_id, collector) is None
    assert collector.received == []


async def test_priming_events_are_not_replayed_but_keep_sequence_contiguous():
    store = InMemoryEventStore()
    priming_id = await store.store_event("s1", None)  # priming event: no message
    real_id = await store.store_event("s1", _msg("real"))

    collector = Collector()
    stream = await store.replay_events_after(priming_id, collector)

    assert stream == "s1"
    assert collector.methods == ["real"]
    assert real_id != priming_id  # sequence advanced even though priming carried no message


async def test_streams_are_independent():
    store = InMemoryEventStore()
    a_ids = [await store.store_event("a", _msg("a0")), await store.store_event("a", _msg("a1"))]
    await store.store_event("b", _msg("b0"))

    collector = Collector()
    stream = await store.replay_events_after(a_ids[0], collector)

    assert stream == "a"
    assert collector.methods == ["a1"]


async def test_old_events_are_evicted_per_stream_cap(store):  # max_events_per_stream=5
    ids = [await store.store_event("s1", _msg(f"m{i}")) for i in range(8)]  # overflows the cap of 5

    collector = Collector()
    # ids[0..2] (m0-m2) were evicted to hold the cap at 5; the buffer now holds
    # m3-m7. The anchor (ids[2], i.e. m2) is itself gone, but everything still
    # held has a higher sequence number than it, so it should all come back —
    # proving replay degrades to "everything we still have" rather than
    # silently under- or over-reporting when the exact anchor has aged out.
    stream = await store.replay_events_after(ids[2], collector)

    assert stream == "s1"
    assert collector.methods == ["m3", "m4", "m5", "m6", "m7"]


async def test_stream_count_is_capped_with_lru_eviction(store):  # max_streams=3
    await store.store_event("a", _msg("a0"))
    await store.store_event("b", _msg("b0"))
    await store.store_event("c", _msg("c0"))
    await store.store_event("a", _msg("a1"))  # touch "a" so it's no longer the least-recently-used
    await store.store_event("d", _msg("d0"))  # forces an eviction — "b" is now the oldest-touched

    evicted = Collector()
    assert await store.replay_events_after("b:0", evicted) is None  # evicted
    assert evicted.received == []

    survivor = Collector()
    stream = await store.replay_events_after("a:0", survivor)
    assert stream == "a"
    assert survivor.methods == ["a1"]
