/* Content Robot — tương tác phía trình duyệt (không phụ thuộc thư viện) */
(function () {
  const t = document.getElementById('toast');
  if (t) setTimeout(() => t.remove(), 4200);
  if (location.search.includes('ok=')) history.replaceState(null, '', location.pathname + location.search.replace(/[?&]ok=[^&]*/, '').replace(/^&/, '?'));
})();

function initCalendar() {
  const C = window.CAL, body = document.getElementById('cBody'), title = document.getElementById('cTitle');
  const pop = document.getElementById('cPop');
  const DOW = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];
  const MON = ['Tháng 1', 'Tháng 2', 'Tháng 3', 'Tháng 4', 'Tháng 5', 'Tháng 6', 'Tháng 7', 'Tháng 8', 'Tháng 9', 'Tháng 10', 'Tháng 11', 'Tháng 12'];
  const H0 = 6, H1 = 24, PX = 56;
  const show = { facebook: true, pinterest: true };
  let view = 'week';
  let cur = parseD(C.today);

  function parseD(s) { const [y, m, d] = s.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d)); }
  function iso(d) { return d.toISOString().slice(0, 10); }
  function addD(d, n) { const x = new Date(d); x.setUTCDate(x.getUTCDate() + n); return x; }
  function monday(d) { const w = (d.getUTCDay() + 6) % 7; return addD(d, -w); }
  function mins(hm) { const [h, m] = hm.split(':').map(Number); return h * 60 + m; }
  function esc(s) { return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
  function evs() { return C.events.filter(e => show[e.ch]); }
  const chCls = ch => ch === 'facebook' ? 'fb' : 'pin';
  const chName = ch => ch === 'facebook' ? 'Facebook' : 'Pinterest';
  const stIcon = st => st === 'published' ? '✓' : (st === 'failed' ? '!' : '⏱');

  function renderWeek() {
    const m0 = monday(cur), days = [...Array(7)].map((_, i) => addD(m0, i));
    const end = days[6];
    title.textContent = `${days[0].getUTCDate()} – ${end.getUTCDate()} ${MON[end.getUTCMonth()]}, ${end.getUTCFullYear()}`;
    const H = (H1 - H0) * PX;
    let html = '<div class="wk"><div class="dh" style="border-right:1px solid var(--line)"></div>';
    days.forEach((d, i) => {
      const today = iso(d) === C.today;
      html += `<div class="dh ${today ? 'today' : ''}"><div class="dn">${DOW[i]}</div><div class="dd">${d.getUTCDate()}</div></div>`;
    });
    html += `<div class="gut" style="height:${H}px">`;
    for (let h = H0 + 1; h < H1; h++) html += `<span style="top:${(h - H0) * PX}px">${String(h).padStart(2, '0')}:00</span>`;
    html += '</div>';
    const slotM = [...new Set(Object.values(C.slots).flat())].map(mins);
    days.forEach(d => {
      const ds = iso(d), today = ds === C.today;
      html += `<div class="col ${today ? 'today' : ''}" style="height:${H}px">`;
      for (let h = H0 + 1; h < H1; h++) html += `<div class="hr" style="top:${(h - H0) * PX}px"></div>`;
      slotM.forEach(m => html += `<div class="gold" style="top:${(m / 60 - H0) * PX}px;height:${PX / 2}px" title="Khung giờ vàng"></div>`);
      if (today) html += `<div class="now" style="top:${(mins(C.now) / 60 - H0) * PX}px"></div>`;
      const list = evs().filter(e => e.d === ds).sort((a, b) => mins(a.t) - mins(b.t));
      const lanes = [];
      list.forEach(e => {
        const s0 = mins(e.t); let lane = 0;
        while (lanes[lane] !== undefined && lanes[lane] > s0) lane++;
        lanes[lane] = s0 + 30; e._lane = lane;
      });
      const n = Math.max(1, lanes.length);
      list.forEach(e => {
        const top = (mins(e.t) / 60 - H0) * PX, w = 100 / n;
        html += `<div class="ev ${chCls(e.ch)} ${e.st}" data-id="${e.id}" title="${esc(e.title)}" style="top:${top + 1}px;height:${PX / 2 - 2}px;left:calc(${e._lane * w}% + 3px);width:calc(${w}% - 6px)">
          ${e.img ? `<img src="${esc(e.img)}" alt="">` : ''}<span class="tm">${e.t}</span><span class="tt">${stIcon(e.st)} ${esc(e.title)}</span></div>`;
      });
      html += '</div>';
    });
    body.innerHTML = html + '</div>';
    const nowEl = body.querySelector('.now');
    const tops = [...body.querySelectorAll('.ev')].map(x => x.offsetTop).concat(nowEl ? [nowEl.offsetTop] : []);
    const anchor = tops.length ? Math.min(...tops) : 9e9;
    body.scrollTop = anchor < 9e9 ? Math.max(0, anchor - 90) : 3 * PX;
  }

  function renderMonth() {
    const y = cur.getUTCFullYear(), m = cur.getUTCMonth();
    title.textContent = `${MON[m]}, ${y}`;
    const first = new Date(Date.UTC(y, m, 1)), start = monday(first);
    let html = '<div class="mo">' + DOW.map(d => `<div class="mh">${d}</div>`).join('');
    for (let i = 0; i < 42; i++) {
      const d = addD(start, i), ds = iso(d), out = d.getUTCMonth() !== m;
      const list = evs().filter(e => e.d === ds).sort((a, b) => mins(a.t) - mins(b.t));
      html += `<div class="md ${out ? 'out' : ''} ${ds === C.today ? 'today' : ''}"><div class="num">${d.getUTCDate()}</div>`;
      list.slice(0, 3).forEach(e => html += `<div class="ch ${chCls(e.ch)}" data-id="${e.id}"><span class="badge-ch ${chCls(e.ch)}" style="width:15px;height:15px;font-size:9px;border-radius:4px">${e.ch === 'facebook' ? 'f' : 'P'}</span><b>${e.t}</b><span>${esc(e.title)}</span></div>`);
      if (list.length > 3) html += `<div class="more">+${list.length - 3} bài nữa</div>`;
      html += '</div>';
      if (i >= 34 && addD(start, i + 1).getUTCMonth() !== m && (i + 1) % 7 === 0) break;
    }
    body.innerHTML = html + '</div>';
  }

  function render() { pop.classList.remove('on'); view === 'week' ? renderWeek() : renderMonth(); }

  body.addEventListener('click', ev => {
    const el = ev.target.closest('[data-id]');
    if (!el) return;
    const e = C.events.find(x => String(x.id) === el.dataset.id);
    const r = el.getBoundingClientRect();
    pop.innerHTML = `${e.img ? `<img src="${esc(e.img)}" alt="">` : ''}
      <div style="display:flex;gap:8px;align-items:center;margin-top:10px"><span class="badge-ch ${chCls(e.ch)}">${e.ch === 'facebook' ? 'f' : 'P'}</span><b>${chName(e.ch)}</b><span class="chip ${e.st === 'published' ? 'ok' : 'info'}" style="margin-left:auto">${esc(e.stl)}</span></div>
      <h4>${esc(e.title)}</h4><div class="small muted">${e.t} · ${e.d.split('-').reverse().join('/')}</div>
      <div style="display:flex;gap:8px;margin-top:12px"><a class="btn sm pri" href="/bai/${e.aid}">Mở bản xem trước</a><button class="btn sm" onclick="this.closest('.pop').classList.remove('on')">Đóng</button></div>`;
    const left = Math.min(window.innerWidth - 360, r.right + 10), top = Math.min(window.innerHeight - 330, Math.max(10, r.top - 20));
    pop.style.left = left + 'px'; pop.style.top = top + 'px'; pop.classList.add('on');
    ev.stopPropagation();
  });
  document.addEventListener('click', ev => { if (!ev.target.closest('.pop')) pop.classList.remove('on'); });
  document.querySelectorAll('.seg button').forEach(b => b.onclick = () => {
    document.querySelectorAll('.seg button').forEach(x => x.classList.toggle('on', x === b)); view = b.dataset.v; render();
  });
  document.querySelectorAll('.flt label').forEach(l => l.onclick = ev => {
    ev.preventDefault(); show[l.dataset.ch] = !show[l.dataset.ch]; l.classList.toggle('off', !show[l.dataset.ch]); render();
  });
  document.getElementById('cToday').onclick = () => { cur = parseD(C.today); render(); };
  document.getElementById('cPrev').onclick = () => { cur = view === 'week' ? addD(cur, -7) : new Date(Date.UTC(cur.getUTCFullYear(), cur.getUTCMonth() - 1, 1)); render(); };
  document.getElementById('cNext').onclick = () => { cur = view === 'week' ? addD(cur, 7) : new Date(Date.UTC(cur.getUTCFullYear(), cur.getUTCMonth() + 1, 1)); render(); };
  render();
}

function filterCards(q) {
  q = q.toLowerCase();
  document.querySelectorAll('[data-q]').forEach(el => el.style.display = el.dataset.q.includes(q) ? '' : 'none');
}
