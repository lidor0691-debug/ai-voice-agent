/**
 * ╔══════════════════════════════════════════════════════════╗
 * ║  MAYA BPM — CRM Dashboard Builder v2.0 (Dynamic)        ║
 * ║  1. Extensions → Apps Script → paste this file          ║
 * ║  2. Run: buildDashboard()                                ║
 * ║  3. Re-running is safe — refreshes all sheets           ║
 * ╚══════════════════════════════════════════════════════════╝
 *
 * v2.0: Reads real headers dynamically — no hardcoded column assumptions.
 * Source sheet: 'מאיה סטודיו'
 */

// ── Configuration ────────────────────────────────────────────────
const SRC  = 'מאיה סטודיו';  // Source sheet name — exact
const CALC = 'CALCULATIONS';
const DISP = 'DISPLAY';       // Translated view — QUERY from here, not source
const DASH = 'DASHBOARD';
const VIEW = 'VIEWS';

// Quoted sheet names for use inside Sheets formula strings
const SRC_Q  = "'" + SRC  + "'";
const DISP_Q = "'" + DISP + "'";

// Column search candidates — script tries each name in order (case-insensitive)
// Add your actual Hebrew column names here if they differ
const FIND = {
  date:    ['תאריך ושעת פתיחה', 'timestamp', 'תאריך', 'date', 'created_at', 'זמן'],
  status:  ['סטטוס הרשמה', 'registration_status', 'סטטוס', 'status', 'trial1_status'],
  source:  ['מקור ליד', 'source', 'מקור', 'lead_source'],
  service: ['סוג שירות', 'service_type', 'שירות', 'service', 'interest_type'],
  name:    ['שם הורה', 'שם הילדה', 'girl_name', 'parent_name', 'שם', 'name'],
  phone:   ['טלפון הורה', 'parent_phone', 'טלפון', 'phone', 'girl_phone'],
  notes:   ['notes', 'הערות'],
};

// Status display labels — maps raw values → Hebrew display
// Add your actual status values here so the dashboard labels them correctly
const STATUS_DISPLAY = {
  'חדש':       { label: 'חדש',    color: '#2563eb' },
  'new':       { label: 'חדש',    color: '#2563eb' },
  'contacted': { label: 'בטיפול', color: '#d97706' },
  'בטיפול':    { label: 'בטיפול', color: '#d97706' },
  'נקבע':      { label: 'נקבע',   color: '#059669' },
  'closed':    { label: 'סגור',   color: '#059669' },
  'cancelled': { label: 'בוטל',   color: '#dc2626' },
  'בוטל':      { label: 'בוטל',   color: '#dc2626' },
};

// Clean Hebrew display labels for raw source values from Make.com / integrations
const SOURCE_DISPLAY = {
  'voice_realtime': 'שיחה',
  'studio':         'סטודיו',
  'whatsapp':       'וואטסאפ',
  'instagram':      'אינסטגרם',
  'facebook':       'פייסבוק',
  'call':           'טלפון',
  'referral':       'המלצה',
  'website':        'אתר',
};

// Which status value = "closed/won" (for closing rate calculation)
// Update this to match your actual "success" status value
const CLOSED_STATUS = 'נקבע';

const CLR = {
  navy:      '#1b2a4a',
  navyMid:   '#243654',
  blue:      '#2563eb',
  blueMid:   '#3b82f6',
  green:     '#059669',
  orange:    '#d97706',
  red:       '#dc2626',
  purple:    '#7c3aed',
  teal:      '#0891b2',
  bgLight:   '#f1f5f9',
  bgWhite:   '#ffffff',
  bgStripe:  '#f8fafc',
  textDark:  '#1e293b',
  textLight: '#94a3b8',
  border:    '#e2e8f0',
};

// ── Utilities ────────────────────────────────────────────────────

function colLetter(n) {
  let s = '';
  while (n > 0) { s = String.fromCharCode(65 + (n - 1) % 26) + s; n = Math.floor((n - 1) / 26); }
  return s;
}

