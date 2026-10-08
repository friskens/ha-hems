"""Desired operation and adapter outcome; no hardware recovery policy."""

from dataclasses import dataclass


@dataclass
class Recovery:
    requested: bool = False
    verified: tuple | None = None
    failed: tuple | None = None
    failed_status: str | None = None
    failed_error: str | None = None

    def request(self, enabled, now):
        self.requested = enabled
        self.verified = None
        self.failed = None
        self.failed_status = None
        self.failed_error = None
