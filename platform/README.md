# platform/

Infrastructure for the **tinyagentos.com** public website. This is not the
TinyAgentOS product itself — it's the scripts, config, and static assets that
bring up the Proxmox LXC container that serves the landing page, docs site,
and BitTorrent tracker.

## What's in here

```
platform/
├── install-lxc.sh       # Run on the Proxmox host: creates + provisions the LXC
├── provision.sh         # Run inside the LXC: installs packages, configures services
├── Caddyfile            # Caddy reverse-proxy/static-server config for all subdomains
├── DEPLOYMENT.md        # Step-by-step runbook for tomorrow's setup session
├── README.md            # this file
└── site/
    ├── public/          # Landing page (tinyagentos.com) — static HTML/CSS
    │   ├── index.html
    │   ├── style.css
    │   ├── favicon.svg
    │   └── assets/
    └── docs/            # Docs site scaffold (docs.tinyagentos.com)
        ├── mkdocs.yml   # MkDocs config pointing at the repo's docs/ tree
        └── _docs_overrides.css
```

## Relationship to the main repo

All files under `platform/` are infrastructure for the website, not the
product. The product lives in `tinyagentos/`, `desktop/`, and `scripts/`.
Do not mix them.

The one exception is `docs/deploy/platform-lxc.md` (in the main `docs/` tree),
which documents the LXC configuration for public reference per issue #90.

## Workflow

### First-time provisioning

1. Download the Debian 12 template on the Proxmox host if not present:
   ```bash
   pveam update && pveam download local debian-12-standard
   ```
2. Clone this repo on the Proxmox host (or copy the `platform/` directory there).
3. Set any environment overrides (see `install-lxc.sh` header).
4. Run:
   ```bash
   sudo bash platform/install-lxc.sh
   ```
5. Point DNS at the LXC IP (see `platform/Caddyfile` for the required records).
6. Caddy auto-issues Let's Encrypt certs on first request.

Full step-by-step in `platform/DEPLOYMENT.md`.

### Building the docs site locally

The docs site uses MkDocs with the Material theme, rendering the main repo's
`docs/` tree. Build it from the repo root:

```bash
pip install mkdocs mkdocs-material pymdown-extensions mkdocs-exclude
cd platform/site/docs
mkdocs build
```

Output lands in `platform/site/docs/site/`. Deploy to the LXC:

```bash
rsync -av --delete platform/site/docs/site/ \
    root@<LXC-IP>:/var/www/docs.tinyagentos.com/public/
```

A GitHub Actions workflow (to be added in a follow-up) will do this automatically
on merge to `master`.

### Updating the landing page

Edit `platform/site/public/index.html` and `platform/site/public/style.css`,
then copy to the LXC:

```bash
rsync -av --delete platform/site/public/ \
    root@<LXC-IP>:/var/www/tinyagentos.com/public/
```

### Re-running provision.sh

`provision.sh` guards itself with a sentinel file at
`/var/lib/tinyagentos-platform/provisioned`. Safe to re-run: it exits
immediately if provisioning has already completed. To force a full re-run:

```bash
pct exec <CTID> -- rm /var/lib/tinyagentos-platform/provisioned
pct exec <CTID> -- bash /root/provision.sh
```

## GitHub issues this covers

| Issue | Title |
|---|---|
| #90 | tinyagentos.com: platform LXC provisioning (phase 1) |
| #91 | tinyagentos.com: landing page + docs site (phase 1) |
| #92 | tinyagentos.com: opentracker on tracker.tinyagentos.com (phase 2) |

Issue #92 is labelled phase-2 but opentracker is provisioned by `provision.sh`
in phase 1 to avoid a second maintenance window. The Grafana panel and IPv6
verification (#92 acceptance criteria) are deferred.
