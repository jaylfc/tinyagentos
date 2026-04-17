#!/bin/bash
# host-firewall-up.sh — insert ACCEPT rules into DOCKER-USER so incus bridge
# traffic isn't dropped by Docker's default FORWARD policy.
#
# Idempotent: uses 'iptables -C' to check before each '-I'. Safe to run
# multiple times (e.g. on service restart or manual invocation).
#
# Environment:
#   BRIDGES  space-separated list of bridge interfaces to allow
#            default: incusbr0

set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "host-firewall-up.sh: must run as root" >&2
    exit 1
fi

BRIDGES="${BRIDGES:-incusbr0}"

# If the DOCKER-USER chain doesn't exist, there's nothing to do.
if ! iptables -n -L DOCKER-USER >/dev/null 2>&1; then
    echo "host-firewall-up: DOCKER-USER chain not found (docker not installed?); nothing to do."
    exit 0
fi

for BRIDGE in $BRIDGES; do
    # Rule 1: traffic arriving on the bridge (container → host or container → internet)
    if iptables -C DOCKER-USER -i "$BRIDGE" -j ACCEPT 2>/dev/null; then
        echo "host-firewall-up: ACCEPT -i $BRIDGE already present; skipping."
    else
        iptables -I DOCKER-USER -i "$BRIDGE" -j ACCEPT
        echo "host-firewall-up: inserted ACCEPT -i $BRIDGE into DOCKER-USER."
    fi

    # Rule 2: traffic leaving the bridge toward containers (return traffic / initiated from host)
    if iptables -C DOCKER-USER -o "$BRIDGE" -j ACCEPT 2>/dev/null; then
        echo "host-firewall-up: ACCEPT -o $BRIDGE already present; skipping."
    else
        iptables -I DOCKER-USER -o "$BRIDGE" -j ACCEPT
        echo "host-firewall-up: inserted ACCEPT -o $BRIDGE into DOCKER-USER."
    fi
done
