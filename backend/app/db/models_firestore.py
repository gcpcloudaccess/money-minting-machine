"""Firestore-backed model layer - an alternate backend to
app/db/models_sqlalchemy.py, active when Settings.use_firestore is True (see
app/config.py). Deliberately narrow: it exposes exactly the class-level query
syntax this codebase's 12 call sites actually use (Model.col.desc(),
Model.col.in_([...]), filter_by(**kwargs), order_by, limit,
first/all/one_or_none, add/flush/commit/refresh/get) - confirmed by grepping
every db.query()/db.add() call in the app before writing this - not a
general-purpose ORM. See app/db/firestore_session.py for the
FirestoreSession/FirestoreQuery that interprets these against real Firestore
collections.

Why this exists at all: Cloud Run's local container disk (where the default
SQLite file lives) is ephemeral - it's wiped on every scale-to-zero restart
or redeploy. Firestore is real persistence with a free tier that comfortably
covers this app's write volume (a decision every few minutes, nowhere near
Firestore's free 20K writes/day)."""

from __future__ import annotations

import datetime as dt


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class _Desc:
    """Model.col.desc() - marks a field for descending order_by()."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name


class _Asc:
    """Model.col.asc() - marks a field for ascending order_by() (rarely used
    explicitly since ascending is the default, but SQLAlchemy exposes it too)."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name


class _In:
    """Model.col.in_([...]) - the one non-equality filter this codebase uses
    (Decision.id.in_(...), Decision.symbol.in_(...))."""

    __slots__ = ("name", "values")

    def __init__(self, name: str, values) -> None:
        self.name = name
        self.values = list(values)


class Column:
    """Class-level descriptor: accessing Model.col (no instance) returns this
    descriptor itself, so Model.col.desc()/.asc()/.in_(...) work exactly like
    a SQLAlchemy InstrumentedAttribute. Accessing instance.col returns the
    plain stored value. This dual behavior is what lets every consumer file's
    existing query code (main.py, execution_engine.py, etc.) run completely
    unchanged against either backend."""

    def __init__(self, default=None, default_factory=None):
        self.default = default
        self.default_factory = default_factory
        self.name: str | None = None

    def __set_name__(self, owner, name) -> None:
        self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return obj.__dict__.get(self.name, self._make_default())

    def __set__(self, obj, value) -> None:
        obj.__dict__[self.name] = value

    def _make_default(self):
        if self.default_factory is not None:
            return self.default_factory()
        return self.default

    def desc(self) -> _Desc:
        return _Desc(self.name)

    def asc(self) -> _Asc:
        return _Asc(self.name)

    def in_(self, values) -> _In:
        return _In(self.name, values)


class Relationship:
    """Lazy one-to-many / one-to-one traversal, resolved via a live Firestore
    query the moment it's accessed on an instance - only implements the two
    relationship traversals this codebase actually performs at runtime
    (Decision.trades in memory/retrieval.py, Trade.position in the same
    file); every other relationship SQLAlchemy defines on the sibling models
    (Portfolio.positions, Trade.portfolio, etc.) is declared there but never
    actually traversed by attribute access anywhere in the app - everything
    else queries by foreign key explicitly instead, so nothing more is
    needed here. `target` is a zero-arg callable returning the target class,
    not the class itself, to avoid needing forward references/import order
    tricks between models defined in the same module."""

    def __init__(self, target, fk_field: str, many: bool):
        self.target = target
        self.fk_field = fk_field
        self.many = many

    def __set_name__(self, owner, name) -> None:
        self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        from app.db.firestore_session import get_session_for_relationship

        db = get_session_for_relationship()
        target_cls = self.target()
        if self.many:
            return db.query(target_cls).filter_by(**{self.fk_field: obj.id}).all()
        fk_value = obj.__dict__.get(self.fk_field)
        if fk_value is None:
            return None
        return db.get(target_cls, fk_value)


def _columns(cls) -> dict[str, Column]:
    cols: dict[str, Column] = {}
    for klass in reversed(cls.__mro__):
        for name, val in vars(klass).items():
            if isinstance(val, Column):
                cols[name] = val
    return cols


