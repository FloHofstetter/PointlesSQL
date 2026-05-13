# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |
| < 0.1   | No        |

## Reporting a vulnerability

If you discover a security vulnerability in PointlesSQL, please report it
responsibly. **Do not open a public GitHub issue.**

Email **flo.max.hofstetter@gmail.com** with:

- A description of the vulnerability
- Steps to reproduce
- Affected version(s)
- Impact assessment (if known)

You will receive an acknowledgement within **48 hours** and a detailed
response within **7 days** outlining next steps.

## Disclosure policy

- Confirmed vulnerabilities will be fixed in a patch release as soon as
  possible.
- A security advisory will be published via GitHub Security Advisories
  once a fix is available.
- Credit will be given to the reporter unless they prefer to remain
  anonymous.

## Scope

The following are in scope:

- PointlesSQL application code (`pointlessql/`)
- Frontend assets shipped with the wheel (`frontend/`)
- Docker images published to `ghcr.io/flohofstetter/pointlessql`
- Python packages published to PyPI (`pointlessql`, when published)

The following are **out of scope**:

- soyuz-catalog (separate repository — report there)
- Hermes runtime and `hermes-plugin-pointlessql` (separate repositories)
- Notebook user content executed inside the embedded JupyterLab
- Third-party dependencies (report to the upstream maintainer)
- Infrastructure hosting your PointlesSQL deployment
