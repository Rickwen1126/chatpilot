"""Unit tests for pending message queue."""

import time

from chatpilot.queue.pending_queue import PendingQueue


def test_enqueue_dequeue():
    """Basic enqueue and dequeue."""
    q = PendingQueue()
    q.enqueue("session-1", "hello")
    result = q.dequeue("session-1")
    assert result is not None
    assert result.content == "hello"
    assert result.session_id == "session-1"


def test_dequeue_empty():
    """Dequeue from empty queue returns None."""
    q = PendingQueue()
    assert q.dequeue("session-1") is None


def test_dequeue_order():
    """Messages should dequeue in FIFO order."""
    q = PendingQueue()
    q.enqueue("s1", "first")
    q.enqueue("s1", "second")
    r1 = q.dequeue("s1")
    r2 = q.dequeue("s1")
    assert r1.content == "first"
    assert r2.content == "second"
    assert q.dequeue("s1") is None


def test_dequeue_expired():
    """Expired messages should be skipped."""
    q = PendingQueue()
    q.enqueue("s1", "old", ttl_ms=1)  # 1ms TTL — expires immediately
    time.sleep(0.01)  # wait for expiry
    assert q.dequeue("s1") is None


def test_cleanup():
    """Cleanup should remove all expired entries."""
    q = PendingQueue()
    q.enqueue("s1", "old", ttl_ms=1)
    q.enqueue("s2", "fresh", ttl_ms=999_999)
    time.sleep(0.01)
    q.cleanup()
    assert q.dequeue("s1") is None
    result = q.dequeue("s2")
    assert result is not None
    assert result.content == "fresh"
