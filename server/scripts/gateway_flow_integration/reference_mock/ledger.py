import asyncio
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from scripts.gateway_flow_integration.reference_mock.golden_ledger import (
    GoldenEntry,
    digest_bytes,
    digest_payload,
    make_golden_entry,
)
from scripts.gateway_flow_integration.reference_mock.model import ReferenceBehavior, ReferenceReply, RequestFacts


@dataclass(frozen=True, slots=True, kw_only=True)
class LedgerTicket:
    sequence: int
    started_at: float
    golden: GoldenEntry
    concurrency: int


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestEntry:
    sequence: int
    observed_at: str
    transport: str
    chain: str
    source: int
    host: str | None
    peer_host: str | None
    method: str
    behavior: str
    request_id: str | int | None
    head: int
    target_height: int
    params_digest: str
    status_code: int
    response_id: str | int | None
    payload_digest: str
    elapsed_ms: float
    concurrency: int
    semantic_match: bool
    fault_contract_match: bool


def _expects_semantic_match(behavior: ReferenceBehavior) -> bool:
    return behavior in {ReferenceBehavior.GOOD, ReferenceBehavior.TIMEOUT}


class RequestLedger:
    """Record actual traffic and an independently computed golden stream under one sequence."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._next_sequence = 1
        self._active = 0
        self._peak = 0
        self._requests: list[RequestEntry] = []
        self._golden: list[GoldenEntry] = []
        self._counters: Counter[str] = Counter()

    async def begin(self, facts: RequestFacts, behavior: ReferenceBehavior) -> LedgerTicket:
        async with self._lock:
            sequence = self._next_sequence
            self._next_sequence += 1
            self._active += 1
            self._peak = max(self._peak, self._active)
            concurrency = self._active
            self._counters[f'{facts.transport.value}:{behavior.value}:{facts.chain.value}:{facts.source}:{facts.method}'] += 1
        try:
            golden = make_golden_entry(sequence, facts)
        except Exception:
            async with self._lock:
                self._active = max(0, self._active - 1)
            raise
        return LedgerTicket(sequence=sequence, started_at=time.monotonic(), golden=golden, concurrency=concurrency)

    async def finish(
        self,
        ticket: LedgerTicket,
        facts: RequestFacts,
        behavior: ReferenceBehavior,
        reply: ReferenceReply,
    ) -> None:
        payload_digest = digest_payload(reply.payload) if reply.payload is not None else digest_bytes(reply.body)
        semantic_match = (
            reply.status_code == ticket.golden.status_code
            and reply.response_id == ticket.golden.response_id
            and payload_digest == ticket.golden.payload_digest
        )
        entry = RequestEntry(
            sequence=ticket.sequence,
            observed_at=datetime.now(UTC).isoformat(),
            transport=facts.transport.value,
            chain=facts.chain.value,
            source=facts.source,
            host=facts.host,
            peer_host=facts.peer_host,
            method=facts.method,
            behavior=behavior.value,
            request_id=facts.request_id,
            head=facts.head,
            target_height=facts.target_height,
            params_digest=digest_payload(facts.params),
            status_code=reply.status_code,
            response_id=reply.response_id,
            payload_digest=payload_digest,
            elapsed_ms=round((time.monotonic() - ticket.started_at) * 1000, 3),
            concurrency=ticket.concurrency,
            semantic_match=semantic_match,
            fault_contract_match=semantic_match is _expects_semantic_match(behavior),
        )
        async with self._lock:
            self._active = max(0, self._active - 1)
            self._golden.append(ticket.golden)
            self._requests.append(entry)

    async def report(self) -> dict[str, object]:
        async with self._lock:
            return {
                'requests': [asdict(entry) for entry in self._requests],
                'golden': [asdict(entry) for entry in self._golden],
                'counters': dict(self._counters),
                'active': self._active,
                'peak_concurrency': self._peak,
            }

    async def clear(self) -> None:
        async with self._lock:
            if self._active:
                raise RuntimeError('Reference ledger cannot be cleared while requests are active.')
            self._requests.clear()
            self._golden.clear()
            self._counters.clear()
            self._peak = 0
