let snapshot = null, filter = 'all', loading = false;
const $ = s => document.querySelector(s);
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const formatTime = stamp => new Intl.DateTimeFormat('en-CA', {timeZone:'America/Toronto',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}).format(new Date(stamp));
function render() {
  if (!snapshot) return;
  const query = $('#search').value.trim().toLowerCase();
  const now = Date.now();
  const passes = snapshot.passes.map(p => ({...p, fresh: !!p.checkedAt && now - Date.parse(p.checkedAt) <= 660000 && !p.error}));
  const fresh = passes.filter(p => p.fresh);
  const branchCount = new Set(fresh.flatMap(p => p.branches.filter(b => b.available > 0).map(b => b.name))).size;
  const allFresh = fresh.length === passes.length;
  $('#notice').className = allFresh ? '' : 'warning';
  $('#notice').textContent = allFresh ? `${branchCount ? `Passes available at ${branchCount} ${branchCount === 1 ? 'branch' : 'branches'}.` : 'No Rec Pass Express copies available.'} Watcher checks every 5 minutes.` : 'Availability is incomplete or out of date. Check the catalogue before travelling.';
  const visible = passes.filter(p => filter !== 'available' || (p.fresh && p.branches.some(b => b.available > 0))).filter(p => !query || p.branches.some(b => b.name.toLowerCase().includes(query)));
  visible.sort((a,b) => Number(b.fresh && b.branches.some(x=>x.available>0)) - Number(a.fresh && a.branches.some(x=>x.available>0)));
  $('#passes').innerHTML = visible.map(p => {
    const branches = p.branches.filter(b => b.available > 0 && b.name.toLowerCase().includes(query));
    const total = p.branches.reduce((sum,b)=>sum+b.available,0);
    let label = !p.checkedAt ? 'Awaiting first check' : !p.fresh ? 'Needs a fresh check' : total ? `${total} available` : 'Unavailable';
    const css = p.fresh && total ? 'available' : !p.fresh ? 'warning' : '';
    const empty = !p.checkedAt ? 'The watcher has not published a successful check yet.' : !p.fresh ? 'Current availability is unknown. Previous results may have changed.' : 'No available Rec Pass Express copies found.';
    return `<section class="pass"><div class="pass-head"><div class="pass-meta"><span>${escapeHTML(p.shortName)} · Rec Pass Express</span><span class="state ${css}">${label}</span></div><h2>${escapeHTML(p.name)}</h2><p>${escapeHTML(p.description)}</p></div>${branches.length ? `<ul class="branch-list">${branches.map(b => `<li class="branch"><div><div class="branch-name">${escapeHTML(b.name)}</div><div class="branch-detail">${b.available} ${b.available===1?'copy':'copies'} ${p.fresh ? 'available' : 'at last successful check'}</div></div><a class="directions" href="https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(`Hamilton Public Library ${b.name} branch Ontario`)}" target="_blank" rel="noopener noreferrer">Directions ↗</a></li>`).join('')}</ul>` : `<p class="empty">${empty}</p>`}${branches.length && !p.fresh ? `<p class="empty">Previous results · Confirm in the catalogue.</p>` : ''}<div class="pass-foot">${p.checkedAt ? `<time datetime="${escapeHTML(p.checkedAt)}">Checked ${escapeHTML(formatTime(p.checkedAt))}</time>` : '<span>No successful check yet</span>'}<a href="${escapeHTML(p.catalogueUrl)}" target="_blank" rel="noopener noreferrer">HPL catalogue ↗</a></div></section>`;
  }).join('') || `<div class="no-matches">${query ? 'No branches match your search.' : 'No passes have confirmed current availability.'}</div>`;
}
async function refresh() {
  if (loading) return;
  loading = true; $('#refresh').disabled = true; $('#refresh').textContent = 'Refreshing…';
  try {
    const response = await fetch('/api/status', {cache:'no-store',signal:AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error('Could not read availability');
    snapshot = await response.json(); render();
  } catch {
    if (snapshot) render();
    $('#notice').className = 'warning';
    $('#notice').textContent = 'Could not refresh results. Any displayed results are from the previous refresh. Try again or check the HPL catalogue.';
    if (!snapshot) $('#passes').innerHTML = '<div class="no-matches">Availability could not be loaded. Use Refresh results to retry.</div>';
  } finally {loading = false; $('#refresh').disabled = false; $('#refresh').textContent = 'Refresh results ↻';}
}
function setTheme(theme) {document.documentElement.dataset.theme = theme; $('#theme').textContent = theme==='dark'?'Light mode':'Dark mode';}
let savedTheme; try {savedTheme=localStorage.getItem('hpl-theme');} catch {}
setTheme(savedTheme || (matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'));
$('#theme').addEventListener('click',()=>{const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';setTheme(theme);try{localStorage.setItem('hpl-theme',theme);}catch{}});
$('#refresh').addEventListener('click',refresh);
$('#search').addEventListener('input',render);
document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{filter=button.dataset.filter;document.querySelectorAll('[data-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));render();}));
refresh();setInterval(refresh,60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
