// commitlint configuration (W3 D6 follow-up).
//
// Enforces Conventional-Commits shape so the cliff-driven CHANGELOG
// regen (scripts/regen-changelog.py) can categorise every commit
// deterministically.  Project-level package.json is intentionally
// absent — the pre-commit hook (alessandrojcm/commitlint-pre-commit-hook)
// and the GitHub workflow (wagoid/commitlint-github-action) both
// auto-fetch the Node runtime they need.
//
// Tuning rationale:
// - type-enum: strict; the historical 5 'debug(ci):' commits stay
//   in git but new ones must use 'ci:' or 'chore:' instead.
// - scope-enum: disabled.  The repo carries ~130 historical scopes,
//   and the long tail (page-name scopes like 'chrome', 'topbar')
//   means a closed list would either reject legitimate new scopes
//   or balloon to unreadable size.  Type-discipline is the primary
//   load-bearing rule; scope-shape is freeform.
// - subject-case: disabled — many historical subjects are sentence
//   case (capitalised first word), the CHANGELOG renderer normalises
//   anyway.
// - subject-max-length: 120 (loosened from default 100 because some
//   legitimate refactor commits carry rc-range suffixes that push
//   past 100).
// - header-max-length: 120 (matches subject).
//
// To install the commit-msg hook locally after this lands:
//   uv run pre-commit install --hook-type commit-msg

module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'type-enum': [
      2, 'always',
      ['feat', 'fix', 'docs', 'refactor', 'test', 'chore',
       'build', 'ci', 'perf', 'style', 'revert'],
    ],
    'scope-enum': [0],
    'scope-empty': [0],
    'scope-case': [0],
    'subject-case': [0],
    'subject-empty': [2, 'never'],
    'subject-min-length': [2, 'always', 5],
    'subject-max-length': [2, 'always', 120],
    'type-empty': [2, 'never'],
    'header-max-length': [2, 'always', 120],
    'body-leading-blank': [1, 'always'],
  },
};
