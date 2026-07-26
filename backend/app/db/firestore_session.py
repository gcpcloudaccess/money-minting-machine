"""Firestore-backed drop-in for the subset of sqlalchemy.orm.Session/Query
this codebase actually uses: query().filter_by().filter(col.in_(...)).
order_by(col.desc()/.asc()).limit().first()/.all()/.one_or_none(), plus
add()/flush()/commit()/refresh()/get()/close(). Not a general ORM - see
app/db/models_firestore.py's module docstring for how this pairing was
scoped (every db.query()/db.add() call site in the app was grepped before
either file was written).

Auto-increment integer ids are kept (rather than switching to Firestore's
native string document ids) so API paths and JSON responses that already
assume an int (e.g. GET /decisions/{decision_id}: int, latest_decision_id in
/watchlist) don't need to change anywhere. Ids are allocated from a
per-collection counter document in a reserved "_counters" collection,
incremented inside a Firestore transaction so two concurrent writers can
never hand out the same id twice - though in practice this app runs with
Cloud Run min/max instances both pinned to 1 specifically to avoid
concurrent writers altogether (see the session's earlier discussion on
double-ticking), so this is a safety margin, not a load-bearing assumption.

This module is only imported when Settings.use_firestore is True (see
app/db/session.py) - the `google.cloud.firestore` import is deferred inside
functions so the default SQLite path never needs that package installed."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from app.config import get_settings
from app.db.models_firestore import Column, FirestoreModel, _Asc, _Desc, _In, _columns

if TYPE_CHECKING:
    from google.cloud import firestore as _firestore_types

_client = None
_client_lock = threading.Lock()


def get_client():
    """Lazily creates (and caches) the Firestore client. Uses Application
    Default Credentials - on Cloud Run that's the service's own runtime
    service account, no key file needed, as long as the Firestore API is
    enabled and that service account has the Cloud Datastore User role
    (granted by default to the default compute service account in most
    projects). FIRESTORE_PROJECT_ID is optional - if unset, the client
    infers the project from the environment (GOOGLE_CLOUD_PROJECT, which
    Cloud Run sets automatically)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from google.cloud import firestore

                settings = get_settings()
                _client = firestore.Client(project=settings.firestore_project_id or None)
    return _client


def _next_id(collection_name: str) -> int:
    from google.cloud import firestore

    client = get_client()
    counter_ref = client.collection("_counters").document(collection_name)

    @firestore.transactional
    def _increment(transaction) -> int:
        snapshot = counter_ref.get(transaction=transaction)
        current = snapshot.get("next_id") if snapshot.exists else 1
        transaction.set(counter_ref, {"next_id": current + 1})
        return current

    return _increment(client.transaction())


class FirestoreQuery:
    def __init__(self, session: "FirestoreSession", model: type[FirestoreModel]):
        self._session = session
        self._model = model
        self._filters: list[tuple[str, str, object]] = []
        self._order: tuple[str, str] | None = None
        self._limit: int | None = None

    def filter_by(self, **kwargs) -> "FirestoreQuery":
        for k, v in kwargs.items():
            self._filters.append((k, "==", v))
        return self

    def filter(self, *conditions) -> "FirestoreQuery":
        for cond in conditions:
            if isinstance(cond, _In):
                self._filters.append((cond.name, "in", cond.values))
            else:
                raise NotImplementedError(
                    f"FirestoreQuery.filter() only supports Column.in_(...) expressions, got {cond!r} "
                    "- if a new equality/other filter is needed, extend this method rather than "
                    "calling .filter() with something else."
                )
        return self

    def order_by(self, column) -> "FirestoreQuery":
        if isinstance(column, _Desc):
            self._order = (column.name, "desc")
        elif isinstance(column, _Asc):
            self._order = (column.name, "asc")
        elif isinstance(column, Column):
            self._order = (column.name, "asc")
        else:
            raise NotImplementedError(f"Unsupported order_by expression: {column!r}")
        return self

    def limit(self, n: int) -> "FirestoreQuery":
        self._limit = n
        return self

    def all(self) -> list[FirestoreModel]:
        return self._session._fetch(self._model, self._filters, self._order, self._limit)

    def first(self) -> FirestoreModel | None:
        results = self._session._fetch(self._model, self._filters, self._order, self._limit or 1)
        return results[0] if results else None

    def one_or_none(self) -> FirestoreModel | None:
        results = self._session._fetch(self._model, self._filters, self._order, self._limit)
        if not results:
            return None
        if len(results) > 1:
            raise ValueError(f"one_or_none() found {len(results)} {self._model.__collection__} rows, expected at most 1")
        return results[0]

    def count(self) -> int:
        return len(self._session._fetch(self._model, self._filters, self._order, self._limit))


class FirestoreSession:
    """Mimics just enough of sqlalchemy.orm.Session for this codebase.
    add()/flush()/commit() all write immediately - Firestore has no
    multi-statement transaction spanning a whole request the way this app
    uses the SQLAlchemy Session, but each individual document write is
    already atomic on its own, which is enough at this app's data volume and
    stakes (a paper-trading demo, not a system moving real money)."""

    def __init__(self) -> None:
        self._client = get_client()

    def _collection(self, model: type[FirestoreModel]):
        return self._client.collection(model.__collection__)

    def query(self, model: type[FirestoreModel]) -> FirestoreQuery:
        return FirestoreQuery(self, model)

    def get(self, model: type[FirestoreModel], id_: int) -> FirestoreModel | None:
        if id_ is None:
            return None
        snap = self._collection(model).document(str(id_)).get()
        if not snap.exists:
            return None
        return model._from_doc(snap.id, snap.to_dict())

    def add(self, obj: FirestoreModel) -> None:
        self._write(obj)

    def flush(self) -> None:
        pass  # add() already writes immediately - nothing pending to flush

    def commit(self) -> None:
        pass  # ditto

    def refresh(self, obj: FirestoreModel) -> None:
        fresh = self.get(type(obj), obj.id)
        if fresh is not None:
            for name in _columns(type(obj)):
                obj.__dict__[name] = fresh.__dict__.get(name)

    def close(self) -> None:
        pass

    def _write(self, obj: FirestoreModel) -> None:
        if obj.__dict__.get("id") is None:
            obj.__dict__["id"] = _next_id(obj.__collection__)
        self._collection(type(obj)).document(str(obj.id)).set(obj._to_doc())

    def _fetch(self, model, filters, order, limit) -> list[FirestoreModel]:
        query = self._collection(model)
        for field, op, value in filters:
            query = query.where(field, op, value)
        if order:
            from google.cloud import firestore

            field, direction = order
            fs_dir = firestore.Query.DESCENDING if direction == "desc" else firestore.Query.ASCENDING
            query = query.order_by(field, direction=fs_dir)
        if limit is not None:
            query = query.limit(limit)
        return [model._from_doc(doc.id, doc.to_dict()) for doc in query.stream()]


def get_session_for_relationship() -> FirestoreSession:
    """Used only by the two lazy relationship descriptors in
    models_firestore.py (Decision.trades, Trade.position) - a fresh
    lightweight session is fine for these simple read-only lookups, they
    don't need to share a transaction with whatever wrote the parent object."""
    return FirestoreSession()