// Strip invisible Unicode characters (RTL/LTR marks, zero-width spaces, BOM)
// that Google Sheets often embeds in Hebrew column headers
function normalize(str) {
  return String(str).trim().replace(/[\u200B-\u200D\uFEFF\u202A-\u202E\u00A0]/g, '');
}

// Read header row → returns { normalizedHeaderName: columnLetter }
function readHeaders(srcSheet) {
  const n = srcSheet.getLastColumn();
  if (!n) return {};
  const vals = srcSheet.getRange(1, 1, 1, n).getValues()[0];
  const map = {};
  vals.forEach((h, i) => { if (h) map[normalize(h)] = colLetter(i + 1); });
  return map;
}

// Find first matching column letter from candidates list
function findCol(map, candidates) {
  for (const c of candidates) {
    const normC = normalize(c);
    for (const [h, l] of Object.entries(map))
      if (normalize(h) === normC) return l;
  }
  return null;
}

// Get unique non-empty values from a column (rows 2 onward)
function uniqueVals(srcSheet, letter) {
  if (!letter) return [];
  const last = srcSheet.getLastRow();
  if (last < 2) return [];
  const vals = srcSheet.getRange(letter + '2:' + letter + last).getValues().flat();
  return [...new Set(vals.filter(v => v !== '' && v !== null))].slice(0, 30);
}

// Build a COUNTIF formula safely, returns '' if column not found
function countIf(col, val) {
  if (!col) return '';
  return `=IFERROR(COUNTIF(${SRC_Q}!${col}2:${col},"${val}"),0)`;
}

// Build a COUNTIFS for date range
function countIfDateRange(col, fromExpr, toExpr) {
  if (!col) return '';
  return `=IFERROR(COUNTIFS(${SRC_Q}!${col}2:${col},">="&${fromExpr},${SRC_Q}!${col}2:${col},"<="&${toExpr}),0)`;
}

// ── Entry point ──────────────────────────────────────────────────

function buildDashboard() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const srcSheet = ss.getSheetByName(SRC);
  if (!srcSheet) {
    SpreadsheetApp.getUi().alert('❌ Sheet "' + SRC + '" not found.\nCheck the tab name and try again.');
    return;
  }

  // Detect columns dynamically, fall back to known column letters if detection fails
  const FALLBACK = { date: 'A', source: 'B', service: 'C', status: 'N', name: 'G', phone: 'H', notes: 'O' };
  const headerMap  = readHeaders(srcSheet);
  const cols = {
    date:    findCol(headerMap, FIND.date)    || FALLBACK.date,
    status:  findCol(headerMap, FIND.status)  || FALLBACK.status,
    source:  findCol(headerMap, FIND.source)  || FALLBACK.source,
    service: findCol(headerMap, FIND.service) || FALLBACK.service,
    name:    findCol(headerMap, FIND.name)    || FALLBACK.name,
    phone:   findCol(headerMap, FIND.phone)   || FALLBACK.phone,
    notes:   findCol(headerMap, FIND.notes)   || FALLBACK.notes,
  };

  // Discover actual values in categorical columns
  const statusVals  = uniqueVals(srcSheet, cols.status);
  const sourceVals  = uniqueVals(srcSheet, cols.source);
  const serviceVals = uniqueVals(srcSheet, cols.service);

  Logger.log('Headers: ' + JSON.stringify(headerMap));
  Logger.log('Cols: ' + JSON.stringify(cols));
  Logger.log('Status values: ' + JSON.stringify(statusVals));
  Logger.log('Source values: ' + JSON.stringify(sourceVals));
  Logger.log('Service values: ' + JSON.stringify(serviceVals));

  const ctx = { cols, statusVals, sourceVals, serviceVals, headerMap };

  buildCalc(ss, ctx);
  buildDisplay(ss, srcSheet, ctx);
  buildDash(ss, ctx);
  buildViews(ss, ctx);
  reorderSheets(ss);

  SpreadsheetApp.getUi().alert(
    '✅ Dashboard built!\n\n' +
    '• DASHBOARD — main view\n' +
    '• VIEWS — operational filters\n' +
    '• CALCULATIONS — hidden helpers\n\n' +
    'Columns detected:\n' +
    '  Date:    ' + (cols.date    || '❌ not found') + '\n' +
    '  Status:  ' + (cols.status  || '❌ not found') + '\n' +
    '  Source:  ' + (cols.source  || '❌ not found') + '\n' +
    '  Service: ' + (cols.service || '❌ not found')
  );
}

