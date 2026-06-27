# Custom NetBox image = stock NetBox + the prometheus-sd plugin, which exposes a
# Prometheus http_sd service-discovery API (so the monitoring stack can pull its
# scrape targets from NetBox). Built by docker-compose (see the `netbox` service's
# `build:`). The base image stays pinned/overridable via NETBOX_IMAGE in .env, passed
# in as the NETBOX_BASE_IMAGE build arg.
ARG NETBOX_BASE_IMAGE=netboxcommunity/netbox:v4.6-5.0.1
FROM ${NETBOX_BASE_IMAGE}

# netbox-plugin-prometheus-sd v1.3.0 supports NetBox >= 4.0 (module: netbox_prometheus_sd).
# This image manages its venv with uv (no pip console script / pip module is present).
RUN VIRTUAL_ENV=/opt/netbox/venv /usr/local/bin/uv pip install --no-cache netbox-plugin-prometheus-sd==1.3.0

# Enable the plugin. NetBox loads every *.py in /etc/netbox/config/; the stock
# plugins.py is only commented examples, so we replace it with the active config.
COPY plugins.py /etc/netbox/config/plugins.py
