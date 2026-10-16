# Fronius GEN24 — historical reference

This is background from an original GEN24 installation, not a bundled driver
or copy-paste controller. HEMS Client 0.2.0a1 is device-neutral and does not
call a Fronius integration, Modbus, scripts, services or any other equipment
interface.

Use it only when designing a **local, user-owned** Home Assistant automation
for a verified GEN24 installation. That automation may read the HEMS Client
decision and freshness entities, then map them to the site's own entities and
safety policy. It must not assume that another GEN24 model, firmware, battery,
metering arrangement or site has the same settings.

## Useful observations from the original installation

- Mode changes could reset limit registers. Confirm the required write order
  and independently read back the resulting settings.
- API and storage-control ownership can interact. A tested export path used
  **Target Feed In** with **Discharge to Grid**; a discharge slider alone did
  not establish the intended net export.
- Transitions between API and Modbus ownership could temporarily disrupt
  communication. A local automation needs its own timing, error handling and
  safe-default policy.
- A raw rate scale of `-2` represented 100% as 10,000 on one observed system.
  Verify model-specific scale factors and signed encodings before using them.
- Zero export and peak shaving need a suitable local measurement/control loop;
  neither can be inferred from a battery-mode label.

The canonical, device-neutral decision fields are generated in
[PROTOCOL.md](PROTOCOL.md). Future Fronius blueprints may build on those fields,
but must remain optional local automation examples.
