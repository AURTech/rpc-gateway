from dataclasses import dataclass


@dataclass(slots=True, kw_only=True)
class _RetryNode[Key]:
    key: Key
    deadline: float


class RetryHeap[Key]:
    """Bounded indexed min-heap with at most one deadline per key."""

    def __init__(self, max_items: int) -> None:
        self._max_items = max_items
        self._nodes: list[_RetryNode[Key]] = []
        self._positions: dict[Key, int] = {}

    def __bool__(self) -> bool:
        return bool(self._nodes)

    def __contains__(self, key: Key) -> bool:
        return key in self._positions

    def put(self, key: Key, deadline: float) -> bool:
        """Insert or replace a deadline and report whether the earliest deadline moved forward."""
        earliest = self.next_deadline()
        position = self._positions.get(key)
        if position is None:
            if len(self._nodes) >= self._max_items:
                raise RuntimeError('Tip retry heap reached its item limit.')
            self._positions[key] = len(self._nodes)
            self._nodes.append(_RetryNode(key=key, deadline=deadline))
            self._sift_up(len(self._nodes) - 1)
            return earliest is None or deadline < earliest

        previous = self._nodes[position].deadline
        self._nodes[position].deadline = deadline
        if deadline < previous:
            self._sift_up(position)
        elif deadline > previous:
            self._sift_down(position)
        latest_earliest = self.next_deadline()
        return earliest is None or (latest_earliest is not None and latest_earliest < earliest)

    def next_deadline(self) -> float | None:
        if not self._nodes:
            return None
        return self._nodes[0].deadline

    def pop(self) -> Key | None:
        if not self._nodes:
            return None
        root = self._nodes[0]
        last = self._nodes.pop()
        del self._positions[root.key]
        if self._nodes:
            self._nodes[0] = last
            self._positions[last.key] = 0
            self._sift_down(0)
        return root.key

    def drain(self) -> list[Key]:
        keys = [node.key for node in self._nodes]
        self.clear()
        return keys

    def clear(self) -> None:
        self._nodes.clear()
        self._positions.clear()

    def _sift_up(self, position: int) -> None:
        while position > 0:
            parent = (position - 1) // 2
            if self._nodes[parent].deadline <= self._nodes[position].deadline:
                return
            self._swap(parent, position)
            position = parent

    def _sift_down(self, position: int) -> None:
        size = len(self._nodes)
        while True:
            left = position * 2 + 1
            if left >= size:
                return
            right = left + 1
            smallest = left
            if right < size and self._nodes[right].deadline < self._nodes[left].deadline:
                smallest = right
            if self._nodes[position].deadline <= self._nodes[smallest].deadline:
                return
            self._swap(position, smallest)
            position = smallest

    def _swap(self, left: int, right: int) -> None:
        self._nodes[left], self._nodes[right] = self._nodes[right], self._nodes[left]
        self._positions[self._nodes[left].key] = left
        self._positions[self._nodes[right].key] = right