// ── CALCULATIONS ─────────────────────────────────────────────────
// Fixed cell positions so DASHBOARD can reference them reliably:
//   B2  = total rows
//   B3  = today
//   B4  = this week
//   B5  = this month
//   B7  = closed count (CLOSED_STATUS)
//   B8  = closing rate
//   B10+ = status breakdown (label in A, count in B)
//   B20+ = source breakdown
//   B30+ = service breakdown

function buildCalc(ss, ctx) {
  const { cols, statusVals, sourceVals, serviceVals } = ctx;
  let s = ss.getSheetByName(CALC) || ss.insertSheet(CALC);
  s.clearContents();
  s.clearFormats();

  const totalFormula = cols.date
    ? `=IFERROR(COUNTA(${SRC_Q}!${cols.date}2:${cols.date}),0)`
    : `=IFERROR(COUNTA(${SRC_Q}!A2:A),0)`;

  const data = [
    [1, 'CALCULATIONS — נוצר אוטומטית, אין לערוך ידנית', ''],
    [2, 'סה"כ לידים',  totalFormula],
    [3, 'היום',        cols.date ? countIfDateRange(cols.date, 'TODAY()', 'TODAY()') : ''],
    [4, 'השבוע',       cols.date ? countIfDateRange(cols.date, '(TODAY()-WEEKDAY(TODAY(),2)+1)', 'TODAY()') : ''],
    [5, 'החודש',       cols.date ? countIfDateRange(cols.date, 'DATE(YEAR(TODAY()),MONTH(TODAY()),1)', 'TODAY()') : ''],
    [6, '', ''],
    [7, 'נסגרו (' + CLOSED_STATUS + ')', cols.status ? countIf(cols.status, CLOSED_STATUS) : ''],
    // Closing rate: show placeholder when no closed leads yet
    [8, 'שיעור סגירה', '=IFERROR(IF(B7=0,"—",B7/B2),"—")'],
    [9, '', ''],
  ];

  data.forEach(([row, label, formula]) => {
    s.getRange(row, 1).setValue(label);
    if (formula) s.getRange(row, 2).setFormula(formula);
  });
  s.getRange('B8').setNumberFormat('0%');

  // ── Section helpers for CALCULATIONS ──
  function calcSection(row, title) {
    s.getRange(row, 1, 1, 2).merge()
      .setValue(title)
      .setBackground(CLR.navyMid).setFontColor(CLR.bgWhite)
      .setFontWeight('bold').setFontSize(9);
  }
  function calcRow(row, label, formula) {
    s.getRange(row, 1).setValue(label).setFontColor(CLR.textDark).setFontSize(9);
    if (formula) s.getRange(row, 2).setFormula(formula)
      .setFontColor(CLR.textDark).setFontSize(9).setHorizontalAlignment('right');
    s.getRange(row, 1, 1, 2)
      .setBackground(row % 2 === 0 ? CLR.bgWhite : CLR.bgStripe);
  }

  // Status breakdown starting at row 10
  calcSection(10, 'לפי סטטוס');
  statusVals.forEach((val, i) => {
    const label = (STATUS_DISPLAY[val] && STATUS_DISPLAY[val].label) || String(val);
    calcRow(11 + i, label, cols.status ? countIf(cols.status, val) : '');
  });

  // Source breakdown starting at row 20
  calcSection(20, 'לפי מקור');
  sourceVals.forEach((val, i) => {
    const label = SOURCE_DISPLAY[String(val)] || String(val);
    calcRow(21 + i, label, cols.source ? countIf(cols.source, val) : '');
  });

  // Service breakdown starting at row 30
  calcSection(30, 'לפי שירות');
  serviceVals.forEach((val, i) => {
    calcRow(31 + i, String(val), cols.service ? countIf(cols.service, val) : '');
  });

  // Debug: column map
  calcSection(40, 'מיפוי עמודות (debug)');
  Object.entries(ctx.headerMap).forEach(([h, l], i) => {
    s.getRange(41 + i, 1).setValue(l + ' = ' + h).setFontSize(8).setFontColor(CLR.textLight);
  });

  // Formatting
  s.getRange(1, 1, 1, 2).setBackground(CLR.navy).setFontColor(CLR.bgWhite).setFontWeight('bold').setFontSize(10);
  // Style the top KPI rows (2–8)
  for (let r = 2; r <= 8; r++) {
    if (r !== 6) {
      s.getRange(r, 1).setFontColor(CLR.textDark).setFontSize(9)
        .setBackground(r % 2 === 0 ? CLR.bgWhite : CLR.bgStripe);
      s.getRange(r, 2).setFontColor(CLR.navy).setFontWeight('bold').setFontSize(9)
        .setBackground(r % 2 === 0 ? CLR.bgWhite : CLR.bgStripe)
        .setHorizontalAlignment('right');
    }
  }
  s.setColumnWidth(1, 220);
  s.setColumnWidth(2, 120);
  s.setTabColor(CLR.textLight);
  s.hideSheet();
}

