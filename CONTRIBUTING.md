# Contributing

Open an issue describing the intended behavior and reproducible failure. Include HA/integration versions and sanitised diagnostics; never post API keys, raw private payloads or household addresses.

Keep protocol, observations, recovery and hardware adapters separate. Add tests that reproduce failures, especially stale data, sign mistakes, repeated commands and restart/cancellation. Device adapters must document independent readback and supported actions. Do not add SOC-limit writes, private integration imports or periodic redundant actuator verification without an explicit design discussion.

Install `requirements-dev.txt`, run `python -m pytest -q` and `python -m ruff check custom_components tests`. Core tests use fake HA services; report live device tests separately. Changes are reviewed through pull requests. Contributions are licensed under MIT.
