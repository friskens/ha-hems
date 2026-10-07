"""Desired operation and adapter outcome; no hardware recovery policy."""

from dataclasses import dataclass


@dataclass
class Recovery:
    requested: bool = False
    verified: tuple | None = None
    failed: tuple | None = None

    def request(self, enabled, now):
        self.requested = enabled
        self.verified = None
        self.failed = None