// ── DISPLAY (translated view of source — QUERY reads from here) ──────────────
// Mirrors the source sheet column-by-column using ARRAYFORMULA.
// The source column (מקור ליד) is translated via IFS to Hebrew display values.
// All other columns are passed through unchanged.
// Source sheet is never modified.

function buildDisplay(ss, srcSheet, ctx) {
  const { cols } = ctx;
  let s = ss.getSheetByName(DISP);
  if (!s) s = ss.insertSheet(DISP);
  s.clearContents();
  s.clearFormats();

  const totalCols = srcSheet.getLastColumn();

  // Row 1: copy headers from source
  const srcHeaders = srcSheet.getRange(1, 1, 1, totalCols).getValues();
  s.getRange(1, 1, 1, totalCols).setValues(srcHeaders)
    .setBackground(CLR.navyMid).setFontColor(CLR.bgWhite).setFontWeight('bold').setFontSize(9);

  // Rows 2+: ARRAYFORMULA per column, translating source column
  for (let i = 1; i <= totalCols; i++) {
    const letter = colLetter(i);
    let formula;
    if (letter === cols.source) {
      // Build IFS: each known raw value → Hebrew label, fallback = raw value
      const ifsArgs = Object.entries(SOURCE_DISPLAY)
        .map(([k, v]) => `${SRC_Q}!${letter}2:${letter}="${k}","${v}"`)
        .join(',');
      formula = `=ARRAYFORMULA(IF(${SRC_Q}!${letter}2:${letter}="","",IFS(${ifsArgs},TRUE,${SRC_Q}!${letter}2:${letter})))`;
    } else {
      formula = `=ARRAYFORMULA(${SRC_Q}!${letter}2:${letter})`;
    }
    s.getRange(2, i).setFormula(formula);
  }

  s.setTabColor(CLR.textLight);
  s.hideSheet();
}

// ── DASHBOARD ────────────────────────────────────────────────────

