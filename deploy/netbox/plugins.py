# Enabled NetBox plugins. Baked into the custom image (see Dockerfile); NetBox's
# config loader reads every *.py in /etc/netbox/config/.
PLUGINS = ["netbox_prometheus_sd"]

# netbox-plugin-prometheus-sd needs no PLUGINS_CONFIG. It exposes, under
# /api/plugins/prometheus-sd/: devices/, virtual-machines/, services/, ip-addresses/
# — each returning Prometheus http_sd-compatible JSON with __meta_netbox_* labels.
