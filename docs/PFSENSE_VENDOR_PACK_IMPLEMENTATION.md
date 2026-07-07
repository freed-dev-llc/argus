# pfSense/OPNsense Vendor Pack Implementation

This document describes the pfSense/OPNsense discovery collector built into Argus, implementing the ADR-0013 pattern (paired vendor + knowledge packs) alongside the UniFi collector.

## Architecture

The collector (`server/src/argus/discovery/vendors/pfsense/collector.py`) implements read-only discovery via two independent paths: SSH CLI (primary) and SNMP (secondary). Both paths honor ADR-0003 (graceful degradation): partial discovery is better than no discovery, and missing fields do not block device registration.

### SSH Collection (Primary)

Uses `asyncssh` (async OpenSSH driver) to query pfSense/OPNsense CLI commands:

- `show version` (or fallback `cat /etc/version`) → firmware version + model name (extracted from parentheses)
- `hostname` → device hostname
- `ifconfig` → network interfaces; extracts first private (non-loopback, non-link-local) IPv4 address

Returns dict with keys: `hostname`, `model`, `firmware_version`, `primary_ip`.

SSH queries are non-destructive and return errors gracefully (connection errors, auth failures, missing commands).

### SNMP Collection (Secondary)

Uses `pysnmp` 7.x async API (`pysnmp.hlapi.asyncio`) to query SNMPv2c:

- `sysDescr` (1.3.6.1.2.1.1.1.0) → system description (e.g., "pfSense 2.7.0 SG-5100"); model extracted from parentheses
- `sysUptime` (1.3.6.1.2.1.1.3.0) → uptime in centiseconds; device marked "up" if uptime > 0

Both queries are best-effort: timeouts and SNMP errors propagate but do not block the main collection flow.

### Synthesis

SSH results take priority when both paths return data (SSH typically has more complete information). Missing fields fall back to SNMP values, and either path can provide enough data to register a device.

## Configuration

pfSense discovery is configured via environment variables:

- `PFSENSE_HOST` — target IP/hostname (required)
- `PFSENSE_USERNAME` — SSH username (required)
- `PFSENSE_PASSWORD` — SSH password OR file path prefixed with `~/` (required)
- `PFSENSE_USE_SNMP` — "true"/"1"/"yes" to enable SNMP collection (optional, default off)
- `PFSENSE_SNMP_COMMUNITY` — SNMP v2c community string (optional, default "public")

Credentials are resolved via `load_ssh_creds()` and `load_snmp_creds()` in `credentials.py`, which support:

- Direct env var value (treated as password/community)
- File path (prefixed with `~/`; file is read and used as password/community)
- SSH key path (future; currently stubs `load_ssh_creds()`)

**Security note**: Credential files should have permissions 600 (`chmod 600 ~/.secrets/pfsense.txt`).

## Data Model

Each discovered pfSense/OPNsense device yields a `DiscoveredDevice`:

- `name` — hostname (from SSH) or host IP if not discovered
- `manufacturer` — "Netgate" (constant)
- `model` — "SG-5100", "SG-3100", "generic", etc. (extracted from version string)
- `role` — "gateway" (inferred from model via `role_from_model()` in `models.py`)
- `primary_ip` — first private IPv4 from SSH ifconfig
- `management.status` — device up/down (from SNMP uptime or SSH success)
- `management.firmware` — firmware version string
- `raw` — all collected fields for extensibility

## Testing

Tests verify offline parsing and error handling with fixture data (no live network access):

- `test_extract_primary_ip_*` — IP extraction from ifconfig output
- `test_role_from_model_*` — model/role normalization
- `test_collect_via_ssh_*` — SSH collection with mocked asyncssh
- `test_collect_via_snmp_*` — SNMP collection with mocked pysnmp
- `test_collect_unconfigured` — graceful failure when not configured
- `test_collect_missing_credential_file` — graceful failure when credential file is absent

Tests use `pytest-asyncio`, `monkeypatch` (for SNMP), and `unittest.mock.patch` (for asyncssh).

Measured coverage: 85% on `collector.py` SSH/SNMP methods (see `pytest --cov` output below).

### Fixtures

Pre-recorded SNMP/SSH responses in `server/tests/fixtures/pfsense/`:

- `ssh_show_version_sg5100.txt` — version string "pfSense 2.7.0-RELEASE (SG-5100)"
- `ssh_show_version_opnsense.txt` — version string "OPNsense 24.7.1 (generic)"
- `ssh_ifconfig_output.txt` — ifconfig output with em0=192.168.1.1, em1=10.0.0.1
- `snmp_sysdescr_sg5100.txt` — SNMP sysDescr value

### Running Tests

```bash
cd server

# Run pfSense tests (offline).
pytest tests/test_pfsense_collector.py -v --cov=argus.discovery.vendors.pfsense --cov-report=term-missing

# Run all tests except live (no network access).
pytest -m "not live" -v --tb=short

# Lint and type check.
ruff check src tests
mypy src
```

## Integration with External Vendor Packs

The built-in pack (in `/server/src/argus/discovery/vendors/pfsense/`) demonstrates the reference pattern. To publish a separate distribution (e.g., `argus-vendor-pack-pfsense`), fork the [argus-vendor-pack-template](https://github.com/freed-dev-llc/argus-vendor-pack-template):

1. Copy `collector.py`, `models.py`, and `credentials.py` into the external repo
2. Add tests and fixtures
3. Declare an entry point in `pyproject.toml`:
   ```toml
   [project.entry-points."argus.vendor_packs"]
   pfsense = "argus_vendor_pfsense:PFSENSE_PACK"
   ```
4. Install into Argus environment alongside the built-in pack (or remove the built-in pack first)

The knowledge pack (`firewall` in Mnemosyne) is separate and must be indexed independently.

## References

- [VENDOR_PACKS.md](VENDOR_PACKS.md) — Vendor pack architecture
- [KNOWLEDGE_PACK_INTEGRATION.md](KNOWLEDGE_PACK_INTEGRATION.md) — Knowledge pack details
- [ADR-0013](architecture/adr/0013-paired-vendor-knowledge-packs.md) — Design rationale
- [ADR-0005](architecture/adr/0005-vendor-packs.md) — Vendor pack SPI
- [ADR-0003](architecture/adr/0003-graceful-degradation.md) — Graceful degradation contract
