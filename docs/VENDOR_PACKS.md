# Vendor packs — installing & adding modules

Argus discovery is a **host/plugin** layer ([ADR-0005](architecture/adr/0005-vendor-packs.md)).
A *vendor pack* adds support for a vendor/technology — a read-only collector plus declarative
metadata — and attaches to Argus **without modifying it**. This guide covers installing packs
and writing your own.

## How packs are discovered

- **Built-in packs** ship in this repo (currently **UniFi** and **pfSense/OPNsense**).
- **External packs** come from any installed distribution that advertises an
  `argus.vendor_packs` entry point. Install the distribution into the **same environment as
  `argus-netbox`** and it auto-registers — public or private, with no change to Argus.

Check what's registered at any time:

```bash
python -c "from argus.discovery.vendors import discover_packs; print(sorted(discover_packs()))"
# e.g. ['pfsense', 'unifi']  →  ['aruba_central', 'mist', 'pfsense', 'unifi'] once external packs are installed
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

## Paired knowledge packs (Argus ↔ Mnemosyne)

A vendor pack can declare an optional `knowledge_pack` field linking to a **Mnemosyne knowledge
pack** that explains how to operate the vendor's technology ([ADR-0013](architecture/adr/0013-paired-vendor-knowledge-packs.md)).
This creates a two-faced integration: **Argus discovers the devices**; **Mnemosyne explains how
they work**. The two remain independently deployable (Argus carries no RAG dependencies) but
are wired at runtime by the dashboard's "Ask the Brain" panel.

### For vendor pack authors

When you ship a pack with a `knowledge_pack` name, declare it in your `VendorPack` descriptor:

```python
EXAMPLE_PACK = VendorPack(
    name=ExampleCollector.name,
    manufacturer=MANUFACTURER,
    transport=Transport.CONTROLLER_API,
    capabilities=frozenset({DEVICES}),
    config_vars=CONFIG_VARS,
    collector=ExampleCollector,
    knowledge_pack="example_vendor",  # Mnemosyne pack name (ADR-0013)
)
```

The dashboard reads this field and queries the matching Mnemosyne pack automatically — no
hardcoded defaults. If `knowledge_pack=None` (the default), the "Ask the Brain" panel either
falls back to a default or disables that vendor's knowledge face.

### Reference examples

**UniFi** (in-tree):
- Argus vendor pack: `discovery/vendors/unifi/`, declares `knowledge_pack="ubiquiti"`
- Mnemosyne knowledge pack: `src/mnemosyne/packs/ubiquiti/`, contains UniFi documentation

**pfSense/OPNsense** (in-tree):
- Argus vendor pack: `discovery/vendors/firewall/` (collector `firewall`, alias `pfsense`), declares `knowledge_pack="firewall"`
- Mnemosyne knowledge pack: (to be created) with firewall operations, rules, best practices

### Creating a knowledge pack for your vendor

Create a new directory under `mnemosyne/src/mnemosyne/packs/<your_pack_name>/` with:

1. **manifest.yaml** — declarative config:
   ```yaml
   name: your_pack_name           # Must match knowledge_pack value in Argus VendorPack
   title: Your Vendor Expert
   description: >
     An expert on Your Vendor's technology — operations, configuration, troubleshooting.
   
   # Models (optional; falls back to global defaults if not set)
   embedding_model: bge-m3
   chat_model: qwen2.5:1.5b
   
   # Chunking strategy for this domain
   chunk_size: 500
   chunk_overlap: 150
   
   # Retrieval
   top_k: 5
   
   # The expert's persona
   system_prompt: >
     You are a vendor expert helping engineers operate and troubleshoot systems.
     Answer using ONLY the provided context. Cite sources inline as [n].
     If the context does not contain the answer, say so plainly.
   ```

2. **sources/** directory with curated knowledge:
   - Local files: Markdown, PDF, plaintext documents dropped directly
   - Remote URLs: Listed in `sources/sources.yaml` for the pipeline to fetch (see Mnemosyne
     docs on source loading)

3. **Optional pack.py** — a custom `KnowledgePack` subclass if you need to override
   document loading or post-processing (see the Ubiquiti pack's title cleanup for an example).

For distribution, a **single installation** can ship both the Argus and Mnemosyne faces via
a distribution with two entry points:

```toml
[project.entry-points."argus.vendor_packs"]
your_vendor = "your_vendor_pack:YOUR_PACK"

[project.entry-points."mnemosyne.knowledge_packs"]
your_vendor = "your_vendor_knowledge:YOUR_KNOWLEDGE_PACK"
```

This way, `pip install your-vendor-pack` installs the discovery integration into Argus
and the knowledge pack into Mnemosyne simultaneously, both in separate service environments.

## Public or private

A pack can live in its own repo at any visibility. **Private** packs depend only on the public
`argus-netbox` SPI and install into your deployment from a private index or `git+ssh`; Argus's
Apache-2.0 license permits closed-source plugins. Keep competitively-sensitive integrations in
a private pack repo — Argus itself stays vendor-neutral.

See [ARCHITECTURE.md](ARCHITECTURE.md) for where discovery fits and
[ADR-0005](architecture/adr/0005-vendor-packs.md) for the design rationale.
