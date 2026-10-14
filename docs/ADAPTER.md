# Legacy 0.1 adapter reference

This document is retained only as a historical reference for HEMS Client 0.1.
It does **not** describe a supported configuration for 0.2.0a1 or later.

The 0.2 client is telemetry-only: it sends selected measurements to HEMS and
exposes the resulting decisions as Home Assistant entities. It never calls
scripts or services, writes device settings, or selects a safe hardware mode.

If a site needs to act on a HEMS decision, its owner creates and tests a local
Home Assistant automation, template, or blueprint. That local implementation
chooses the equipment entities, write order, readback checks, retries and its
own safety policy. The current decision schema is defined in the generated
[PROTOCOL.md](PROTOCOL.md).

Brand-specific automation examples may be added in the future, but they remain
user-owned examples rather than part of the HEMS Client runtime.
