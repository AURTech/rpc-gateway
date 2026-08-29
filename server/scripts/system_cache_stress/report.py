from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class ScenarioReport:
    name: str
    elapsed_ms: int
    checks: dict[str, bool]
    counts: dict[str, int]

    def json_value(self) -> dict[str, object]:
        return {
            'name': self.name,
            'elapsed_ms': self.elapsed_ms,
            'checks': self.checks,
            'counts': self.counts,
            'success': all(self.checks.values()),
        }