function buildDash(ss, ctx) {
  const { cols, statusVals, sourceVals, serviceVals } = ctx;
  let s = ss.getSheetByName(DASH);
  if (!s) s = ss.insertSheet(DASH);
  s.clearContents();
  s.clearFormats();
  s.clearConditionalFormatRules();
  s.getRange(1, 1, 50, 12).breakApart();
  s.setTabColor(CLR.blue);
  s.setRightToLeft(true);

  // Columns: A=margin | B–I=content (8 cols × 148px) | J=margin
  s.setColumnWidth(1, 20);
  for (let c = 2; c <= 9; c++) s.setColumnWidth(c, 148);
  s.setColumnWidth(10, 20);

  // Row heights
  const rh = {
    1:4,  2:56, 3:24, 4:10,       // header + top spacer
    5:22, 6:52, 7:8,  8:22, 9:52, // KPI rows 1 & 2
    10:8, 11:30, 12:24,            // analytics section
    13:24,14:24,15:24,16:24,       // analytics data rows
    17:8, 18:30, 19:24,            // recent leads section
    20:22,21:22,22:22,23:22,24:22,25:22,26:22,27:22,28:22,29:22,
    30:8, 31:30, 32:24,            // follow-up section
    33:22,34:22,35:22,36:22,37:22,38:22,39:22,40:22,41:22,42:22,
    43:14,
  };
  Object.entries(rh).forEach(([r, h]) => s.setRowHeight(+r, h));

  // Background
  s.getRange(1, 1, 44, 10).setBackground(CLR.bgLight);
  s.getRange(1, 1, 44, 1).setBackground(CLR.bgLight);
  s.getRange(1, 10, 44, 1).setBackground(CLR.bgLight);
  s.getRange(1, 1, 1, 10).setBackground(CLR.blueMid); // accent strip

  // Header
  s.getRange(2, 2, 1, 8).merge()
    .setValue('📊 לוח בקרה  —  מאיה BPM Dance Studio')
    .setBackground(CLR.navy).setFontColor(CLR.bgWhite)
    .setFontSize(19).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');

  // Subtitle with live timestamp
  s.getRange(3, 2, 1, 8).merge()
    .setFormula('="עודכן: "&TEXT(NOW(),"dd/mm/yyyy  HH:mm")')
    .setBackground(CLR.navyMid).setFontColor(CLR.textLight)
    .setFontSize(9).setHorizontalAlignment('center').setVerticalAlignment('middle');

  // Spacers
  [4, 7, 10, 17, 30].forEach(r =>
    s.getRange(r, 2, 1, 8).setBackground(CLR.bgLight));

  // ── KPI Row 1: Total | Today | This Month | Closed ───────────
  [
    { label: 'סה"כ לידים',  val: '=IFERROR(CALCULATIONS!B2,0)',                bg: CLR.navy   },
    { label: 'היום',         val: '=IFERROR(CALCULATIONS!B3,0)',                bg: CLR.teal   },
    { label: 'החודש',        val: '=IFERROR(CALCULATIONS!B5,0)',                bg: CLR.orange },
    { label: 'שיעור סגירה',  val: '=IF(CALCULATIONS!B7=0,"אין נתונים",IFERROR(TEXT(CALCULATIONS!B8,"0%"),"—"))',   bg: CLR.purple },
  ].forEach((k, i) => kpiCard(s, 5, 6, 2 + i * 2, k.label, k.val, k.bg));

  // ── KPI Row 2: This Week + top 3 status counts ───────────────
  const kpi2Base = [
    { label: 'השבוע',  val: '=IFERROR(CALCULATIONS!B4,0)', bg: CLR.blue },
  ];
  // Fill remaining 3 slots with discovered status values (rows 11, 12, 13 in CALCULATIONS)
  statusVals.slice(0, 3).forEach((val, i) => {
    const displayLabel = (STATUS_DISPLAY[val] && STATUS_DISPLAY[val].label) || String(val);
    const displayColor = (STATUS_DISPLAY[val] && STATUS_DISPLAY[val].color) || CLR.blue;
    kpi2Base.push({
      label: displayLabel,
      val:   '=IFERROR(CALCULATIONS!B' + (11 + i) + ',0)',
      bg:    displayColor,
    });
  });
  // Pad to 4 cards if fewer statuses found
  while (kpi2Base.length < 4) kpi2Base.push({ label: '—', val: '"—"', bg: CLR.navyMid });
  kpi2Base.slice(0, 4).forEach((k, i) => kpiCard(s, 8, 9, 2 + i * 2, k.label, k.val, k.bg));

  // ── Analytics: Source table (B:D) and Service table (F:H) ────
  secHeader(s.getRange(11, 2, 1, 8).merge(), 'מקורות ליד וסוגי שירות');

  tblHeader(s, 12, 2, ['מקור', 'לידים', '%']);
  sourceVals.slice(0, 4).forEach((val, i) => {
    s.getRange(13 + i, 2).setValue(SOURCE_DISPLAY[String(val)] || String(val));
    s.getRange(13 + i, 3).setFormula('=IFERROR(CALCULATIONS!B' + (21 + i) + ',0)');
    s.getRange(13 + i, 4).setFormula('=IFERROR(CALCULATIONS!B' + (21 + i) + '/CALCULATIONS!B2,0)').setNumberFormat('0%');
  });
  if (sourceVals.length) tblRows(s, 13, 2, Math.min(sourceVals.length, 4), 3);

  s.getRange(12, 5, 5, 1).setBackground(CLR.bgLight); // spacer col E

  tblHeader(s, 12, 6, ['שירות', 'לידים', '%']);
  serviceVals.slice(0, 4).forEach((val, i) => {
    s.getRange(13 + i, 6).setValue(String(val));
    s.getRange(13 + i, 7).setFormula('=IFERROR(CALCULATIONS!B' + (31 + i) + ',0)');
    s.getRange(13 + i, 8).setFormula('=IFERROR(CALCULATIONS!B' + (31 + i) + '/CALCULATIONS!B2,0)').setNumberFormat('0%');
  });
  if (serviceVals.length) tblRows(s, 13, 6, Math.min(serviceVals.length, 4), 3);
  s.getRange(12, 9, 5, 1).setBackground(CLR.bgLight);

  // ── Recent Leads ─────────────────────────────────────────────
  secHeader(s.getRange(18, 2, 1, 8).merge(), 'לידים אחרונים');

  const selectCols  = buildSelectCols(ctx);
  const headerLabels = buildHeaderLabels(ctx);
  tblHeader(s, 19, 2, headerLabels);

  s.getRange(20, 2).setFormula(
    `=IFERROR(QUERY(${DISP_Q}!A:ZZ,"SELECT ${selectCols} ORDER BY A DESC LIMIT 10 LABEL ${buildLabelClause(selectCols)}",1),{"אין נתונים","","","","","",""})`
  );
  tblRows(s, 20, 2, 10, headerLabels.length);
  if (cols.date) s.getRange(20, 2, 10, 1).setNumberFormat('dd/mm/yy HH:mm');
  const statusColInResult = getStatusColInResult(ctx);
  if (statusColInResult) applyStatusCF(s, 20, statusColInResult, 10);

  // ── Follow-up needed ─────────────────────────────────────────
  secHeader(s.getRange(31, 2, 1, 8).merge(), 'ממתינים לטיפול');
  tblHeader(s, 32, 2, headerLabels);

  const followupWhere = buildFollowupWhere(ctx);

  s.getRange(33, 2).setFormula(
    followupWhere
      ? `=IFERROR(QUERY(${DISP_Q}!A:ZZ,"SELECT ${selectCols} WHERE ${followupWhere} ORDER BY A DESC LIMIT 10 LABEL ${buildLabelClause(selectCols)}",1),{"אין לידים פתוחים","","","","","",""})`
      : `=IFERROR(QUERY(${DISP_Q}!A:ZZ,"SELECT ${selectCols} ORDER BY A DESC LIMIT 10 LABEL ${buildLabelClause(selectCols)}",1),{"אין נתונים","","","","","",""})`
  );
  tblRows(s, 33, 2, 10, headerLabels.length);
  if (cols.date) s.getRange(33, 2, 10, 1).setNumberFormat('dd/mm/yy HH:mm');
  if (statusColInResult) applyStatusCF(s, 33, statusColInResult, 10);

  // Trim extra rows/cols
  const maxR = s.getMaxRows(); if (maxR > 44) s.hideRows(44, maxR - 44);
  const maxC = s.getMaxColumns(); if (maxC > 10) s.hideColumns(11, maxC - 10);
}

