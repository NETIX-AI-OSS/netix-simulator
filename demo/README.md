# NETIX demo tenant (org 9999) — simulator + republisher

This directory drives the demo tenant's **live** telemetry with the OSS
`netix-simulator` + `netix-republisher` combo, replacing the platform
`simulator-service`. Values land on the seeded demo **asset tags**, so the viz
Systems dashboards show live data.

## Pipeline

```
netix-simulator  --(BACnet)-->  netix-republisher  --(MQTT)-->  platform broker
   headless,                       netix_envelope,                /Netix/Sim/Device/#
   config.yaml                     config.toml
        |                               |
        └─ 29 templates,                └─ one envelope per device:
           95 devices,                     {"reason","time","id":"<tag_identifier>",
           258 points                       "points":[{"pointName":"<role>","data",...}]}
                                                     |
   stormbreaker simulated-data-9999 worker  <────────┘
     parser: tag_name = "<id>/<pointName>" = "<tag_identifier>/<role>"
        |
        └─ Kafka stormbreaker_nc9999 → data-service historian _nc9999
               → viz asset-tag card view (asset_id → tag_ids → latest) → dashboards
```

The demo contract is `demo_spec.json` (vendored from the backend). Each equipment
has a `tag_identifier` and a set of Haystack point `roles`; tag-service seeds one
historised tag `<tag_identifier>/<role>` per point, linked to the asset. The
republisher publishes `id = <tag_identifier>` / `pointName = <role>`, so the
worker writes exactly that tag name (the platform Device/Point separator the viz
frontend splits on) — the one the dashboards read.

## Files

| File | What it is |
|------|------------|
| `demo_spec.json` | Cross-service id contract (vendored, do not edit here). |
| `gen_demo.py` | Generates `config.yaml` from `demo_spec.json`. |
| `config.yaml` | Simulator model: 29 templates (one per asset class), 95 instances (one per equipment, `name_prefix` = `tag_identifier`), 258 BACnet points. |
| `republisher-config.toml` | Republisher config emitted by the simulator (envelope mode, autostart, every point addressed). Broker host is a placeholder — set it per deployment. |

Regenerate after any `demo_spec.json` change:

```bash
python3 demo/gen_demo.py                                   # -> demo/config.yaml
REPUBLISHER_MQTT_HOST=<broker-host> \
  cargo run --release -- --config demo/config.yaml \
    --emit-republisher-config demo/republisher-config.toml # -> demo/republisher-config.toml
```

## Deploy on the edge box (Windows VM)

1. **Build/download** the tagged release binaries (`simulator.exe`,
   `republisher.exe`). The `v*` tag triggers `release-build.yml`.

2. **Run the simulator headless** (serves BACnet on 47808):
   ```
   simulator.exe --no-tui --config config.yaml
   ```

3. **Configure the republisher.** Copy `republisher-config.toml` to the OS config
   dir (`%APPDATA%\netix\republisher\config\config.toml`) and set:
   - `[mqtt] host` → the **external** platform MQTT ingress reachable from the VM
     (the seeded worker default `mqtt.platform` is a cluster-internal DNS name and
     is **not** reachable from an edge box — use the LB/ingress address).
   - TLS / `username` / `password` / cert paths per the cluster's broker.
   - `payload_format = "netix_envelope"`, `device_topic_prefix = "/Netix/Sim/Device"`,
     and `autostart = true` are already set by the emitter.

4. **Run the republisher.** With `autostart = true` it begins publishing on launch
   (no manual "Start" click). Add it to Windows startup so it survives reboots.
   The simulator and republisher discover each other over BACnet on the LAN; if
   Who-Is discovery fails, set `[connections.bacnet] broadcast_address` to the
   local subnet broadcast.

## Platform side (once, per cluster)

The stormbreaker worker + tag pre-link are seeded by:

```bash
python manage.py seed_demo_worker            # after seed_demo_tenant
```

This creates the `simulated-data-9999` worker (MQTT `/Netix/Sim/Device/#` → Kafka
`stormbreaker_nc9999`), installs the `<id>/<pointName>` parser, and **pre-links** a
`Timeseries` per demo tag (via `bulk_create`, so no `post_save` upsert clobbers the
seeded tag's curated metadata). Run it after the tag-service demo seed so the tags
exist to link; re-run after adding tags.

Once verified, retire the `simulator-service` demo publisher so the edge combo is
the single telemetry source for org 9999.
