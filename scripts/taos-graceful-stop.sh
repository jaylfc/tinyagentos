#!/bin/bash
# Triggers taOS graceful shutdown via HTTP. Used by systemd stop/pre-shutdown hooks.
# Succeeds even if the API is unreachable so we don't block system reboot.
curl -fsS -X POST --max-time 320 http://localhost:6969/api/system/prepare-shutdown || true
