"""Desired operation survives recoverable faults, but never a manual stop."""

from dataclasses import dataclass

from .const import DECISION_MAX_AGE, FAULT_RETRY_SECONDS


@dataclass
class Recovery:
    requested: bool = False
    pending: bool = False
    restore_pending: bool = False
    ready_after: float = 0
    first_good: float = 0
    last_good: float = 0
    good_count: int = 0
    verified: tuple | None = None

    def request(self, enabled, now):
        self.requested = enabled
        self.pending = enabled
        self.restore_pending = True
        self.ready_after = now
        self.reset_good()
        self.verified = None

    def fault(self, now, control=False):
        self.pending = self.requested
        self.restore_pending = True
        if control:
            self.ready_after = max(self.ready_after, now + FAULT_RETRY_SECONDS)
        self.reset_good()
        self.verified = None

    def reset_good(self):
        self.first_good = self.last_good = 0
        self.good_count = 0

    def good(self, now):
        if not self.good_count or now - self.last_good >= 120:
            self.first_good, self.good_count = now, 0
        self.good_count += 1
        self.last_good = now

    def can_resume(self, now, decision):
        return bool(
            self.requested
            and self.pending
            and not self.restore_pending
            and now >= self.ready_after
            and self.good_count >= 3
            and now - self.first_good >= 60
            and now - self.last_good < 90
            and decision
            and 0 <= now - decision.received_at < DECISION_MAX_AGE
        )
