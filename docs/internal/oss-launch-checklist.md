# OSS-Launch Checklist (Pre-Visibility-Flip)

This file is the runnable to-do list for the external user actions
required *before* the public visibility flip of PointlesSQL,
soyuz-catalog, shoreguard-fresh, and hermes-plugin-pointlessql.
The Some-day "Pre-OSS-release hygiene" roadmap block describes the
*what* and *why*; this file is the literal hand-off.

Status legend: `[ ]` = todo, `[x]` = done, `[~]` = in progress.

Last updated: 2026-05-13.

---

## 1. Trademark filings (EUIPO)

EU-wide trademark protection costs roughly €850 per mark across
three Nice classes; DE-only via DPMA is roughly €290 per mark.
File before the visibility flip — once the brands are public, the
priority clock starts and a squatter can pre-empt.

- [ ] Pre-filing search — confirm no collisions:
  - EUIPO eSearch: <https://www.tmdn.org/tmview/>
  - DPMA register: <https://register.dpma.de/>
  - Known risk: existing **ShoreGuard** mark in maritime
    industry (Class 6 metal / Class 12 vehicles). Class-9-only-
    software filing should still clear; document the search
    outcome.
- [ ] **PointlesSQL** — Classes 9 (software) + 42 (SaaS) + 41
      (consulting/training). EU: ~€850. DE-only fallback: ~€290.
- [ ] **soyuz-catalog** — same classes. EU: ~€850 / DE: ~€290.
- [ ] **ShoreGuard** — same classes. EU: ~€850 / DE: ~€290.
- Total EU-wide: ~€2550. DE-only fallback: ~€870.
- Filing portal: <https://euipo.europa.eu/ohimportal/en/route-to-registration>

## 2. Domain registrations

