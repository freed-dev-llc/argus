# pfSense/OPNsense Discovery Testing

This document describes how to test the pfSense/OPNsense discovery collectors offline and against live lab instances.

## Offline Tests (No Lab Required)

The offline tests in `test_pfsense_collector.py` verify parsing logic and graceful degradation without requiring network access.

Run all offline tests:
```bash
pytest server/tests/test_pfsense_collector.py -v
```

These tests verify:
- Role inference from model strings (SG-5100, SG-3100, generic, etc.)
- IP address extraction from `ifconfig` output
- Skipping of loopback and link-local addresses
- Configuration validation (missing env vars)
- Credential file error handling

## Live Tests (Requires Lab Instances)

The live tests in `test_pfsense_live.py` discover pfSense/OPNsense firewall instances running on lab hardware at:
- **OPNsense**: 192.168.1.92
- **pfSense**: 192.168.1.93

### Prerequisites

1. **Lab instances running**
   - OPNsense at 192.168.1.92 with SSH enabled (port 22)
   - pfSense at 192.168.1.93 with SSH enabled (port 22)

2. **Credential files**
   Create JSON credential files in `~/.secrets/` (readable only by the test user, mode 600):

   **~/.secrets/lab-opnsense-creds**
   ```json
   {
     "username": "root",
     "password": "YourOPNsensePassword123"
   }
   ```

   **~/.secrets/lab-pfsense-creds**
   ```json
   {
     "username": "admin",
     "password": "YourpfSensePassword456"
   }
   ```

   **~/.secrets/lab-snmpv2** (for SNMP discovery, if enabled)
   ```json
   {
     "community": "public"
   }
   ```

   Set file permissions to prevent accidental exposure:
   ```bash
   chmod 600 ~/.secrets/lab-*.creds
   chmod 600 ~/.secrets/lab-snmpv2
   ```

3. **SSH access to lab instances**
   - Both instances must allow password authentication via SSH
   - User must be able to run read-only commands (`show version`, `ifconfig`, `hostname`)
   - Optionally, test SSH keys instead of passwords by pre-installing public keys

### Running Live Tests

Live tests are marked `@pytest.mark.live` and are skipped by default. To run them:

```bash
# Run all live tests
pytest -m live server/tests/test_pfsense_live.py -v

# Run only OPNsense test
pytest -m live server/tests/test_pfsense_live.py::test_discover_opnsense_192_168_1_92 -v

# Run only pfSense test
pytest -m live server/tests/test_pfsense_live.py::test_discover_pfsense_192_168_1_93 -v

# Show output for fixture capture
pytest -m live server/tests/test_pfsense_live.py -v -s
```

### What Live Tests Verify

1. **Device discovery**: At least one device is discovered from each instance
2. **Required fields**: Each device has:
   - `primary_ip`: Set to a private IPv4 address
   - `manufacturer`: Must be "Netgate"
   - `role`: Must be "gateway"
3. **Network validation**: Primary IP is in valid IPv4 format and is private
4. **Logging**: Raw discovery output is printed for fixture collection

### Capturing Fixtures from Live Discovery

To extract real-world output for offline test fixtures:

1. Run live tests with output capture:
   ```bash
   pytest -m live server/tests/test_pfsense_live.py -v -s
   ```

2. Copy device info and SSH command output from the test output

3. Save to fixture files:
   - `server/tests/fixtures/pfsense/ssh_show_version_*.txt` — version command output
   - `server/tests/fixtures/pfsense/ssh_ifconfig_output.txt` — ifconfig command output
   - `server/tests/fixtures/pfsense/snmp_sysdescr_*.txt` — SNMP sysDescr output

## Troubleshooting

### "Credential file not found: ..."
Ensure credential files exist at `~/.secrets/lab-*.creds` with correct permissions (mode 600).

### "SSH connection failed: ..."
- Verify lab instances are running and SSH is enabled
- Check firewall rules allow SSH (port 22)
- Verify hostnames/IPs are correct (192.168.1.92 and 192.168.1.93)
- Test manually: `ssh admin@192.168.1.93` (or `root@192.168.1.92` for OPNsense)

### "asyncssh not installed"
Install the discovery extras:
```bash
pip install 'argus-netbox[discovery]'
```

### "No devices discovered"
- Check that the lab instances are responding
- Verify credentials are correct
- Check SSH logs on the firewall instances (`tail -f /var/log/auth.log`)
- Run manual SSH commands to verify they work:
  ```bash
  ssh admin@192.168.1.93 "show version"
  ssh admin@192.168.1.93 "ifconfig"
  ```

## Continuous Integration

Live tests are skipped by default in CI (no lab instances available). To enable live tests in CI:
1. Provision lab instances in the CI environment
2. Store credentials in CI secrets (not in the repo)
3. Run `pytest -m live` in the CI pipeline
