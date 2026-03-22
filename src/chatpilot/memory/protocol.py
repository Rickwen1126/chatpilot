from __future__ import annotations

from datetime import datetime
from typing import Protocol


class MemoryStore(Protocol):
    """Async key-value store scoped by route and record type.

    Every record is uniquely addressed by ``(route_id, type, id)``.
    Implementations may persist to SQLite, in-memory dicts, disk JSON, etc.
    """

    async def save(self, route_id: str, type: str, data: dict) -> str:
        """Persist a new record and return its generated id.

        Parameters
        ----------
        route_id:
            The chat route (channel / user) that owns the record.
        type:
            Logical record type, e.g. ``"task"``, ``"context"``, ``"summary"``.
        data:
            Arbitrary payload; the store may inject ``id``, ``created_at``.

        Returns
        -------
        str
            The unique id assigned to the saved record.
        """
        ...

    async def get(self, route_id: str, type: str, id: str) -> dict | None:
        """Fetch a single record by its id, or ``None`` if not found.

        Parameters
        ----------
        route_id:
            The chat route that owns the record.
        type:
            Logical record type.
        id:
            The unique id returned by :meth:`save`.
        """
        ...

    async def list(self, route_id: str, type: str) -> list[dict]:
        """Return all records of the given type under a route.

        Parameters
        ----------
        route_id:
            The chat route that owns the records.
        type:
            Logical record type to list.

        Returns
        -------
        list[dict]
            Records in insertion order (oldest first).
        """
        ...

    async def delete(self, route_id: str, type: str, id: str) -> bool:
        """Remove a record. Return ``True`` if it existed, ``False`` otherwise.

        Parameters
        ----------
        route_id:
            The chat route that owns the record.
        type:
            Logical record type.
        id:
            The unique id of the record to delete.
        """
        ...

    async def update(self, route_id: str, type: str, id: str, data: dict) -> None:
        """Merge *data* into an existing record (shallow update).

        Parameters
        ----------
        route_id:
            The chat route that owns the record.
        type:
            Logical record type.
        id:
            The unique id of the record to update.
        data:
            Fields to merge into the existing record.

        Raises
        ------
        KeyError
            If the record does not exist.
        """
        ...

    async def query_due_before(self, type: str, before: datetime) -> list[dict]:
        """Return records of *type* across all routes whose ``due`` field <= *before*.

        This is a cross-route query used by the scheduler to find tasks
        that are due for execution.

        Parameters
        ----------
        type:
            Logical record type (typically ``"task"``).
        before:
            Upper bound (inclusive) on the ``due`` datetime field.

        Returns
        -------
        list[dict]
            Matching records, ordered by ``due`` ascending.
        """
        ...
