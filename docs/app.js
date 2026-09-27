import { $, bars, esc, fail, int, kpis, load, pct, seg, select } from './kit.js';

const OK = new Set(['ok']);
const report = (md) => md.split('\n').map((line) => {
  let h = esc(line).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(https:\/\/pypi\.org\/project\/[^\s)]+)/g, '<a href="$1">$1</a>');
  if (line.startsWith('# ')) return `<h3 style="margin:0 0 8px">${h.slice(2)}</h3>`;
  return line.trim() ? `<p style="margin:4px 0">${h}</p>` : '';
}).join('');

try {
  const d = await load();
  const B = d.bench_runs, sum = (k) => B.reduce((a, r) => a + r[k], 0);
  const tokens = B.map((r) => r.tokens).sort((a, b) => a - b);
  kpis($('#kpis'), [
    { label: 'Sub-questions answered', value: pct(sum('answered') / sum('subquestions')), note: `tools failing 15% of the time; ${int(sum('subquestions') - sum('answered'))} gaps named in the reports` },
    { label: 'Claims matching their source', value: `${int(sum('correct'))}/${int(sum('answered'))}`, note: 'each cited to the page it came from' },
    { label: 'Killed and resumed', value: `${d.summary.resumed_same}/20`, note: 'ended with the same report and path' },
    { label: 'Tokens per run', value: int(tokens[Math.floor((tokens.length - 1) / 2)]), note: `median; ceiling ${int(d.budget.max_tokens)}, never reached` },
  ]);
  let qi = 0, rate = '0.15', at = 0, timer = 0;
  function draw() {
    const r = d.runs[rate][qi], upto = r.trace.slice(0, at);
    $('#trace').innerHTML = r.trace.map((t, i) => `<button type="button" class="step${i < at ? ' on' : ''}" data-i="${i + 1}" title="${esc(t.status)}">${esc(t.node)}${t.node === 'researcher' ? ` · ${esc(t.status)}` : ''}</button>`).join('');
    const spent = upto.reduce((a, t) => a + t.tokens, 0), last = upto[upto.length - 1];
    $('#meter').innerHTML = `<div>Step<b>${at} of ${r.trace.length}</b><span class="muted small">${last ? `${esc(last.node)}: ${esc(last.status)}` : 'not started'}</span></div>` +
      `<div>Tokens metered<b>${int(spent)}</b><span class="muted small">of a ${int(d.budget.max_tokens)} ceiling</span></div>` +
      `<div>Outcome<b>${at === r.trace.length ? esc(r.status) : 'running'}</b><span class="muted small">${r.attempts.filter((a) => OK.has(a.status)).length} of ${r.attempts.length} sub-questions answered</span></div>`;
    // researcher steps run the pending sub-questions in order: the first pass takes each once, then the
    // send-back takes the retryable ones, again in order; so the trace says what each one did and when
    const n = r.attempts.length, again = r.attempts.flatMap((a, i) => (a.retried ? [i] : []));
    const state = r.attempts.map(() => null);
    upto.filter((t) => t.node === 'researcher').forEach((t, j) => { const i = j < n ? j : again[j - n]; if (i != null) state[i] = { status: t.status, second: j >= n }; });
    const done = r.trace.length === at;
    $('#subs').innerHTML = `<div class="grid3">${r.attempts.map((a, i) => {
      const st = state[i], cls = !st ? 'mid' : OK.has(st.status) ? 'ok' : 'no';
      return `<button type="button" class="box sub" data-i="${i}" style="text-align:left;cursor:pointer"><b>${esc(a.entity)}</b> · ${esc(a.aspect)}<br><span class="pill ${cls}">${st ? esc(st.status.replace('_', ' ')) : 'waiting'}</span> <span class="muted small">${st?.second ? 'after the send-back' : ''}</span>${st && OK.has(st.status) && a.value ? `<br><span class="small">${esc(a.value)}</span>` : ''}</button>`;
    }).join('')}</div>`;
    $('#report').innerHTML = done ? report(r.report) : '<span class="muted">The writer runs last.</span>';
  }
  function play() {
    clearInterval(timer);
    at = 0; draw();
    timer = setInterval(() => { const n = d.runs[rate][qi].trace.length; at = Math.min(n, at + 1); draw(); if (at >= n) clearInterval(timer); }, 350);
  }
  const eventful = d.runs['0.15'].findIndex((r) => r.attempts.some((a) => a.retried || a.status !== 'ok'));
  select($('#qsel'), d.runs['0.15'].map((r, i) => [i, r.question]), Math.max(0, eventful), (i) => { qi = +i; play(); });
  seg($('#rate'), [['0.0', '0%'], ['0.15', '15%'], ['0.4', '40%']], rate, (v) => { rate = v; play(); });
  $('#play').onclick = play;
  $('#trace').onclick = (e) => { const b = e.target.closest('button[data-i]'); if (b) { clearInterval(timer); at = +b.dataset.i; draw(); } };
  $('#subs').onclick = (e) => {
    const b = e.target.closest('button.sub'); if (!b) return;
    const a = d.runs[rate][qi].attempts[+b.dataset.i];
    $('#log').innerHTML = `${esc(a.entity)} · ${esc(a.aspect)}: ` + a.log.map(([what, arg, st]) => `${esc(what)} <code>${esc(String(arg).replace('https://pypi.org/project/', '…/'))}</code> → ${esc(st)}`).join('; ');
  };
  const S = d.summary.sweep;
  bars($('#sweep'), Object.entries(S).map(([r, x]) => ({ label: `tools fail ${Math.round(100 * r)}%`, value: x.answered, text: `${pct(x.answered)} answered · ${int(x.tokens)} tokens`, color: +r > 0.2 ? 'var(--bad)' : 'var(--accent)' })), { max: 1 });
} catch (err) {
  fail(err);
}
