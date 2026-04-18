# Packaging / clean-machine install walkthrough

Covers the Sprint 40 contract: a user with a fresh workstation
(no `git clone`, no `../soyuz-catalog` sibling, no ssh key
against `github.com`) can install the PointlesSQL stack by logging
in to GHCR and pulling two private images. Exercises the on-tag
`docker.yml` workflow's output end-to-end — the walkthrough only
passes if the first `v0.1.0rc3` tag's docker.yml run actually
published both images with the OCI labels they should carry.

## Preconditions

- Sprint 40 tag (`v0.1.0rc3` or later) pushed and the `docker.yml`
  workflow completed successfully — two images now live at
  `ghcr.io/flohofstetter/pointlessql:<tag>` and
  `ghcr.io/flohofstetter/soyuz-catalog:<soyuz-tag>`.
- Host has Docker Engine 24+ and Docker Compose v2.17+.
- A **classic** PAT with `read:packages` scope exported as
  `GHCR_PAT`. (Fine-grained PATs need per-package grants that the
  classic scope sidesteps.)
- Browser: launch with `--browser firefox` per
  [CLAUDE.md](../../CLAUDE.md) (bundled Firefox, not system Chrome).
- **Do NOT run this playbook from a PointlesSQL source checkout.**
  Compose inside a source tree would find the local
  `docker-compose.yml` with the `build:` blocks active and silently
  rebuild instead of pulling — masking the thing this playbook is
  there to test.

## Walkthrough

1. **Fresh tmpdir simulates a clean machine.**
   - Action: `WORK=$(mktemp -d) && cd "$WORK"`.
   - Assert: `ls -a .` shows only `.` and `..` — no stray
     `docker-compose.yml` present.

2. **Anonymous pull fails (proves the images are private).**
   - Action: `docker logout ghcr.io` to wipe any stale credentials.
   - Action: `docker pull ghcr.io/flohofstetter/pointlessql:v0.1.0rc3`.
   - Assert: the pull exits non-zero with `denied` or
     `unauthorized` in stderr. If it succeeds, the image was
     accidentally published public — fix **before** continuing,
     otherwise the auth flow is untested.

3. **`docker login` with the PAT succeeds.**
   - Action: `echo "$GHCR_PAT" | docker login ghcr.io -u <user> --password-stdin`.
   - Assert: stdout reports `Login Succeeded`.
   - Action: retry `docker pull ghcr.io/flohofstetter/pointlessql:v0.1.0rc3`.
   - Assert: the pull now completes with a digest printed.

4. **Download the reference compose file at the tag.**
   - Action:
     `curl -fL -o docker-compose.yml https://raw.githubusercontent.com/FloHofstetter/PointlesSQL/v0.1.0rc3/docker-compose.yml`.
   - Assert: the file exists and contains two commented `# image:
     ghcr.io/flohofstetter/...` lines (one per service).

5. **Flip `build:` → `image:` on both services.**
   - Action: single `sed` to uncomment the two `# image:` lines
     and comment the six `build:` lines (`sed -i -E
     's/^([[:space:]]*)# (image: ghcr\.io)/\1\2/;
     s/^([[:space:]]*)(build:|  context:|  dockerfile:|  additional_contexts:|    soyuz-catalog:|  ssh:|    - default|  secrets:|    - gh_pat)/\1# \2/'
     docker-compose.yml` — exact incantation lives in
     [docs/install.md](../install.md)).
   - Assert: `grep -c '^[[:space:]]*image: ghcr.io' docker-compose.yml` returns `2`.
   - Assert: `grep -c '^[[:space:]]*build:' docker-compose.yml` returns `0`.

6. **`docker compose pull` succeeds.**
   - Action: `docker compose pull`.
   - Assert: both `soyuz-catalog` and `pointlessql` images report
     `Pulled` (or `Already exists` on a warm daemon).

7. **`docker compose up -d` launches both containers.**
   - Action: `docker compose up -d`.
   - Assert: `docker compose ps --format '{{.Service}} {{.State}}'`
     lists both services as `running`.

8. **Both healthchecks report `healthy`.**
   - Action: poll `docker compose ps --format json | jq -r
     '.[] | "\(.Service) \(.Health)"'` every 2s for up to 60s.
   - Assert: both rows end at `healthy`. Services must not take
     longer — the image is pre-built, no dep install happens at
     container start.

9. **Home page renders under Playwright MCP.**
   - Action: `browser_navigate('http://127.0.0.1:8000/')`.
   - Action: `browser_snapshot()`.
   - Assert: the snapshot contains the Welcome `<h1>` (matches the
     assertion in [`home.md`](home.md) step 1 — same template
     source, independent of install method).
   - Action: `browser_network_requests()`.
   - Assert: the document request returned HTTP 200.

10. **OCI labels are present on both images.**
    - Action: `docker image inspect
      ghcr.io/flohofstetter/pointlessql:v0.1.0rc3 --format
      '{{index .Config.Labels "org.opencontainers.image.source"}}'`.
    - Assert: output is `https://github.com/FloHofstetter/PointlesSQL`.
    - Action: same inspect on the soyuz image.
    - Assert: output is `https://github.com/FloHofstetter/soyuz-catalog`.
    - (These labels are what GHCR uses to link the package to the
      repo sidebar — a missing source label is a silent UX
      regression, not a crash.)

11. **Teardown leaves no volumes behind.**
    - Action: `docker compose down -v`.
    - Assert: `docker volume ls --filter label=com.docker.compose.project=$(basename "$WORK")`
      returns no rows.
    - Action: `cd / && rm -rf "$WORK"`.

## Found bugs

(none at time of writing — fill in during the first live replay,
following the BUG-40-NN naming convention from Phase 7)

## Playwright MCP script

Intent-level pseudocode for the browser portion (steps 9):

```
browser_navigate('http://127.0.0.1:8000/')
browser_snapshot()
browser_network_requests()
```
