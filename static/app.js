const $ = s => document.querySelector(s);
let lessons = [], modules = [], current = null, configured = false, filter = 'all', timer, lastSaved = 0, switching = false, syncing = false;
let cacheTimer, preparedPlayback = false;
let courses = [], selectedCourse = null, courseGeneration = 0, syncTimer;
let positionDirty = false;
let materials = [];
const video = $('#video');
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clock = n => { n = Math.floor(n || 0); return `${Math.floor(n / 60)}:${String(n % 60).padStart(2,'0')}`; };
const code = n => n ? `#F${String(n).padStart(2,'0')}` : 'Extra';
const coursePath = (path, id = selectedCourse?.id || 'autodidata') => `${path}?course_id=${encodeURIComponent(id)}`;
const indexedCourse = () => ['autodidata','indexed'].includes(selectedCourse?.layout);
const courseTotal = () => selectedCourse?.total ?? lessons.length;
const lessonLabel = l => selectedCourse?.layout === 'autodidata' ? code(l.number) : (l.tags.find(t => /^#f\d+$/i.test(t))?.toUpperCase() || `Aula ${lessons.findIndex(item => item.id === l.id) + 1}`);
function toast(text, error = false) { const el = $('#toast'); clearTimeout(timer); el.textContent = text; el.className = error ? 'error' : ''; el.hidden = false; timer = setTimeout(() => el.hidden = true, 7000); }
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {'Content-Type':'application/json','X-Trilha-Local':'1',...options.headers}});
  if (!response.ok) { let data; try { data = await response.json(); } catch {} throw Error(typeof data?.detail === 'string' ? data.detail : `Falha na operação (${response.status}).`); }
  return response.json();
}
function completedNumbers(items = lessons) { return [...new Set(items.filter(l => l.number).map(l => l.number))].filter(n => items.filter(l => l.number === n).every(l => l.completed)); }
function courseDone() { return indexedCourse() ? completedNumbers().length : lessons.filter(l => l.completed).length; }
function updateProgress() {
  const done = courseDone(), total = courseTotal(), percent = total ? Math.round(done / total * 100) : 0;
  $('#progress-count').textContent = `${done} de ${total} aulas concluídas`;
  $('#progress-bar').style.width = `${percent}%`;
  $('#percent').innerHTML = `${percent}<span>%</span>`;
  $('#library-count').textContent = `${modules.length} módulos · ${lessons.length} vídeos importados`;
  $('#course-count').textContent = total || '—';
  $('#cover-footer').textContent = `${modules.length} MÓDULOS · ${total ? `${total} AULAS` : 'AGUARDANDO IMPORTAÇÃO'}`;
  $('#complete').textContent = current?.completed ? '✓ Aula concluída' : '✓ Marcar como concluída';
  $('#complete').disabled = !current;
  const idx = lessons.findIndex(l => l.id === current?.id);
  $('#previous').disabled = idx <= 0;
  $('#next').disabled = idx < 0 || idx >= lessons.length - 1;
}
function render() {
  const query = $('#search').value.trim().toLowerCase();
  const opened = new Set([...document.querySelectorAll('.module[open]')].map(el => el.dataset.module));
  const visible = lessons.filter(l => (filter === 'all' || (filter === 'done' ? l.completed : !l.completed)) &&
    (!query || `${lessonLabel(l)} ${l.title} ${l.filename} ${l.tags.join(' ')}`.toLowerCase().includes(query)));
  const groups = [...modules];
  if (lessons.some(l => l.module === 'extras')) groups.push({code:'extras',name:'Outros vídeos do canal',start:0,end:0});
  $('#lesson-list').innerHTML = groups.map(m => {
    const all = lessons.filter(l => l.module === m.code), items = visible.filter(l => l.module === m.code);
    if ((query || filter !== 'all') && !items.length) return '';
    const completed = indexedCourse() && m.code !== 'extras' ? completedNumbers(all).length : all.filter(l => l.completed).length;
    const total = m.code === 'extras' ? all.length : m.total;
    const open = opened.has(m.code) || current?.module === m.code || (!current && !opened.size && m.code === groups[0]?.code) || query;
    const badge = m.code.startsWith('g-') ? groups.indexOf(m) + 1 : m.code === 'extras' ? '+' : m.code;
    const missing = selectedCourse?.synced_at && m.start && !query && filter !== 'done' ? Array.from({length:m.end-m.start+1},(_,i)=>m.start+i).filter(n=>!all.some(l=>l.number===n)) : [];
    return `<details class="module" data-module="${esc(m.code)}" ${open ? 'open' : ''}><summary><span>${esc(badge)}</span><strong>${esc(m.name)}</strong><small>${completed}/${total}</small></summary>${items.map(l => `<div class="lesson-row ${l.id === current?.id ? 'current' : ''}"><button class="lesson-open" data-id="${esc(l.id)}" aria-label="Assistir ${esc(lessonLabel(l))} ${esc(l.title)}"><span class="lesson-symbol">${l.id === current?.id ? '▶' : '▷'}</span><span><strong>${esc(l.title)}</strong><small>${esc(lessonLabel(l))} <span>·</span> ${clock(l.duration)}${l.position > 0 && !l.completed ? ` · parou em ${clock(l.position)}` : ''}</small></span></button><button class="lesson-check ${l.completed ? 'done' : ''}" data-check="${esc(l.id)}" aria-label="${l.completed ? 'Desmarcar' : 'Concluir'} ${esc(lessonLabel(l))}" aria-pressed="${l.completed}">${l.completed ? '✓' : ''}</button></div>`).join('')}${missing.length ? `<div class="missing index-gap">No índice: ${missing.map(n => '#F'+String(n).padStart(selectedCourse.layout === 'autodidata' ? 2 : 3,'0')).join(', ')} · ainda não encontrada no canal.</div>` : ''}${!items.length ? '<div class="missing">Aguardando sincronização do Telegram.</div>' : ''}</details>`;
  }).join('') || `<p class="missing">${lessons.length ? 'Nenhuma aula encontrada com este filtro.' : 'Clique em Sincronizar Telegram para importar as aulas deste curso.'}</p>`;
  updateProgress();
}
async function savePosition(keepalive = false) {
  if (!positionDirty || !current || switching || video.readyState === 0 || !Number.isFinite(video.currentTime) || !video.getAttribute('src')) return;
  const position = video.currentTime;
  current.position = position;
  const id = current.id;
  positionDirty = false;
  lastSaved = Date.now();
  try { await api(`/api/lessons/${id}`, {method:'PATCH',body:JSON.stringify({position}),keepalive}); }
  catch (error) { if (current?.id === id) positionDirty = true; if (!keepalive) toast(`Progresso não salvo: ${error.message}`, true); }
}
async function selectLesson(id) {
  const lesson = lessons.find(l => l.id === id);
  if (!lesson) return;
  await savePosition();
  switching = true;
  video.pause();
  current = lesson;
  positionDirty = false;
  localStorage.setItem(`trilha-current:${selectedCourse.id}`, lesson.id);
  $('#cover').hidden = true;
  video.hidden = false;
  $('#playback-state').textContent = 'Carregando vídeo do Telegram…';
  const module = modules.find(m => m.code === lesson.module);
  $('#lesson-module').textContent = `${module ? module.name : 'Outros vídeos'} / ${lessonLabel(lesson)}`;
  $('#lesson-title').textContent = lesson.title;
  $('#lesson-description').textContent = lesson.caption || lesson.filename;
  video.src = `/api/video/${encodeURIComponent(lesson.id)}`;
  video.playbackRate = Number($('#speed').value);
  video.load();
  switching = false;
  render();
  preparedPlayback = false;
  clearTimeout(cacheTimer);
  checkCache(lesson.id);
}
video.addEventListener('loadedmetadata', () => {
  if (current?.position > 0 && current.position < video.duration - 2) video.currentTime = current.position;
  video.playbackRate = Number($('#speed').value);
  $('#playback-state').textContent = current?.position ? `Retomando de ${clock(current.position)}` : 'Pronto para assistir';
});
video.addEventListener('playing', () => $('#playback-state').textContent = preparedPlayback ? 'Assistindo do computador · progresso salvo' : 'Assistindo · progresso salvo automaticamente');
video.addEventListener('waiting', () => $('#playback-state').textContent = 'Carregando próximo trecho…');
video.addEventListener('pause', () => {
  if (!switching && current && video.getAttribute('src')) {
    $('#playback-state').textContent = video.ended ? 'Aula finalizada' : 'Pausado · seu progresso é salvo automaticamente';
    savePosition();
  }
});
video.addEventListener('timeupdate', () => { if (!video.paused && !switching) positionDirty = true; if (Date.now() - lastSaved > 8000) savePosition(); });
video.addEventListener('error', () => {
  if (!current || !video.getAttribute('src')) return;
  $('#playback-state').textContent = 'Não foi possível reproduzir o vídeo';
  toast('Falha ao carregar. Verifique sua conexão e a sessão do Telegram. Alguns formatos podem não ser compatíveis com o navegador.',true);
});
video.addEventListener('ended', async () => {
  if (!current) return;
  await savePosition();
  try { if (!current.completed) await toggleComplete(current.id); toast('Aula concluída. A próxima está na lista ao lado.'); }
  catch (error) { toast(error.message,true); }
});
async function toggleComplete(id) {
  const lesson = lessons.find(l => l.id === id);
  if (!lesson) return;
  const completed = !lesson.completed;
  await api(`/api/lessons/${id}`, {method:'PATCH',body:JSON.stringify({completed})});
  lesson.completed = completed;
  render();
}
$('#lesson-list').addEventListener('click', async event => {
  const check = event.target.closest('[data-check]'), row = event.target.closest('[data-id]');
  try { if (check) await toggleComplete(check.dataset.check); else if (row) await selectLesson(row.dataset.id); }
  catch (error) { toast(error.message,true); }
});
$('#complete').onclick = async () => { try { await toggleComplete(current.id); } catch(e) { toast(e.message,true); } };
$('#next').onclick = () => selectLesson(lessons[lessons.findIndex(l => l.id === current?.id) + 1]?.id);
$('#previous').onclick = () => selectLesson(lessons[lessons.findIndex(l => l.id === current?.id) - 1]?.id);
$('#speed').onchange = () => { video.playbackRate = Number($('#speed').value); localStorage.setItem('trilha-speed',$('#speed').value); };
$('#speed').value = localStorage.getItem('trilha-speed') || '1';