class FirestoreModel:
    """Base for every Firestore-backed model. Subclasses set __collection__
    and declare fields as Column(...) class attributes - see the models
    below. `id` is kept as a Python int (not Firestore's native string
    document id) so API responses/paths that already assume integer ids
    (e.g. GET /decisions/{decision_id}: int) don't need to change - the int
    is just stored as the string document id under the hood
    (db/firestore_session.py's _next_id() allocates it)."""

    __collection__: str = ""

    id: int | None = Column(default=None)

    def __init__(self, **kwargs) -> None:
        cols = _columns(type(self))
        for name, col in cols.items():
            self.__dict__[name] = kwargs.get(name, col._make_default())
        # tolerate any field not declared as a Column, same forgiving spirit
        # as the plain constructor calls elsewhere in this codebase.
        for k, v in kwargs.items():
            if k not in cols:
                self.__dict__[k] = v

    def _to_doc(self) -> dict:
        # "id" IS the Firestore document key (see FirestoreSession._write), but
        # it's also duplicated into the document body here - otherwise a query
        # that filters on id (e.g. main.py's Decision.id.in_(decision_ids)) has
        # nothing to match against, since Firestore's .where() can't filter on
        # a document's own key without the more involved FieldPath.document_id()
        # API, which this narrow shim doesn't implement.
        return {name: getattr(self, name) for name in _columns(type(self))}

    @classmethod
    def _from_doc(cls, doc_id: str, data: dict) -> "FirestoreModel":
        obj = cls.__new__(cls)
        for name in _columns(cls):
            obj.__dict__[name] = data.get(name)
        obj.__dict__["id"] = int(doc_id)
        return obj


class Portfolio(FirestoreModel):
    __collection__ = "portfolios"

    cash_inr = Column()
    starting_capital = Column()
    leverage = Column()
    status = Column(default="active")  # active | closed
    exchange = Column(default="NSE")
    session_start = Column(default_factory=utcnow)
    session_end = Column(default=None)
    created_at = Column(default_factory=utcnow)


class Position(FirestoreModel):
    __collection__ = "positions"

    portfolio_id = Column()
    symbol = Column()
    side = Column()  # LONG | SHORT
    quantity = Column()
    avg_price = Column()
    status = Column(default="open")  # open | closed
    opened_at = Column(default_factory=utcnow)
    closed_at = Column(default=None)
    exit_price = Column(default=None)
    realized_pnl = Column(default=None)
    exchange = Column(default="NSE")
    currency = Column(default="INR")
    fx_rate_to_inr = Column(default=1.0)
    stop_loss = Column(default=None)
    target_price = Column(default=None)


class Trade(FirestoreModel):
    __collection__ = "trades"

    portfolio_id = Column()
    decision_id = Column(default=None)
    position_id = Column(default=None)
    symbol = Column()
    action = Column()  # BUY | SELL
    quantity = Column()
    price = Column()
    gross_value = Column()
    total_costs = Column()
    cost_breakdown_json = Column(default_factory=dict)
    net_cash_impact = Column()
    timestamp = Column(default_factory=utcnow)
    exchange = Column(default="NSE")
    currency = Column(default="INR")
    price_local = Column(default=0.0)
    fx_rate_to_inr = Column(default=1.0)

    position = Relationship(lambda: Position, "position_id", many=False)


class Decision(FirestoreModel):
    __collection__ = "decisions"

    symbol = Column()
    timestamp = Column(default_factory=utcnow)
    verdict = Column()  # BUY | SELL | HOLD | WAIT | SWITCH
    directional_confidence = Column()
    consensus_reasoning = Column()
    evidence_json = Column(default_factory=dict)
    alternatives_json = Column(default_factory=dict)
    critic_feedback_json = Column(default_factory=dict)
    expected_risk_return_json = Column(default_factory=dict)
    executed = Column(default=False)

    trades = Relationship(lambda: Trade, "decision_id", many=True)


class AgentVote(FirestoreModel):
    __collection__ = "agent_votes"

    decision_id = Column()
    agent_name = Column()
    agent_type = Column()  # analyst | critic
    action = Column()
    confidence = Column()
    reasoning = Column()
    evidence_json = Column(default_factory=dict)
    weight_used = Column(default=0.0)


class AgentReliability(FirestoreModel):
    __collection__ = "agent_reliability"

    agent_name = Column()
    success_count = Column(default=1.0)  # Beta prior alpha
    fail_count = Column(default=1.0)  # Beta prior beta
    trust_score = Column(default=0.6)
    last_updated = Column(default_factory=utcnow)


class ResearchNote(FirestoreModel):
    __collection__ = "research_notes"

    symbol = Column()
    timestamp = Column(default_factory=utcnow)
    category = Column()  # news | policy | technical | fundamental ...
    content = Column()
    tags = Column(default="")


class AuditLog(FirestoreModel):
    __collection__ = "audit_log"

    timestamp = Column(default_factory=utcnow)
    event_type = Column()
    payload_json = Column(default_factory=dict)


class PositionalPick(FirestoreModel):
    __collection__ = "positional_picks"

    scan_id = Column()
    symbol = Column()
    timestamp = Column(default_factory=utcnow)
    direction = Column()  # BUY | SELL | HOLD | WAIT
    directional_confidence = Column()
    rank_score = Column()
    structure_type = Column(default=None)
    structure_json = Column(default_factory=dict)
    iv_rank = Column(default=None)
    days_to_next_catalyst = Column(default=None)
    next_catalyst_label = Column(default=None)
    consensus_reasoning = Column()
    agent_details_json = Column(default_factory=dict)
