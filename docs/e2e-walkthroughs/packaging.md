# Packaging / clean-machine install walkthrough

> **Mode:** `hybrid` · **Surface:** Docker CLI + home-page smoke

Covers the contract: a user with a fresh workstation
(no `git clone`, no `../soyuz-catalog` sibling, no GitHub account)
can install the PointlesSQL stack with two commands — download the
compose file and `docker compose up`. Exercises the on-tag
`docker.yml` workflow's output end-to-end — the walkthrough only
passes if a published tag's docker.yml run actually pushed both
public images with the OCI labels they should carry.

## Preconditions

- A tag (`v0.1.0rc3` or later) pushed and the `docker.yml`
 workflow completed successfully — two images now live at
 `ghcr.io/flohofstetter/pointlessql:<tag>` and
 `ghcr.io/flohofstetter/soyuz-catalog:<soyuz-tag>`.
- Both GHCR packages are **public**.
- Host has Docker Engine 24+ and Docker Compose v2.17+.
- Browser: launch with `--browser firefox` per
 [CLAUDE.md](https://github.com/FloHofstetter/PointlesSQL/blob/main/CLAUDE.md) (bundled Firefox, not system Chrome).
- **Do NOT run this playbook from a PointlesSQL source checkout.**
 The pull-only compose file is self-contained; running from a
 source tree risks picking up the dev override and rebuilding
 instead of pulling — masking the thing this playbook tests.

## Walkthrough

1. **Fresh tmpdir simulates a clean machine.**
 - Action: `WORK=$(mktemp -d) && cd "$WORK"`.
 - Assert: `ls -a .` shows only `.` and `..` — no stray
 `docker-compose.yml` present.

2. **Anonymous pull succeeds (proves the images are public).**
 - Action: `docker logout ghcr.io` to wipe any stale credentials.
 - Action: `docker pull ghcr.io/flohofstetter/pointlessql:v0.1.0rc3`.
 - Assert: the pull completes with a digest printed, with no
 `docker login`. If it fails with `denied`/`unauthorized`, the
 package is still private — flip it public **before** continuing,
 otherwise the zero-credential contract is untested.

3. **Download the reference compose file.**
 - Action:
 `curl -fsSL -o docker-compose.yml https://raw.githubusercontent.com/FloHofstetter/PointlesSQL/main/docker/docker-compose.yml`.
 - Assert: the file exists and contains two
 `image: ghcr.io/flohofstetter/...` lines (one per service).
 - Assert: `grep -c '^[[:space:]]*build:' docker-compose.yml`
 returns `0` — the default file pulls, never builds.

4. **`docker compose pull` succeeds.**
 - Action: `docker compose pull`.
 - Assert: both `soyuz-catalog` and `pointlessql` images report
 `Pulled` (or `Already exists` on a warm daemon).

5. **`docker compose up -d` launches both containers.**
 - Action: `docker compose up -d`.
 - Assert: `docker compose ps --format '{{.Service}} {{.State}}'`
 lists both services as `running`.

6. **Both healthchecks report `healthy`.**
 - Action: poll `docker compose ps --format json | jq -r
 '.[] | "\(.Service) \(.Health)"'` every 2s for up to 60s.
 - Assert: both rows end at `healthy`. Services must not take
 longer — the image is pre-built, no dep install happens at
 container start.

7. **Home page renders under Playwright MCP.**
 - Action: `browser_navigate('http://127.0.0.1:8000/')`.
 - Action: `browser_snapshot()`.
 - Assert: the snapshot contains the Welcome `<h1>` (matches the
 assertion in [`home.md`](home.md) step 1 — same template
 source, independent of install method).
 - Action: `browser_network_requests()`.
 - Assert: the document request returned HTTP 200.

8. **OCI labels are present on both images.**
 - Action: `docker image inspect
 ghcr.io/flohofstetter/pointlessql:v0.1.0rc3 --format
 '{{index .Config.Labels "org.opencontainers.image.source"}}'`.
 - Assert: output is `https://github.com/FloHofstetter/PointlesSQL`.
 - Action: same inspect on the soyuz image.
 - Assert: output is `https://github.com/FloHofstetter/soyuz-catalog`.
 - (These labels are what GHCR uses to link the package to the
 repo sidebar — a missing source label is a silent UX
 regression, not a crash.)

9. **Teardown leaves no volumes behind.**
 - Action: `docker compose down -v`.
 - Assert: `docker volume ls --filter label=com.docker.compose.project=$(basename "$WORK")`
 returns no rows.
 - Action: `cd / && rm -rf "$WORK"`.

## Found bugs

(none at time of writing — fill in during the first live replay)

## Playwright MCP script

Intent-level pseudocode for the browser portion (step 7):

```
browser_navigate('http://127.0.0.1:8000/')
browser_snapshot()
browser_network_requests()
```
