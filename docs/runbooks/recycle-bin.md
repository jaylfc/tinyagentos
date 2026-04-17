# Recycle bin runbook

## How it works (per container)

Every taOS agent container has a soft-delete recycle bin at
`/var/recycle-bin/` backed by freedesktop.org trash-cli. The default
`/usr/bin/rm` is shadowed by `/usr/local/bin/rm`, which forwards to
`trash-put` — so `rm file.txt` moves `file.txt` into the recycle bin
rather than permanently deleting it.

Items in the recycle bin are automatically purged after 30 days via the
`tinyagentos-recycle-sweep.timer` systemd unit.

## Browsing / restoring / emptying

Inside a container:
- `trash-list` — list trashed items
- `trash-restore` — interactive restore
- `trash-empty` — purge now (bypass the 30-day sweep)

In the taOS UI: Files app → Recycle Bin tab (Phase 1.E — pending).

## Escape hatches

- `/usr/bin/rm file.txt` — permanent delete (no shadow applied)
- `TAOS_TRASH_DISABLE=1 rm file.txt` — single-command permanent delete
- `TAOS_TRASH_DISABLE=1 bash` — entire shell session uses real rm

## What this does NOT cover

- Binaries that call `unlink()` directly rather than shelling out (Layer 2,
  libtrash LD_PRELOAD, deferred to a later phase).
- Deletions via NFS/SMB/S3 from clients outside the container.
- The FS-level snapshot backstop (Layer 3) is configured on the host,
  not per-container — see `docs/design/architecture-pivot-v2.md` §6.3.

## Admin ops

- Force purge ALL agents' bins (host-side): loop over taos-agent-* and
  `incus exec <name> -- trash-empty -f`.
- Change retention (default 30d): edit
  `/usr/local/bin/taos-recycle-sweep` in the container (`-mtime +30`
  → `-mtime +N`) and reload the timer.
- Bypass entire container's recycle bin: `systemctl disable --now
  tinyagentos-recycle-sweep.timer` + `ln -sf /usr/bin/rm /usr/local/bin/rm`.
