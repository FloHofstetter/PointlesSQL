// PointlesSQL cron humanizer.
//
// Usage:
//   <span x-data="{ c: '0 0 * * *' }"
//         x-text="pqlHumanizeCron(c)"
//         :title="c">0 0 * * *</span>
//
// Handles the small set of cron shapes a user can actually compose
// from the Bootstrap create-job modal: the six '@' macros, the all-
// star minute-ticker, step-minute intervals, and integer M/H with
// '*' or integer day/month/dow fields.  Anything else falls through
// to the raw expression so the UI never lies about what's scheduled.
// bootstrap.js re-attaches the function to ``window.pqlHumanizeCron``.

const MACROS = {
  '@hourly': 'Every hour',
  '@daily': 'Daily at 00:00',
  '@midnight': 'Daily at 00:00',
  '@weekly': 'Weekly on Sunday at 00:00',
  '@monthly': 'Monthly on the 1st at 00:00',
  '@yearly': 'Yearly on Jan 1 at 00:00',
  '@annually': 'Yearly on Jan 1 at 00:00',
};

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTH_ALIAS = {
  jan: 1,
  feb: 2,
  mar: 3,
  apr: 4,
  may: 5,
  jun: 6,
  jul: 7,
  aug: 8,
  sep: 9,
  oct: 10,
  nov: 11,
  dec: 12,
};
const DOW_ALIAS = {
  sun: 0,
  mon: 1,
  tue: 2,
  wed: 3,
  thu: 4,
  fri: 5,
  sat: 6,
};

function pad2(n) {
  return n < 10 ? '0' + n : String(n);
}

function ordinal(n) {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return n + 'th';
  switch (n % 10) {
    case 1:
      return n + 'st';
    case 2:
      return n + 'nd';
    case 3:
      return n + 'rd';
    default:
      return n + 'th';
  }
}

function parseInt10(s) {
  if (!/^-?\d+$/.test(s)) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function parseMonth(s) {
  const n = parseInt10(s);
  if (n !== null) return n >= 1 && n <= 12 ? n : null;
  const alias = MONTH_ALIAS[s.toLowerCase()];
  return alias === undefined ? null : alias;
}

function parseDow(s) {
  const n = parseInt10(s);
  if (n !== null) {
    if (n === 7) return 0; // Sunday alias
    return n >= 0 && n <= 6 ? n : null;
  }
  const alias = DOW_ALIAS[s.toLowerCase()];
  return alias === undefined ? null : alias;
}

export function pqlHumanizeCron(expr) {
  if (expr == null) return '';
  const trimmed = String(expr).trim();
  if (!trimmed) return '';

  if (trimmed[0] === '@') {
    const macro = MACROS[trimmed.toLowerCase()];
    return macro || trimmed;
  }

  const parts = trimmed.split(/\s+/);
  if (parts.length !== 5) return trimmed;
  const [m, h, dom, mon, dow] = parts;

  // Step-minute form "*/N * * * *" — every N minutes.
  const stepMatch = m.match(/^\*\/(\d+)$/);
  if (stepMatch && h === '*' && dom === '*' && mon === '*' && dow === '*') {
    const n = Number(stepMatch[1]);
    if (n === 1) return 'Every minute';
    return 'Every ' + n + ' minutes';
  }

  // `* * * * *` — every minute.
  if (m === '*' && h === '*' && dom === '*' && mon === '*' && dow === '*') {
    return 'Every minute';
  }

  // From here on, minute must be an integer.
  const mNum = parseInt10(m);
  if (mNum === null || mNum < 0 || mNum > 59) return trimmed;

  // `M * * * *` — every hour at :MM.
  if (h === '*' && dom === '*' && mon === '*' && dow === '*') {
    return 'Every hour at :' + pad2(mNum);
  }

  // From here on, hour must be an integer.
  const hNum = parseInt10(h);
  if (hNum === null || hNum < 0 || hNum > 23) return trimmed;
  const time = pad2(hNum) + ':' + pad2(mNum);

  // `M H * * *` — daily.
  if (dom === '*' && mon === '*' && dow === '*') {
    return 'Daily at ' + time;
  }

  // `M H * * D` — weekly (single dow, dom/mon = *).
  if (dom === '*' && mon === '*' && dow !== '*') {
    const d = parseDow(dow);
    if (d === null) return trimmed;
    return 'Weekly on ' + DAYS[d] + ' at ' + time;
  }

  // `M H D * *` — monthly.
  if (mon === '*' && dow === '*' && dom !== '*') {
    const d = parseInt10(dom);
    if (d === null || d < 1 || d > 31) return trimmed;
    return 'Monthly on the ' + ordinal(d) + ' at ' + time;
  }

  // `M H D MON *` — yearly.
  if (dow === '*' && dom !== '*' && mon !== '*') {
    const d = parseInt10(dom);
    const mo = parseMonth(mon);
    if (d === null || d < 1 || d > 31 || mo === null) return trimmed;
    return 'Yearly on ' + MONTHS[mo - 1] + ' ' + ordinal(d) + ' at ' + time;
  }

  return trimmed;
}
