# 13. Paired vendor + knowledge packs (Argus ↔ Mnemosyne)

Date: 2026-06-29

## Status

Accepted

## Context

Argus answers *"what is on the network"* via **vendor packs** (ADR-0005): an
`argus.vendor_packs` entry point resolving to a `VendorPack` (collector + manufacturer +
transport + capabilities + practices). [Mnemosyne](https://github.com/freed-dev-llc/mnemosyne)
answers *"how does this work / what should I do"* via **knowledge packs**: a
`mnemosyne.knowledge_packs` entry point resolving to a `KnowledgePack` (manifest + curated
sources + eval set). The two were designed in parallel — same plugin mechanism, same
"built-in or installed distribution" model — but nothing connected them:

- The names don't match by construction — Argus's discovery pack is `unifi`; Mnemosyne's
  knowledge pack is `ubiquiti`. There was no link from one to the other.
- The dashboard's "Ask the Brain" panel (ADR-0008) **hardcoded** `pack="ubiquiti"`, so it
  always queried the UniFi knowledge regardless of which vendors were actually discovered. That
  breaks the moment a second vendor exists.

We want adding a vendor to "just work" end-to-end — Argus discovers it *and* the dashboard can
ask the matching expert — while keeping the two services independently deployable (ADR-0008:
Argus carries no RAG dependencies; Mnemosyne runs as a separate `mnemosyne-http`).

## Decision

Treat a vendor as having two **faces** — a *discovery* face (Argus) and a *knowledge* face
(Mnemosyne) — that share a vendor but not necessarily a name, and link them by data:

1. **`VendorPack.knowledge_pack`** — an optional field naming the Mnemosyne knowledge pack that
   explains this vendor (`unifi` → `"ubiquiti"`; `None` = no knowledge face yet). It is
   surfaced in the `list_collectors` / `GET /api/collectors` metadata.
2. **The dashboard derives the ask pack from discovery.** `AskBrainPanel` reads the collectors'
   `knowledge_pack` values and queries that pack (a selector appears when more than one vendor
   has a knowledge face), instead of a hardcoded literal. With no knowledge face it falls back
   to the existing default — back-compatible.
3. **As vendors grow, ship both faces from one distribution.** A new vendor's distribution
   advertises **both** entry points — `argus.vendor_packs` *and* `mnemosyne.knowledge_packs`,
   under the same vendor — so `pip install argus-vendor-pack-<vendor>` gives Argus its collector
   and Mnemosyne its knowledge. They install into their respective service environments (Argus
   and Mnemosyne stay separately deployed); no new framework — both projects already support
   entry-point packs. This is the cross-repo half of the decision; Mnemosyne records the
   matching ADR.

This stays deliberately small: one optional field + one data-driven lookup now, with a
convention (not machinery) for the multi-vendor future.

## Consequences

- The Argus↔Mnemosyne link is data-driven: a vendor pack declares its knowledge counterpart,
  and the dashboard asks the right expert automatically. The hardcoded `ubiquiti` is gone.
- `knowledge_pack` is optional and defaults to `None`, so existing in-tree and external packs
  (the private `argus-vendor-packs`) keep working unchanged; the field is additive.
- The runtime coupling is loose: Argus only needs the *name* of the knowledge pack, not
  Mnemosyne itself. If Mnemosyne is unconfigured/unreachable the panel degrades exactly as
  before (ADR-0008).
- The "one distribution, two entry points" convention is a guideline realized when the second
  vendor lands; nothing in this repo forces a packaging layout. Aligning Argus's `unifi` and
  Mnemosyne's `ubiquiti` pack names is left as optional future cleanup (the explicit field
  removes the need to rename now).