function preparationScreen(text) {
  video.hidden = true;
  $('#cover').hidden = false;
  $('#cover-title').textContent = 'Preparando sua aula…';
  $('#cover-copy').textContent = text;
  $('#connect').hidden = true;
}
async function checkCache(id, reloadWhenReady = false) {
  if (current?.id !== id) return;
  try {
    const state = await api(`/api/cache/${encodeURIComponent(id)}`);
    if (current?.id !== id) return;
    const button = $('#prepare'), detail = $('#cache-detail');
    button.disabled = state.running || state.ready;
    if (state.ready) {
      preparedPlayback = true;
      button.textContent = '✓ Aula preparada';
      detail.textContent = 'Disponível neste computador. A reprodução usa o arquivo local.';
      if (reloadWhenReady) {
        switching = true;
        $('#cover').hidden = true;
        video.hidden = false;
        video.src = `/api/video/${encodeURIComponent(id)}`;
        video.load();
        switching = false;
        $('#playback-state').textContent = 'Aula preparada. Pressione Play para continuar.';
        toast('Aula pronta para assistir pelo arquivo local.');
      }
    } else if (state.running) {
      if (video.getAttribute('src')) {
        await savePosition();
        switching = true;
        video.pause();
        video.removeAttribute('src');
        video.load();
        switching = false;
      }
      const percent = state.total ? Math.floor(state.downloaded / state.total * 100) : 0;
      button.textContent = `Preparando ${percent}%…`;
      detail.textContent = `${(state.downloaded / 1048576).toFixed(1)} de ${(state.total / 1048576).toFixed(1)} MB · aguarde concluir para assistir sem depender do Telegram.`;
      preparationScreen(`${percent}% · ${(state.downloaded / 1048576).toFixed(1)} de ${(state.total / 1048576).toFixed(1)} MB`);
      $('#playback-state').textContent = 'Preparando a aula para reprodução local…';
      cacheTimer = setTimeout(() => checkCache(id, true), 1500);
    } else {
      button.textContent = '↓ Preparar aula';
      detail.textContent = state.error || 'Se travar, prepare esta aula antes de assistir. O vídeo será salvo temporariamente no computador.';
      if (state.error && reloadWhenReady) {
        $('#cover').hidden = true;
        video.hidden = false;
        video.src = `/api/video/${encodeURIComponent(id)}`;
        video.load();
        toast(state.error,true);
      }
    }
  } catch(error) {
    if (current?.id === id) { $('#prepare').disabled = false; $('#cache-detail').textContent = error.message; }
  }
}
$('#prepare').onclick = async () => {
  if (!current) return;
  const id = current.id;
  $('#prepare').disabled = true;
  try {
    // Release the live stream so the preparation gets the available bandwidth.
    await savePosition();
    switching = true;
    video.pause();
    video.removeAttribute('src');
    video.load();
    switching = false;
    preparationScreen('Iniciando o download. Você poderá assistir quando concluir.');
    await api(`/api/cache/${encodeURIComponent(id)}`,{method:'POST'});
    if (current?.id === id) $('#playback-state').textContent = 'Preparando a aula para reprodução local…';
    clearTimeout(cacheTimer);
    await checkCache(id,true);
  } catch(error) {
    switching = false;
    if (current?.id === id) {
      $('#cover').hidden = true;
      video.hidden = false;
      video.src = `/api/video/${encodeURIComponent(id)}`;
      video.load();
      $('#prepare').disabled = false;
    }
    toast(error.message,true);
  }
};
$('#search').oninput = render;
document.querySelectorAll('[data-filter]').forEach(button => button.onclick = () => { filter = button.dataset.filter; document.querySelectorAll('[data-filter]').forEach(b => b.classList.toggle('selected',b === button)); render(); });
const openSetup = () => $('#setup-dialog').showModal();
['#connect','#setup','#help'].forEach(s => $(s).onclick = openSetup);
$('#classroom').onclick = () => window.scrollTo({top:0,behavior:'smooth'});
$('#stats').onclick = () => {
  $('#stats-content').innerHTML = `<p>${esc(selectedCourse?.name)}</p><div class="stats-row"><strong>Progresso total</strong><span>${courseDone()} / ${courseTotal()} aulas</span></div>` + modules.map(m => { const items = lessons.filter(l => l.module === m.code); const done = indexedCourse() ? completedNumbers(items).length : items.filter(l => l.completed).length; return `<div class="stats-row">${esc(m.name)}<span>${done} / ${m.total}</span></div>`; }).join('');
  $('#stats-dialog').showModal();
};
async function refreshLessons(id = selectedCourse.id) {
  const [items, groups, catalog, files] = await Promise.all([api(coursePath('/api/lessons',id)),api(coursePath('/api/modules',id)),api('/api/courses'),api(coursePath('/api/materials',id))]);
  if (selectedCourse?.id !== id) return;
  lessons = items;
  modules = groups;
  courses = catalog;
  selectedCourse = courses.find(c => c.id === id);
  materials = files;
  if (current) current = lessons.find(l => l.id === current.id) || null;
  render();
  updateCourseInfo();
}
function setConnected(status) {
  configured = status.configured;
  $('#connection-label').textContent = configured ? (status.connected ? 'Curso conectado · sincronização manual' : 'Clique em Sincronizar para acessar o curso') : 'Telegram ainda não conectado';
  if (!current) {
    $('#playback-state').textContent = configured ? 'Selecione uma aula na lista' : 'Aguardando conexão';
    $('#cover-title').textContent = configured ? 'Uma aula. Um novo passo.' : 'Seu espaço para aprender.';
    $('#cover-copy').innerHTML = configured ? (lessons.length ? 'Escolha uma aula na lateral para começar.' : 'Clique em Sincronizar Telegram<br>para importar suas aulas.') : 'Conecte seu Telegram e continue<br>exatamente de onde parou.';
    $('#connect').hidden = configured;
  }
}
async function pollSync(id = selectedCourse.id) {
  try {
    const status = await api(coursePath('/api/status',id));
    if (selectedCourse?.id !== id) return;
    setConnected(status);
    if (status.sync.running) {
      syncing = true;
      $('#sync').disabled = true;
      $('#sync span').textContent = `Importando ${status.sync.count} vídeos…`;
      syncTimer = setTimeout(() => pollSync(id),1500);
    } else {
      $('#sync').disabled = false;
      $('#sync span').textContent = 'Sincronizar Telegram';
      await refreshLessons(id);
      if (selectedCourse?.id !== id) return;
      if (syncing) { toast(status.sync.error || `${status.sync.count} vídeos sincronizados. Seu progresso foi preservado.`,Boolean(status.sync.error)); syncing = false; }
      setConnected(status);
    }
  } catch(error) { syncing = false; $('#sync').disabled = false; $('#sync span').textContent = 'Sincronizar Telegram'; toast(error.message,true); }
}
$('#sync').onclick = async () => {
  if (!configured) { openSetup(); return; }
  try { $('#sync').disabled = true; await api(coursePath('/api/sync'),{method:'POST'}); syncing = true; await pollSync(); }
  catch(error) { $('#sync').disabled = false; toast(error.message,true); }
};
$('#recheck').onclick = async () => {
  try { const status = await api(coursePath('/api/status')); setConnected(status); if (configured) { $('#setup-dialog').close(); toast('Conta configurada. Clique em Sincronizar Telegram.'); } else toast('A configuração local ainda não foi concluída. Execute conectar.bat.',true); }
  catch(error) { toast(error.message,true); }
};
document.addEventListener('visibilitychange', () => { if(document.hidden) savePosition(true); });
window.addEventListener('pagehide', () => savePosition(true));
function updateCourseInfo() {
  if (!selectedCourse) return;
  $('#course-info').textContent = selectedCourse.description;
  $('#course-subtitle').textContent = selectedCourse.lesson_count ? `${selectedCourse.lesson_count} vídeos · ${Math.floor(selectedCourse.duration / 3600)}h ${Math.floor(selectedCourse.duration % 3600 / 60)}min importados` : 'Sincronize este curso para carregar suas aulas.';
  $('#course-export').href = coursePath('/api/export');
  const missing = selectedCourse.missing_numbers || [];
  $('#index-warning').hidden = !missing.length;
  $('#index-warning').textContent = missing.length ? `O índice lista ${courseTotal()} aulas; ${selectedCourse.lesson_count} vídeos foram encontrados. Ainda não encontradas: ${missing.slice(0,12).map(n => '#F'+String(n).padStart(selectedCourse.layout === 'autodidata' ? 2 : 3,'0')).join(', ')}${missing.length>12 ? '…' : ''}.` : '';
  $('#course-materials').innerHTML = materials.map(m => `<a class="material-link" href="/api/materials/${encodeURIComponent(m.id)}/download" download><span>↓ ${esc((JSON.parse(m.tags)[0] || 'Material').toUpperCase())}</span><span>${esc(m.filename)}<small>${(m.size/1048576).toFixed(1)} MB · baixar material de apoio</small></span></a>`).join('');
}
async function changeCourse(id) {
  const course = courses.find(c => c.id === id);
  if (!course) return;
  const generation = ++courseGeneration;
  await savePosition();
  if (generation !== courseGeneration) return;
  clearTimeout(cacheTimer);
  clearTimeout(syncTimer);
  switching = true;
  video.pause();
  video.removeAttribute('src');
  video.load();
  current = null;
  positionDirty = false;
  switching = false;
  lessons = []; modules = []; materials = []; syncing = false; preparedPlayback = false;
  selectedCourse = course;
  localStorage.setItem('trilha-course',id);
  $('#course-select').value = id;
  $('#breadcrumb-course').textContent = course.name;
  $('#course-title').innerHTML = `${esc(course.name)}<span class="heading-dot">.</span>`;
  $('#course-kicker').textContent = course.name.toUpperCase();
  document.title = `Trilha · ${course.name}`;
  $('#search').value = ''; filter = 'all';
  document.querySelectorAll('[data-filter]').forEach(b => b.classList.toggle('selected',b.dataset.filter === 'all'));
  $('#cover').hidden = false; video.hidden = true;
  $('#lesson-module').textContent = 'SUA SALA DE AULA';
  $('#lesson-title').textContent = 'Escolha seu próximo passo.';
  $('#lesson-description').textContent = 'Selecione uma aula na lista. Cada curso mantém seu próprio progresso.';
  $('#prepare').disabled = true; $('#prepare').textContent = '↓ Preparar aula';
  $('#cache-detail').textContent = 'Prepare uma aula para assistir pelo arquivo local, sem depender da velocidade do Telegram.';
  $('#sync').disabled = false; $('#sync span').textContent = 'Sincronizar Telegram';
  render(); updateCourseInfo();
  const [items, groups, status, files] = await Promise.all([api(coursePath('/api/lessons',id)),api(coursePath('/api/modules',id)),api(coursePath('/api/status',id)),api(coursePath('/api/materials',id))]);
  if (generation !== courseGeneration) return;
  lessons = items; modules = groups; materials = files; render(); setConnected(status); updateCourseInfo();
  const last = localStorage.getItem(`trilha-current:${id}`) || (id === 'autodidata' ? localStorage.getItem('trilha-current') : null);
  if (configured && lessons.some(l => l.id === last)) await selectLesson(last);
  if (status.sync.running) { syncing = true; pollSync(id); }
}
$('#course-select').onchange = () => changeCourse($('#course-select').value).catch(e => toast(e.message,true));
(async () => {
  try {
    courses = await api('/api/courses');
    $('#course-select').innerHTML = courses.map(c => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');
    const saved = localStorage.getItem('trilha-course');
    await changeCourse(courses.some(c => c.id === saved) ? saved : courses[0].id);
  } catch(error) { toast(`Não foi possível carregar a sala: ${error.message}`,true); }
})();
