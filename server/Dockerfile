FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

# Install Argus plus the runtime discovery deps its shipped collectors import: asyncssh
# (pfSense/OPNsense SSH, ADR-0013) and pysnmp (SNMP/LLDP + pfSense SNMP). The full
# [discovery] extra also pulls napalm/netmiko, which no collector imports yet — excluded to
# keep the image lean; add them (or switch to '.[discovery]') when a driver-based collector
# lands. Bounds mirror the [discovery] extra in pyproject.toml.
RUN pip install --no-cache-dir . 'asyncssh>=2.14.0' 'pysnmp>=7.1.27'

EXPOSE 8080

ENTRYPOINT ["argus-http"]