// Build SELECT clause using real column letters (up to 7 useful columns)
function buildSelectCols(ctx) {
  const { cols } = ctx;
  const picks = [cols.date, cols.name, cols.phone, cols.status, cols.service, cols.source, cols.notes]
    .filter(Boolean)
    .slice(0, 7);
  // Always include at least col A if nothing found
  return picks.length ? picks.join(',') : 'A,B,C,D,E,F,G';
}

// Hebrew header labels matching the SELECT columns
function buildHeaderLabels(ctx) {
  const { cols } = ctx;
  const map = {
    [cols.date]:    'תאריך',
    [cols.name]:    'שם',
    [cols.phone]:   'טלפון',
    [cols.status]:  'סטטוס',
    [cols.service]: 'שירות',
    [cols.source]:  'מקור',
    [cols.notes]:   'הערות',
  };
  const picks = [cols.date, cols.name, cols.phone, cols.status, cols.service, cols.source, cols.notes]
    .filter(Boolean).slice(0, 7);
  const labels = picks.map(c => map[c] || c);
  // Pad to 7 with '' for the header row
  while (labels.length < 7) labels.push('');
  return labels;
}

// LABEL clause to strip auto-headers from QUERY
function buildLabelClause(selectCols) {
  return selectCols.split(',').map(c => c.trim() + " ''").join(',');
}

