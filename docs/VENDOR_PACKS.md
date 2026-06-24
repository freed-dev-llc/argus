# Vendor packs — installing & adding modules

Argus discovery is a **host/plugin** layer ([ADR-0005](architecture/adr/0005-vendor-packs.md)).
A *vendor pack* adds support for a vendor/technology — a read-only collector plus declarative
metadata — and attaches to Argus **without modifying it**. This guide covers installing packs
and writing your own.

## How packs are discovered

- **Built-in packs** ship in this repo (currently **UniFi**).
- **External packs** come from any installed distribution that advertises an
  `argus.vendor_packs` entry point. Install the distribution into the **same environment as
  `argus-netbox`** and it auto-registers — public or private, with no change to Argus.

Check what's registered at any time:

```bash
python -c "from argus.discovery.vendors import discover_packs; print(sorted(discover_packs()))"
# e.g. ['unifi']  →  ['aruba_central', 'mist', 'unifi'] once external packs are installed
```

## Install a pack

From PyPI or a private index:

```bash
pip install <pack-distribution>
```

From a local checkout (development) — an editable ("linked") install:

```bash
pip install -e /path/to/your-pack          # into the same env as the Argus server
```

Install it into whatever environment runs the Argus server — the editable `argus-netbox`
dev env, a venv, or the server image in your deployment. Once installed, the pack's `name`
is selectable everywhere a collector is: the `discovery_scan` / `network_topology` /
reconcile tools, `SCHEDULE_COLLECTOR`, and the dashboard.

## Add your own pack

Start from the public template — a GitHub **"Use this template"** repo:
**<https://github.com/freed-dev-llc/argus-vendor-pack-template>**

A pack is one Python package with:

- `collector.py` — a `Collector` subclass whose `collect()` observes live state (read-only)
  and returns a normalized `DiscoveryResult`.
- `models.py` — manufacturer + model→role normalization.
- `__init__.py` — a `VendorPack(...)` instance bundling the collector + metadata
  (`manufacturer`, `transport`, `capabilities`, `config_vars`).
- `pyproject.toml` — the entry point that registers it:

  ```toml
  [project.entry-points."argus.vendor_packs"]
  yourvendor = "your_package:YOUR_PACK"
  ```

Implement → `pip install -e .` → verify with `discover_packs()` → iterate. The public SPI you
build against ships in `argus-netbox`: `argus.discovery.base` (`Collector`, `DiscoveryResult`,
`Discovered*`) and `argus.discovery.vendors.pack` (`VendorPack`, `Transport`, capability
constants).

## Practices & management (optional)

A pack can do more than discover devices:

- **Practices** ([ADR-0009](architecture/adr/0009-vendor-pack-practices-spi.md)) — ship
  best-practice / validation rules on `VendorPack.practices`. A `Practice` (in
  `argus.discovery.practices`) is a small, self-describing rule
  (`id` / `title` / `severity` / `evaluate`) that inspects a `PracticeContext` — the live
  observation **and** a read-only NetBox snapshot — and returns advisory `Finding`s. Run them
  with the `evaluate_practices` tool. Practices never write; reconcile stays the only writer.
- **Management-plane data** ([ADR-0010](architecture/adr/0010-management-plane-contract.md)) —
  populate the optional `DiscoveredDevice.management` (`DeviceManagement`: status, serial,
  firmware, mgmt IP / interface / VLAN). Surfaced by discovery today (read-only); NetBox
  write-back is the gated follow-up.

The in-tree UniFi pack is the worked example for both.

## Public or private

A pack can live in its own repo at any visibility. **Private** packs depend only on the public
`argus-netbox` SPI and install into your deployment from a private index or `git+ssh`; Argus's
Apache-2.0 license permits closed-source plugins. Keep competitively-sensitive integrations in
a private pack repo — Argus itself stays vendor-neutral.

See [ARCHITECTURE.md](ARCHITECTURE.md) for where discovery fits and
[ADR-0005](architecture/adr/0005-vendor-packs.md) for the design rationale.
