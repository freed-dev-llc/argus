# Knowledge Pack Integration — Linking Argus Discovery to Mnemosyne RAG

This guide explains how to create a **Mnemosyne knowledge pack** paired with an **Argus vendor pack**,
enabling end-to-end discovery and explanation of network devices ([ADR-0013](architecture/adr/0013-paired-vendor-knowledge-packs.md)).

## Overview

The integration is **data-driven**: when Argus discovers a device from a vendor pack, the pack
declares a `knowledge_pack` field naming a Mnemosyne expert. The dashboard's "Ask the Brain" panel
reads this field and queries the matching knowledge pack — so as new vendors are added, the system
automatically connects to the right expert, with no hardcoded defaults.

```
┌─────────────────────┐
│ Argus Discovery     │
│ (device discovery)  │
└──────────┬──────────┘
           │ VendorPack.knowledge_pack = "firewall"
           │ (metadata in /api/collectors)
           │
      ┌────▼─────────────────────────┐
      │ Dashboard "Ask the Brain"     │
      │ (selects knowledge pack)      │
      └────┬──────────────────────────┘
           │ HTTP POST to Mnemosyne /ask
           │
┌──────────▼──────────────────┐
│ Mnemosyne HTTP Service      │
│ (RAG pipeline + LLM)        │
│ Query pack "firewall"       │
└─────────────────────────────┘
```

### Where the pack selector gets its list

The "Ask the Brain" panel's pack dropdown is fed by `GET /api/packs`, a server-to-server proxy
to Mnemosyne's `/packs` endpoint, so it offers the brain's **real, built** packs rather than
guessing from discovered vendors. The proxy needs `MNEMOSYNE_URL` set (same as `/api/ask`);
when the brain is unconfigured or unreachable it returns `{"error": ...}` and the panel falls
back to the discovered-vendor packs derived from `/api/collectors` (ADR-0013). The selector only
appears when more than one pack is available.

## The Argus side (VendorPack declaration)

In your Argus vendor pack's `__init__.py`, declare the paired knowledge pack:

```python
from argus.discovery.vendors.pack import VendorPack, Transport, DEVICES

FIREWALL_PACK = VendorPack(
    name="firewall",
    manufacturer="Netgate",
    transport=Transport.DEVICE_SSH,
    capabilities=frozenset({DEVICES}),
    config_vars=("FIREWALL_HOST", "FIREWALL_USERNAME", "FIREWALL_PASSWORD"),
    collector=FirewallCollector,
    knowledge_pack="firewall",  # ← Points to Mnemosyne pack named "firewall"
)
```

The `knowledge_pack` field is:
- **Optional** (defaults to `None` — no knowledge face yet)
- **Surfaced in the API** via `/api/collectors` → `collectors[n].knowledge_pack`
- **Read by the dashboard** to auto-select the expert when the user asks a question about
  that vendor

If the field is `None` or missing, the "Ask the Brain" panel falls back to defaults or
disables that vendor's face.

## The Mnemosyne side (KnowledgePack structure)

A Mnemosyne knowledge pack is a **corpus + configuration + persona**. Create a new directory
under `mnemosyne/src/mnemosyne/packs/<pack_name>/` with:

### 1. manifest.yaml — Declarative configuration

```yaml
# Pack identity — must match the knowledge_pack value in Argus VendorPack
name: firewall
title: Firewall Operations Expert
description: >
  An expert on pfSense and OPNsense firewall operations, configuration, rules, monitoring,
  and troubleshooting. The knowledge counterpart to the Argus pfSense/OPNsense vendor pack.

# Model overrides (optional; fall back to global Mnemosyne settings if not set)
embedding_model: bge-m3
chat_model: qwen2.5:1.5b

# Chunking strategy for this domain (tuned for procedural documentation)
chunk_size: 500
chunk_overlap: 150

# Retrieval: how many context chunks to use
top_k: 5

# The expert's persona — becomes the system prompt for every query
system_prompt: >
  You are a firewall operations expert helping engineers configure, deploy, and troubleshoot
  pfSense and OPNsense firewalls. Answer using ONLY the provided context. Cite the sources
  you use inline as [n]. Be concrete and procedural — give exact menu paths, CLI commands,
  and configuration steps where the context supports it. If the context does not contain
  the answer, say so plainly and suggest what documentation would be needed. Never invent
  firewall configurations or firmware behavior.
```

Key fields:
- `name`: **Must match** `VendorPack.knowledge_pack` in Argus (e.g. "firewall")
- `title`: Human-readable name for the dashboard and logs
- `description`: What this pack covers
- `system_prompt`: Shapes the expert's tone and constraints (the most important lever)
- `chunk_size`, `chunk_overlap`, `top_k`: Domain-specific retrieval tuning

### 2. sources/ — Curated knowledge base

Create a `sources/` directory containing:

**Local documents** (files dropped directly):
- Markdown (`.md`)
- PDF (`.pdf`)
- Plain text (`.txt`)
- Any loader-supported format (see Mnemosyne `loaders.py` for full list)

Place them directly in `sources/` or list them in `sources/sources.yaml`:

```yaml
# sources/sources.yaml — explicit source management
local:
  - ../../../external/pfsense-docs/handbook.md  # Relative path to fetched docs
  - licensing-notes.md

urls:
  - https://docs.netgate.com/pfsense/en/latest/
  - https://docs.opnsense.org/
  # (URLs are fetched at index build time; see staging_dir for offline alternatives)
```

**Quality guidance:**
- Start with official vendor documentation (e.g., Netgate's help, OPNsense wiki)
- Add internal runbooks for your deployment patterns
- Include common troubleshooting steps
- Keep documents self-contained; the retrieval system works best with focused chunks
- Remove vendor marketing fluff; the system prefers procedural/technical content

### 3. Optional pack.py — Custom loading logic

For most packs, Mnemosyne's base `KnowledgePack` class handles loading automatically.
Create `pack.py` only if you need custom behavior:

```python
from mnemosyne.packs import KnowledgePack
from pathlib import Path
from langchain_core.documents import Document

class FirewallPack(KnowledgePack):
    """Custom loader for firewall documentation (e.g., stripping titles, splitting large files)."""
    
    def load(self, *, local_only: bool = False, staging_dir: Path | str | None = None) -> list[Document]:
        # Call parent to load documents
        docs = super().load(local_only=local_only, staging_dir=staging_dir)
        
        # Optional: custom post-processing
        for doc in docs:
            # Example: clean up titles for citations
            title = doc.metadata.get("title", "").strip()
            doc.metadata["title"] = title.replace(" — Netgate Help", "")
        
        return docs
```

Then reference it in `__init__.py`:

```python
from .pack import FirewallPack
```

Mnemosyne's pack discovery will find and instantiate this class automatically.

## Building and testing

### In Mnemosyne

1. Create the pack directory structure (manifest + sources/)
2. Run the indexing pipeline to build the knowledge base:
   ```bash
   mnemosyne index --pack firewall
   ```
3. Query it locally to verify sources are loaded correctly:
   ```bash
   mnemosyne ask firewall "How do I create a firewall rule?"
   ```

### In Argus

1. Declare `knowledge_pack="firewall"` in your VendorPack
2. Run `python -c "from argus.discovery.vendors import discover_packs; packs = discover_packs(); print(packs['pfsense'].knowledge_pack)"`
   → should print `"firewall"`
3. Check the API: `curl http://localhost:8000/api/collectors | jq '.collectors[] | select(.name=="firewall")'`
   → should include `"knowledge_pack": "firewall"`

### Full integration test

1. Start Mnemosyne HTTP service:
   ```bash
   MNEMOSYNE_URL=http://localhost:5000 mnemosyne-http
   ```
2. Start Argus with Mnemosyne configured:
   ```bash
   MNEMOSYNE_URL=http://localhost:5000 argus-http
   ```
3. Open the dashboard, run discovery (pfsense collector), then use "Ask the Brain"
4. Verify that the pack selector shows "firewall" as an option
5. Verify questions are answered with context from firewall documentation

## Distribution

To ship both the Argus and Mnemosyne faces in one package:

**pyproject.toml:**
```toml
[project.entry-points."argus.vendor_packs"]
firewall_vendor = "argus_vendor_firewall:FIREWALL_PACK"

[project.entry-points."mnemosyne.knowledge_packs"]
firewall = "mnemosyne_knowledge_firewall.pack:FirewallPack"
```

**Directory layout:**
```
argus-vendor-firewall-package/
├── src/
│   ├── argus_vendor_firewall/
│   │   ├── __init__.py          (VendorPack definition)
│   │   ├── collector.py         (discovery logic)
│   │   └── models.py            (manufacturer/role mapping)
│   └── mnemosyne_knowledge_firewall/
│       ├── __init__.py
│       ├── pack.py              (custom KnowledgePack, if needed)
│       ├── manifest.yaml        (knowledge pack config)
│       └── sources/             (curated documents)
│           └── sources.yaml
└── pyproject.toml               (two entry points)
```

When a user installs the distribution into their Argus and Mnemosyne environments:
- Argus loads the vendor pack and registers the firewall collector
- Mnemosyne loads the knowledge pack and indexes the firewall documentation
- The dashboard automatically connects them via the `knowledge_pack` field

## Troubleshooting

**"Unknown knowledge pack 'firewall'"**
- Verify the pack name in `manifest.yaml` matches `VendorPack.knowledge_pack` exactly
- Run `mnemosyne list-packs` to see all registered packs
- Ensure the Mnemosyne environment is installed and the pack is discoverable

**"Mnemosyne not configured"**
- Set `MNEMOSYNE_URL=http://localhost:5000` (or your deployment URL) in the Argus environment
- Verify Mnemosyne HTTP service is running: `curl http://localhost:5000/health`

**"Knowledge pack has no sources"**
- Verify `sources/` directory exists and contains `.md`, `.pdf`, or `.txt` files
- Run `mnemosyne index --pack firewall --debug` for verbose indexing logs
- Check that source file paths in `sources.yaml` are correct relative paths

## References

- [ADR-0013](architecture/adr/0013-paired-vendor-knowledge-packs.md) — Paired vendor/knowledge
  packs design
- [Mnemosyne documentation](https://github.com/freed-dev-llc/mnemosyne) — Knowledge pack
  creation and management
- [VENDOR_PACKS.md](VENDOR_PACKS.md) — Creating Argus vendor packs