// Which column position (1-based within result) holds status — for conditional formatting
function getStatusColInResult(ctx) {
  const { cols } = ctx;
  const picks = [cols.date, cols.name, cols.phone, cols.status, cols.service, cols.source, cols.notes]
    .filter(Boolean).slice(0, 7);
  const idx = picks.indexOf(cols.status);
  return idx === -1 ? null : 2 + idx; // +2 because col B = column index 2 in sheet
}

// WHERE clause for "needs follow-up": any status that isn't closed/cancelled
function buildFollowupWhere(ctx) {
  const { cols, statusVals } = ctx;
  if (!cols.status || !statusVals.length) return null;
  const openVals = statusVals.filter(v =>
    !['נקבע','closed','cancelled','בוטל'].includes(String(v).toLowerCase())
  );
  if (!openVals.length) return null;
  return openVals.map(v => `${cols.status}='${v}'`).join(' OR ');
}

// ── VIEWS ────────────────────────────────────────────────────────

function buildViews(ss, ctx) {
  const { cols, statusVals } = ctx;
  let s = ss.getSheetByName(VIEW);
  if (!s) s = ss.insertSheet(VIEW);
  s.clearContents();
  s.clearFormats();
  s.clearConditionalFormatRules();
  s.setTabColor(CLR.green);
  s.setRightToLeft(true);

  s.getRange(1, 1, 220, 8).setBackground(CLR.bgLight);
  for (let c = 1; c <= 8; c++) s.setColumnWidth(c, 148);

  s.setRowHeight(1, 42);
  s.getRange(1, 1, 1, 8).merge()
    .setValue('תצוגות תפעוליות  |  מאיה BPM')
    .setBackground(CLR.navy).setFontColor(CLR.bgWhite)
    .setFontSize(14).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');

  const selectCols  = buildSelectCols(ctx);
  const labelClause = buildLabelClause(selectCols);
  const headerLabels = buildHeaderLabels(ctx);
  const followupWhere = buildFollowupWhere(ctx);

  const sections = [
    {
      row: 3, bg: CLR.blue, label: '🟢 לידים פעילים',
      where: followupWhere,
    },
    // One section per discovered status value
    ...statusVals.map((val, i) => ({
      row: 60 + i * 57,
      bg: (STATUS_DISPLAY[val] && STATUS_DISPLAY[val].color) || CLR.navyMid,
      label: (STATUS_DISPLAY[val] && STATUS_DISPLAY[val].label) || String(val),
      where: cols.status ? `${cols.status}='${val}'` : null,
    })),
  ];

  sections.forEach(sec => {
    s.setRowHeight(sec.row, 32);
    s.setRowHeight(sec.row + 1, 26);

    s.getRange(sec.row, 1, 1, 8).merge()
      .setValue(sec.label)
      .setBackground(sec.bg).setFontColor(CLR.bgWhite)
      .setFontSize(11).setFontWeight('bold')
      .setHorizontalAlignment('right').setVerticalAlignment('middle');

    tblHeader(s, sec.row + 1, 1, headerLabels);

    const query = sec.where
      ? `SELECT ${selectCols} WHERE ${sec.where} ORDER BY A DESC LIMIT 50 LABEL ${labelClause}`
      : `SELECT ${selectCols} ORDER BY A DESC LIMIT 50 LABEL ${labelClause}`;

    s.getRange(sec.row + 2, 1).setFormula(
      `=IFERROR(QUERY(${DISP_Q}!A:ZZ,"${query}",1),{"אין נתונים","","","","","",""})`
    );
    if (cols.date) s.getRange(sec.row + 2, 1, 50, 1).setNumberFormat('dd/mm/yy HH:mm');
  });
}

