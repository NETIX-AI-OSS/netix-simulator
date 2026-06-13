# NETIX Simulator

One binary that serves a single config-driven device simulation over **any**
registered industrial protocol — **BACnet/IP, Modbus TCP, OPC UA** — selected in
config. Interactive ratatui TUI plus a headless mode.

The protocol adapters and simulation engine live in
[`netix-protocol-core`](https://github.com/NETIX-AI-OSS/netix-protocol-core) and
are consumed here as git dependencies (the exact commit is pinned in
`Cargo.lock`). Adding a protocol is a change in that repo, not this one.

## Build & run

```bash
cargo build --release
./target/release/simulator                 # TUI; writes a sample config.yaml on first run
./target/release/simulator --no-tui        # headless
```

## Config (`config.yaml`)

The same building simulation is served over the protocols you list:

```yaml
protocols:
  - { id: bacnet, port: 47808 }
  - { id: modbus, port: 502 }
  - { id: opcua,  port: 4840, options: { namespace: "urn:netix:simulator" } }
# ... building / seasonality / templates / instances (see the generated sample)
```

Omitting `protocols:` defaults to BACnet on 47808.

### Protocol notes

- **BACnet/IP** — Who-Is/I-Am discovery, object-list browse, ReadProperty(Multiple).
- **Modbus TCP** — register map derived from the simulation; per-point datatype
  (u16/i16/u32/i32/f32), word order, and scale.
- **OPC UA** — anonymous + None-security endpoint by default; one folder per
  device (variables nested inside). The node namespace is kept distinct from the
  application URI so value reads route correctly; set `options.host` to advertise
  a reachable address to external clients (e.g. UaExpert).

## Licensing

Apache-2.0 (see `LICENSE`). OPC UA support pulls in `async-opcua` (MPL-2.0); see
`NOTICE`.
