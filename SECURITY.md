# Security

Do not put credentials or raw private request/response bodies in public issues. For a suspected vulnerability, use GitHub's private vulnerability reporting if enabled, or contact the maintainer privately before publishing exploit details.

The API key is stored in Home Assistant's config entry, sent in `X-Api-Key` over validated HTTPS, and excluded from diagnostics. Protect HA backups as credentials may be present there. Redirects are rejected. Responses are limited to 64 KiB and errors use stable codes rather than raw server bodies.

Device scripts execute with HA's privileges and are trusted code. A forged verification receipt cannot prove real hardware state. Keep the adapter and the HA installation under your control, and avoid multiple simultaneous battery writers.