Buy before the launch sprint. Cloudflare Registrar for everything
except `.dev` (Cloudflare doesn't sell `.dev` — use Porkbun).

- [ ] `pointlessql.dev` (Porkbun)
- [ ] `pointlessql.io`
- [ ] `pointlessql.com`
- [ ] `shoreguard.io`
- [ ] `shoreguard.dev` (Porkbun)
- [ ] `soyuz-catalog.io`
- Total: ~€200/year with Cloudflare + Porkbun split.

## 3. CODE_OF_CONDUCT.md drop-in (4 repos)

Skipped during the pre-OSS hygiene session because the canonical
text triggered a content filter when bulk-written. Drop in at
visibility-flip time directly from the source:

```bash
for repo in PointlesSQL soyuz-catalog shoreguard-fresh hermes-plugin-pointlessql; do
    curl -fsSL \
      https://raw.githubusercontent.com/EthicalSource/contributor_covenant/release/content/version/2/1/code_of_conduct.md \
      -o ~/git/$repo/CODE_OF_CONDUCT.md
    # then: replace the placeholder enforcement contact email
    sed -i 's|\[INSERT CONTACT METHOD\]|flo.max.hofstetter@gmail.com|' \
        ~/git/$repo/CODE_OF_CONDUCT.md
done
```

- [ ] Run the loop above.
- [ ] Sanity-check each file shows v2.1 + the correct contact email.

## 4. CLA-Assistant setup (4 repos)

Three external steps that must happen before the CLA workflow
can run successfully:

- [ ] Install the **contributor-assistant** GitHub App on the
      `FloHofstetter` account: <https://github.com/apps/contributor-assistant>
- [ ] Create a **public gist** named `signatures.json` (one
      shared across the 4 repos) containing `{}`. Note the gist
      raw URL — it goes into every repo's `.github/workflows/cla.yml`.
- [ ] Create a fine-grained PAT with `contents:write` on the four
      repos. Store it as repo secret `CLA_PAT` in each:
      ```
      gh secret set CLA_PAT --repo FloHofstetter/PointlesSQL < <(echo "<token>")
      gh secret set CLA_PAT --repo FloHofstetter/soyuz-catalog < <(echo "<token>")
      gh secret set CLA_PAT --repo FloHofstetter/shoreguard-fresh < <(echo "<token>")
      gh secret set CLA_PAT --repo FloHofstetter/hermes-plugin-pointlessql < <(echo "<token>")
      ```
- [ ] Drop in the CLA text at `.github/CLA.md` per repo — the CNCF
      Individual CLA v1.0 markdownified, with a one-sentence
      preamble crediting Florian Hofstetter as project owner. The
      canonical CNCF PDF is at:
      <https://github.com/cncf/cla/blob/main/individual-cla.pdf>
- [ ] Drop in the workflow at `.github/workflows/cla.yml` per
      repo. The template (only `path-to-document` URL differs per
      repo):

      ```yaml
      name: CLA Assistant
      on:
        issue_comment:
          types: [created]
        pull_request_target:
          types: [opened, closed, synchronize]
      jobs:
        CLAAssistant:
          runs-on: ubuntu-latest
          steps:
            - name: CLA Assistant
              if: (github.event.comment.body == 'recheck' ||
                   github.event.comment.body == 'I have read the CLA Document and I hereby sign the CLA') ||
                   github.event_name == 'pull_request_target'
              uses: contributor-assistant/github-action@v2.4.0
              env:
                GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
                PERSONAL_ACCESS_TOKEN: ${{ secrets.CLA_PAT }}
              with:
                path-to-signatures: '<gist-raw-url>'
                path-to-document: 'https://github.com/FloHofstetter/<repo>/blob/main/.github/CLA.md'
                branch: 'main'
                allowlist: FloHofstetter,dependabot[bot]
      ```

## 5. LinkedIn update

Recruiters source via LinkedIn (HireEZ / Gem / SeekOut keyword-
scrape LinkedIn, not GitHub). The path to inbound reach-out goes
*through* LinkedIn even when the engineer discovery starts on
GitHub.

- [ ] **Headline**: "Building open-source data audit + governance
      — PointlesSQL · soyuz-catalog · shoreguard"
- [ ] **About**: 3 paragraphs — what the audit-stack does, what
      the governance-stack does, EU-AI-Act framing.
- [ ] **Skills**: Python, FastAPI, Delta Lake, Unity Catalog,
      MLflow, audit, lineage, governance, OpenShell, EU AI Act,
      SOC 2, GDPR. Recruiter-sourcing tools key off these.
- [ ] **Featured**: link to PointlesSQL repo + soyuz-catalog +
      shoreguard once visibility is flipped.

## 6. Launch-day mechanics (deferred to launch sprint, NOT now)

Listed here only so the path is documented; the actual posts go
out on launch day, not now.

- [ ] Show HN post with demo screenshot (Mon/Tue, 8-10 UTC).
- [ ] Twitter thread (10-12 tweets) tagging Data-Eng-Twitter.
- [ ] Reddit r/dataengineering + r/programming.
- [ ] LinkedIn long-form announcement.
- [ ] Blog post #1 same day on the project blog.
- [ ] `gh repo edit FloHofstetter/<repo> --visibility public` for
      all four repos (one command per repo, in coordinated
      sequence).

---

## Quick-reference cost summary

| Item                                | Cost     | Recurring? |
|-------------------------------------|----------|------------|
| 3× EUIPO trademarks (EU-wide)       | ~€2550   | every 10y  |
| 3× DPMA trademarks (DE fallback)    | ~€870    | every 10y  |
| 6 domains (Cloudflare + Porkbun)    | ~€200    | yearly     |
| CLA-Assistant GitHub App            | €0       | —          |
| CODE_OF_CONDUCT.md (Contributor Covenant) | €0 | —          |
| **Total worst-case Year-1 cash**    | **~€2750** | mostly one-shot |

Roadmap reference: `ROADMAP.md` Some-day "Pre-OSS-release hygiene"
block. GTM strategy + acquihire economics:
`~/.claude/projects/-home-flo-git-PointlesSQL/memory/project_gtm_strategy_2026_04_27.md`.
Private strategy file (do NOT commit): `~/.claude/strategy/STRATEGY.md`.