// ── Shared helpers ───────────────────────────────────────────────

function kpiCard(s, labelRow, valRow, startCol, label, formula, bg) {
  s.getRange(labelRow, startCol, 1, 2).merge()
    .setValue(label)
    .setBackground(bg).setFontColor('#c8d8f0')
    .setFontSize(9).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  s.getRange(valRow, startCol, 1, 2).merge()
    .setFormula(formula)
    .setBackground(bg).setFontColor(CLR.bgWhite)
    .setFontSize(26).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
}

function secHeader(range, text) {
  range.setValue(text)
    .setBackground(CLR.navy).setFontColor(CLR.bgWhite)
    .setFontSize(10).setFontWeight('bold')
    .setHorizontalAlignment('right').setVerticalAlignment('middle');
}

function tblHeader(s, row, startCol, labels) {
  s.setRowHeight(row, 26);
  s.getRange(row, startCol, 1, labels.length)
    .setValues([labels])
    .setBackground(CLR.navyMid).setFontColor(CLR.bgWhite)
    .setFontSize(10).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
}

function tblRows(s, startRow, startCol, numRows, numCols) {
  for (let i = 0; i < numRows; i++) {
    s.getRange(startRow + i, startCol, 1, numCols)
      .setBackground(i % 2 === 0 ? CLR.bgWhite : CLR.bgStripe)
      .setFontSize(9).setFontColor(CLR.textDark)
      .setVerticalAlignment('middle')
      .setBorder(false, false, true, false, false, false,
        CLR.border, SpreadsheetApp.BorderStyle.SOLID);
  }
}

function applyStatusCF(s, startRow, statusCol, numRows) {
  const rules = s.getConditionalFormatRules();
  const range = s.getRange(startRow, statusCol, numRows, 1);
  [
    { val: 'נקבע',      bg: '#d1fae5', text: '#065f46' },
    { val: 'closed',    bg: '#d1fae5', text: '#065f46' },
    { val: 'חדש',       bg: '#dbeafe', text: '#1e40af' },
    { val: 'new',       bg: '#dbeafe', text: '#1e40af' },
    { val: 'contacted', bg: '#fef3c7', text: '#92400e' },
    { val: 'בטיפול',    bg: '#fef3c7', text: '#92400e' },
    { val: 'cancelled', bg: '#fee2e2', text: '#991b1b' },
    { val: 'בוטל',      bg: '#fee2e2', text: '#991b1b' },
  ].forEach(st => {
    rules.push(
      SpreadsheetApp.newConditionalFormatRule()
        .whenTextEqualTo(st.val)
        .setBackground(st.bg).setFontColor(st.text)
        .setRanges([range]).build()
    );
  });
  s.setConditionalFormatRules(rules);
}

function reorderSheets(ss) {
  [DASH, VIEW, SRC, DISP, CALC].forEach((name, pos) => {
    const s = ss.getSheetByName(name);
    if (s) { ss.setActiveSheet(s); ss.moveActiveSheet(pos + 1); }
  });
}

function debugHeaders() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const s = ss.getSheetByName('מאיה סטודיו');
  const n = s.getLastColumn();
  const vals = s.getRange(1, 1, 1, n).getValues()[0];
  Logger.log(vals.map((h, i) => colLetter(i+1) + ' = ' + h).join('\n'));
}
