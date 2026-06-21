# Argus vendor pack template

A minimal, copy-to-start **out-of-tree vendor pack** for Argus. Use it to add support for a
vendor/technology without modifying Argus itself — in your own repo, **public or private**
(see [ADR-0005](../../docs/architecture/adr/0005-vendor-packs.md)).

This is exactly how Argus's own UniFi pack is structured, and how private (e.g.
MSP-supported) vendor packs attach: Argus is the **host**, your pack is a **plugin**
discovered via the `argus.vendor_packs` entry point. Argus never needs to know your pack
exists at build time.

## What a pack is

A `VendorPack` bundles, for one vendor:

- a **`Collector`** — the read-only adapter that observes live state and returns a
  normalized `DiscoveryResult` (devices / clients / links);
- **metadata** — `manufacturer`, `transport`, `capabilities`, and the `config_vars` it
  consumes;
- **model normalization** — vendor model strings → NetBox role / manufacturer.

The public SPI it builds against ships in the `argus-netbox` distribution:
`argus.discovery.base` (`Collector`, `DiscoveryResult`, `Discovered*`) and
`argus.discovery.vendors.pack` (`VendorPack`, `Transport`, capability constants).

## Use it

1. **Copy** this directory into your repo and rename `argus_vendor_example` → your vendor.
2. **Implement** `Collector.collect()` in `collector.py` against your vendor's API/protocol
   (keep it read-only), and fill in `models.py`.
3. **Describe** the pack in `__init__.py` (`VendorPack(...)`).
4. **Register** it via the entry point in `pyproject.toml`:

   ```toml
   [project.entry-points."argus.vendor_packs"]
   yourvendor = "your_package:YOUR_PACK"
   ```

5. **Install** it alongside Argus and confirm it registers:

   ```bash
   pip install -e .
   python -c "from argus.discovery.vendors import discover_packs; print(sorted(discover_packs()))"
   # -> [..., 'example', 'unifi']
   ```

Once registered, your pack's `name` is selectable everywhere a collector is (the
`discovery_scan` / `network_topology` / reconcile tools, `SCHEDULE_COLLECTOR`, etc.).

## Private packs

Nothing here has to be public. A private pack lives in a private repo, depends on the
public `argus-netbox`, and is installed into your Argus deployment from a private index or
`git+ssh`. Apache-2.0 (Argus's license) is permissive — your pack's source stays closed.
