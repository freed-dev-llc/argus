#!/usr/bin/env bash
#
# Deploy smoke test — confirm the running Argus stack works after a deploy/.env or image change.
#
# Runs three read-only checks against the live argus-server HTTP API:
#   1. /health returns 200
#   2. the firewall collector actually discovers >=1 device over SSH (no error notes)
#   3. drift for that collector is 0 (NetBox matches the live network)
#
# This is NOT a CI test — it needs the running stack and real network reach to the firewalls,
# so run it on the deploy host (cerebrum) after a change. The compose→collector env *wiring* is
# guarded separately by an offline unit test (server/tests/test_deploy_compose_env.py).
#
# Usage:
#   deploy/smoke-test.sh [BASE_URL]        # default http://127.0.0.1:8094
# Env:
#   COLLECTOR=firewall   collector to exercise (default "firewall")
#   HTTP_TOKEN=...        bearer token, if the API is protected (default: none/open)
#
set -uo pipefail

BASE="${1:-http://127.0.0.1:8094}"
COLLECTOR="${COLLECTOR:-firewall}"
AUTH=()
[ -n "${HTTP_TOKEN:-}" ] && AUTH=(-H "Authorization: Bearer ${HTTP_TOKEN}")

fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }

# 1. health -----------------------------------------------------------------
code=$(curl -s -o /dev/null -w '%{http_code}' -m 10 ${AUTH[@]+"${AUTH[@]}"} "$BASE/health") \
    || fail "server unreachable at $BASE"
[ "$code" = "200" ] || fail "/health returned HTTP $code"
echo "✓ health OK"

# 2. discovery scan finds devices -------------------------------------------
scan=$(curl -s -m 120 ${AUTH[@]+"${AUTH[@]}"} -X POST "$BASE/api/collectors/$COLLECTOR/scan") \
    || fail "scan request failed"
echo "$scan" | python3 -c '
import json, sys
d = json.load(sys.stdin)
devs = d.get("devices", [])
errs = [n for n in d.get("notes", []) if "failed" in n.lower() or "not configured" in n.lower()]
if errs:
    sys.exit("collector reported errors: %s" % errs)
if not devs:
    sys.exit("collector discovered no devices")
for x in devs:
    print("    discovered: %s | %s | %s | %s"
          % (x.get("name"), x.get("manufacturer"), x.get("model"), x.get("primary_ip")))
' || fail "scan(collector=$COLLECTOR) did not discover devices cleanly"
echo "✓ scan discovered devices (collector=$COLLECTOR)"

# 3. drift is 0 -------------------------------------------------------------
drift=$(curl -s -m 120 ${AUTH[@]+"${AUTH[@]}"} "$BASE/api/drift?collector=$COLLECTOR") \
    || fail "drift request failed"
total=$(echo "$drift" | python3 -c 'import json,sys; print(json.load(sys.stdin)["summary"]["total"])') \
    || fail "could not parse drift response"
[ "$total" = "0" ] || fail "drift is $total (expected 0) — NetBox is out of sync with the live network"
echo "✓ drift is 0 (collector=$COLLECTOR)"

echo "SMOKE PASS — $COLLECTOR @ $BASE"
