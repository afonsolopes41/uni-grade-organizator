/* Organizador de Notas — interface. */
'use strict';

const $ = (id) => document.getElementById(id);

const state = {
  review: null,       // resposta de /api/state
  results: null,      // resposta de /api/results
  step: 'upload',
  selected: new Set(),
  hiddenSubjects: new Set(),
  search: '',
  onlySelected: false,
  openRows: new Set(),
  showConfirmed: false,
};

/* ------------------------------------------------------------------ rede */

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const type = response.headers.get('content-type') || '';
  if (!type.includes('application/json')) {
    if (!response.ok) throw new Error(`Erro ${response.status}`);
    return response;
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Erro ${response.status}`);
  return data;
}

const postJSON = (path, body) =>
  api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });

function busy(on, text) {
  $('busy').hidden = !on;
  if (text) $('busy-text').textContent = text;
}

let toastTimer;
function toast(message, isError) {
  const node = $('toast');
  node.textContent = message;
  node.classList.toggle('is-error', !!isError);
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, isError ? 7000 : 3500);
}

const escapeHtml = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const num = (value) => String(value).replace('.', ',');

/* ------------------------------------------------------------------ língua */

/* A língua vive na sessão do servidor (é ela que traduz perguntas e avisos)
   e fica também aqui, para a página abrir já na língua certa. */
async function switchLanguage(code) {
  if (code === LANG) return;
  setLanguage(code);
  try { localStorage.setItem('gradeorg.lang', code); } catch (error) { /* privado */ }
  paintLanguage();
  applyStaticText();
  busy(true, t('busy.applying'));
  try {
    state.review = await postJSON('/api/language', { language: code });
    state.results = null;
    renderFiles();
    renderReview();
    if (state.step === 'results') await loadResults();
  } catch (error) { toast(error.message, true); } finally { busy(false); }
}

function paintLanguage() {
  document.querySelectorAll('#lang button').forEach((button) => {
    button.classList.toggle('is-on', button.dataset.lang === LANG);
  });
}

/* ------------------------------------------------------------- navegação */

function goto(step) {
  state.step = step;
  for (const name of ['upload', 'review', 'results']) {
    $(`panel-${name}`).hidden = name !== step;
  }
  document.querySelectorAll('.step').forEach((button) => {
    button.classList.toggle('is-active', button.dataset.step === step);
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function refreshStepAvailability() {
  const hasFiles = !!(state.review && state.review.files.length);
  document.querySelector('[data-step="review"]').disabled = !hasFiles;
  document.querySelector('[data-step="results"]').disabled = !hasFiles;
  $('upload-actions').hidden = !hasFiles;
}

/* -------------------------------------------------------------- ficheiros */

function setupDropzone() {
  const zone = $('dropzone');
  const input = $('file-input');

  const open = () => input.click();
  zone.addEventListener('click', open);
  $('pick').addEventListener('click', (event) => { event.stopPropagation(); open(); });
  zone.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); }
  });

  ['dragenter', 'dragover'].forEach((name) =>
    zone.addEventListener(name, (event) => {
      event.preventDefault();
      zone.classList.add('is-over');
    }));
  ['dragleave', 'drop'].forEach((name) =>
    zone.addEventListener(name, (event) => {
      event.preventDefault();
      if (name === 'dragleave' && zone.contains(event.relatedTarget)) return;
      zone.classList.remove('is-over');
    }));

  zone.addEventListener('drop', (event) => {
    if (event.dataTransfer?.files?.length) upload(event.dataTransfer.files);
  });
  input.addEventListener('change', () => {
    if (input.files.length) upload(input.files);
    input.value = '';
  });
}

async function upload(fileList) {
  const form = new FormData();
  for (const file of fileList) form.append('files', file);
  busy(true, t('busy.reading', { n: fileList.length }));
  try {
    const data = await api('/api/upload', { method: 'POST', body: form });
    state.review = data;
    state.results = null;
    renderFiles();
    renderUploadErrors(data.rejected || []);
    refreshStepAvailability();
    if ((data.accepted || []).length) {
      toast(t('toast.read', { n: data.accepted.length }));
      renderReview();
      goto('review');
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    busy(false);
  }
}

function renderFiles() {
  const files = state.review?.files || [];
  const conhecidas = state.review?.subjects || [];
  $('file-list').innerHTML = files.map((file) => {
    const sources = (state.review.sources || []).filter((s) => s.filename === file.name);
    const rows = sources.reduce((n, s) => n + s.row_count, 0);
    // A cadeira que o utilizador escolheu para este ficheiro, se escolheu.
    const escolhida = sources
      .map((s) => state.review.answers[`${s.id}:subject`])
      .find(Boolean) || '';
    const detectada = [...new Set(sources.map((s) => s.subject.value).filter(Boolean))];
    return `
      <div class="file-card">
        <div class="file-kind">${escapeHtml(file.kind.toUpperCase())}</div>
        <div class="grow">
          <div class="name">${escapeHtml(file.name)}</div>
          <div class="meta">
            ${escapeHtml(t('file.tables', { n: file.tables }))}
            ${sources.length ? ' · ' + escapeHtml(t('file.rows', { n: rows })) : ''}
          </div>
        </div>
        <label class="file-subject">
          <span>${escapeHtml(t('file.subject'))}</span>
          <select data-assign="${escapeHtml(file.name)}">
            <option value="">${escapeHtml(detectada.length
              ? detectada.join(', ') + ' ' + t('file.subject_auto')
              : t('file.subject_auto'))}</option>
            ${conhecidas.map((s) => `<option value="${escapeHtml(s)}"
              ${escolhida === s ? 'selected' : ''}>${escapeHtml(s)}</option>`).join('')}
          </select>
        </label>
        <button class="icon-btn" data-remove="${escapeHtml(file.name)}"
                title="${escapeHtml(t('file.remove'))}">✕</button>
      </div>`;
  }).join('');

  $('file-list').querySelectorAll('[data-assign]').forEach((select) => {
    select.addEventListener('change', () => subjectAction({
      action: 'assign', file: select.dataset.assign, subject: select.value,
    }));
  });

  $('file-list').querySelectorAll('[data-remove]').forEach((button) => {
    button.addEventListener('click', async () => {
      busy(true, t('busy.removing'));
      try {
        state.review = await postJSON('/api/files/remove', { name: button.dataset.remove });
        state.results = null;
        renderFiles();
        renderReview();
        refreshStepAvailability();
        if (!state.review.files.length) goto('upload');
      } catch (error) { toast(error.message, true); } finally { busy(false); }
    });
  });
}

function renderUploadErrors(rejected) {
  $('upload-errors').innerHTML = rejected.map((item) => `
    <div class="notice error">
      <span class="icon">!</span>
      <span><b>${escapeHtml(item.name)}</b>${escapeHtml(item.error)}</span>
    </div>`).join('');
}

/* --------------------------------------------------------- confirmação */

function renderReview() {
  if (!state.review) return;
  renderQuestions();
  renderCurriculum();
  renderSources();
  $('pass-mark').value = state.review.settings.pass_mark;
  $('merge-by-name').checked = state.review.settings.merge_by_name;
}

function renderQuestions() {
  const questions = state.review.questions || [];
  const container = $('questions');

  if (!questions.length) {
    container.innerHTML = `
      <div class="card card-calm">
        <h2 class="section-title">${escapeHtml(t('questions.none.title'))} <span class="tick">✓</span></h2>
        <p class="section-lead">${escapeHtml(t('questions.none.lead'))}</p>
      </div>`;
    return;
  }

  const cards = questions.map((question) => {
    const choices = question.options.map((option) => {
      const checked = String(state.review.answers[question.id] ?? question.default) === String(option.value);
      return `
        <label class="choice ${checked ? 'is-checked' : ''}">
          <input type="radio" name="${escapeHtml(question.id)}"
                 value="${escapeHtml(option.value)}" ${checked ? 'checked' : ''}>
          <span class="label">${escapeHtml(option.label)}</span>
          ${option.hint ? `<span class="hint">${escapeHtml(option.hint)}</span>` : ''}
        </label>`;
    }).join('');

    const custom = question.allow_custom ? `
      <div class="custom-row">
        <input type="text" placeholder="${escapeHtml(t('questions.custom'))}"
               data-custom="${escapeHtml(question.id)}"
               value="${escapeHtml(customValue(question))}">
        <button class="btn btn-ghost btn-sm"
                data-custom-save="${escapeHtml(question.id)}">${escapeHtml(t('action.save'))}</button>
      </div>` : '';

    // Um botão para abrir a pauta: é muito mais fácil responder a olhar para ela.
    const documento = question.source_id ? `
      <a class="btn btn-ghost btn-sm open-doc" target="_blank" rel="noopener"
         href="/api/document/${encodeURIComponent(question.source_id)}">
        ⧉ ${escapeHtml(t('questions.open_document'))}
        <small>${escapeHtml(t('questions.open_hint'))}</small>
      </a>` : '';

    return `
      <div class="card question ${question.severity === 'warning' ? 'is-warning' : ''}"
           data-question="${escapeHtml(question.id)}">
        <h3>${escapeHtml(question.title)}</h3>
        ${question.detail ? `<p class="detail">${escapeHtml(question.detail)}</p>` : ''}
        <div class="choices">${choices}</div>
        ${custom}
        ${documento}
      </div>`;
  }).join('');

  container.innerHTML = `
    <div class="card card-calm">
      <h2 class="section-title">${escapeHtml(t('questions.title', { n: questions.length }))}</h2>
      <p class="section-lead">${escapeHtml(t('questions.lead'))}</p>
      <button class="btn btn-ghost btn-sm" id="accept-all">✓ ${escapeHtml(t('questions.accept_all'))}</button>
    </div>
    ${cards}`;

  container.querySelectorAll('input[type=radio]').forEach((input) => {
    const commit = () => saveAnswer(input.name, input.value);
    input.addEventListener('change', commit);
    input.addEventListener('click', commit);
  });

  const acceptAll = container.querySelector('#accept-all');
  if (acceptAll) acceptAll.addEventListener('click', () => {
    const answers = {};
    for (const question of questions) {
      const value = state.review.answers[question.id] ?? question.default;
      if (value) answers[question.id] = value;
    }
    saveAnswers(answers);
  });
  container.querySelectorAll('[data-custom-save]').forEach((button) => {
    const id = button.dataset.customSave;
    const field = container.querySelector(`[data-custom="${CSS.escape(id)}"]`);
    const commit = () => { if (field.value.trim()) saveAnswer(id, field.value.trim()); };
    button.addEventListener('click', commit);
    field.addEventListener('keydown', (event) => { if (event.key === 'Enter') commit(); });
  });
}

function customValue(question) {
  const answer = state.review.answers[question.id];
  if (!answer) return '';
  return question.options.some((o) => String(o.value) === String(answer)) ? '' : answer;
}

function saveAnswer(id, value) {
  // Evita um pedido inútil quando o "change" e o "click" disparam os dois.
  if (String(state.review.answers[id] ?? '') === String(value)) return Promise.resolve();
  return saveAnswers({ [id]: value });
}

async function saveAnswers(answers) {
  if (!Object.keys(answers).length) return;
  await applyToReview({ answers });
}

const saveSettings = (settings) => applyToReview({ settings });

const saveOverride = (sourceId, columnIndex, spec) =>
  applyToReview({ overrides: { [sourceId]: { [columnIndex]: spec } } });

async function applyToReview(body) {
  busy(true, t('busy.applying'));
  try {
    state.review = await postJSON('/api/answers', body);
    state.results = null;
    renderReview();
    renderFiles();
  } catch (error) { toast(error.message, true); } finally { busy(false); }
}

async function subjectAction(body) {
  busy(true, t('busy.applying'));
  try {
    state.review = await postJSON('/api/subjects', body);
    state.results = null;
    renderReview();
    renderFiles();
  } catch (error) { toast(error.message, true); } finally { busy(false); }
}

/* ------------------------------------------------- unidades curriculares */

function renderCurriculum() {
  const data = state.review;
  const subjects = data.subjects || [];
  if (!subjects.length) { $('curriculum').innerHTML = ''; return; }

  const curriculum = data.curriculum || {};
  const detected = data.detected_semesters || {};
  const marks = data.pass_marks || {};
  const codes = data.subject_codes || {};
  const files = data.subject_files || {};
  const removed = new Set(data.removed_subjects || []);
  const cursos = [...new Set(Object.values(data.courses || {}).filter(Boolean))];

  const live = subjects.filter((s) => !removed.has(s));
  const porPreencher = live.filter((s) => {
    const meta = curriculum[s] || {};
    return meta.year == null || meta.semester == null;
  }).length;

  const linhas = live.map((subject) => {
    const meta = curriculum[subject] || {};
    const semestre = meta.semester ?? (detected[subject] ? Number(detected[subject]) : null);
    const origem = files[subject] || [];
    return `
      <tr>
        <td class="uc-name-cell">
          <input class="uc-name" type="text" value="${escapeHtml(subject)}"
                 title="${escapeHtml(t('uc.rename'))}"
                 data-rename="${escapeHtml(subject)}">
          ${codes[subject] ? `<div class="uc-codigo">${escapeHtml(codes[subject])}</div>` : ''}
        </td>
        <td class="uc-files" title="${escapeHtml(origem.join(' · '))}">
          ${origem.length
            ? origem.map((f) => `<span class="file-tag">${escapeHtml(f)}</span>`).join('')
            : `<span class="sem-pautas">${escapeHtml(t('uc.no_files'))}</span>`}
        </td>
        <td>
          <input type="text" list="cursos-conhecidos" class="uc-course"
                 placeholder="${escapeHtml(t('uc.course_placeholder'))}"
                 value="${escapeHtml(meta.course || '')}"
                 data-uc="${escapeHtml(subject)}" data-campo="course">
        </td>
        <td class="num ${meta.year == null ? 'falta' : ''}">
          <select data-uc="${escapeHtml(subject)}" data-campo="year">
            <option value="">—</option>
            ${[1, 2, 3, 4, 5].map((y) =>
              `<option value="${y}" ${meta.year === y ? 'selected' : ''}>${escapeHtml(t('uc.year_option', { n: y }))}</option>`).join('')}
          </select>
        </td>
        <td class="num ${semestre == null ? 'falta' : ''}">
          <select data-uc="${escapeHtml(subject)}" data-campo="semester">
            <option value="">—</option>
            ${[1, 2].map((n) =>
              `<option value="${n}" ${semestre === n ? 'selected' : ''}>${n}</option>`).join('')}
          </select>
        </td>
        <td class="num">
          <input type="number" min="0" max="60" step="0.5" placeholder="—"
                 value="${meta.ects ?? ''}" data-uc="${escapeHtml(subject)}" data-campo="ects">
        </td>
        <td class="num">
          <input type="number" min="0" max="20" step="0.5"
                 value="${marks[subject] ?? data.settings.pass_mark}"
                 data-uc="${escapeHtml(subject)}" data-campo="pass_mark">
        </td>
        <td class="num">
          <button class="icon-btn danger" data-remove-uc="${escapeHtml(subject)}"
                  title="${escapeHtml(t('uc.delete'))}">✕</button>
        </td>
      </tr>`;
  }).join('');

  const apagadas = removed.size ? `
    <p class="removed-strip"><b>${escapeHtml(t('uc.removed'))}</b>
      ${[...removed].map((s) => `
        <span class="removed-tag"><s>${escapeHtml(s)}</s>
          <button data-restore-uc="${escapeHtml(s)}">${escapeHtml(t('uc.restore'))}</button>
        </span>`).join('')}
    </p>` : '';

  $('curriculum').innerHTML = `
    <div class="card">
      <h2 class="section-title">${escapeHtml(t('uc.title'))}</h2>
      <p class="section-lead">${escapeHtml(t('uc.lead'))}
        ${porPreencher ? `<b>${escapeHtml(t('uc.missing', { n: porPreencher }))}</b>` : ''}</p>
      <div class="table-scroll">
        <table class="uc-table">
          <thead><tr>
            <th>${escapeHtml(t('uc.col.name'))}</th>
            <th>${escapeHtml(t('uc.col.files'))}</th>
            <th>${escapeHtml(t('uc.col.course'))}<small>${escapeHtml(t('uc.course_hint'))}</small></th>
            <th class="num">${escapeHtml(t('uc.col.year'))}</th>
            <th class="num">${escapeHtml(t('uc.col.semester'))}</th>
            <th class="num">${escapeHtml(t('uc.col.ects'))}</th>
            <th class="num">${escapeHtml(t('uc.col.pass'))}</th>
            <th></th>
          </tr></thead>
          <tbody>${linhas}</tbody>
        </table>
      </div>
      <p class="uc-actions">
        <button class="btn btn-ghost btn-sm" id="btn-nova-uc">${escapeHtml(t('uc.add'))}</button>
      </p>
      ${apagadas}
      <datalist id="cursos-conhecidos">
        ${cursos.map((c) => `<option value="${escapeHtml(c)}"></option>`).join('')}
      </datalist>
    </div>`;

  $('curriculum').querySelectorAll('[data-uc]').forEach((campo) => {
    campo.addEventListener('change', () => {
      const subject = campo.dataset.uc;
      const valor = campo.value.trim();
      if (campo.dataset.campo === 'pass_mark') {
        saveSettings({ subject_pass_marks: { [subject]: valor === '' ? '' : parseFloat(valor) } });
      } else {
        saveSettings({ subject_curriculum: { [subject]: { [campo.dataset.campo]: valor } } });
      }
    });
  });

  $('curriculum').querySelectorAll('[data-rename]').forEach((campo) => {
    const commit = () => {
      const antigo = campo.dataset.rename;
      const novo = campo.value.trim();
      if (!novo || novo === antigo) { campo.value = antigo; return; }
      subjectAction({ action: 'rename', subject: antigo, name: novo });
    };
    campo.addEventListener('change', commit);
    campo.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') campo.blur();
      if (event.key === 'Escape') { campo.value = campo.dataset.rename; campo.blur(); }
    });
  });

  $('curriculum').querySelectorAll('[data-remove-uc]').forEach((button) => {
    button.addEventListener('click', () => {
      const subject = button.dataset.removeUc;
      if (!window.confirm(t('uc.delete_confirm', { name: subject }))) return;
      subjectAction({ action: 'remove', subject });
    });
  });
  $('curriculum').querySelectorAll('[data-restore-uc]').forEach((button) => {
    button.addEventListener('click', () =>
      subjectAction({ action: 'restore', subject: button.dataset.restoreUc }));
  });

  $('curriculum').querySelector('#btn-nova-uc').addEventListener('click', () => {
    const nome = (window.prompt(t('uc.add_prompt')) || '').trim();
    if (nome) subjectAction({ action: 'create', name: nome });
  });
}

/* ------------------------------------------------------ ajustes avançados */

const EPOCA_OPTIONS = () => [
  ['', t('epoca.none')],
  ['epoca1', t('epoca.epoca1')],
  ['epoca2', t('epoca.epoca2')],
  ['especial', t('epoca.especial')],
];

/* A aplicação só quer a nota final: as outras colunas ficam de fora, por isso
   aqui há quatro papéis e mais nada. */
const ROLE_OPTIONS = () => [
  ['name', t('role.name')],
  ['id', t('role.id')],
  ['final', t('role.final')],
  ['ignore', t('role.ignore')],
];

const roleOf = (column) => {
  if (column.role === 'name' || column.role === 'id') return column.role;
  if (column.role === 'grade' && column.kind === 'final') return 'final';
  return 'ignore';
};

function renderSources() {
  const epocas = EPOCA_OPTIONS();
  const papeis = ROLE_OPTIONS();
  const confirmadas = new Set(state.review.confirmed_sources || []);
  const todas = state.review.sources || [];
  const visiveis = state.showConfirmed
    ? todas : todas.filter((s) => !confirmadas.has(s.id));

  const arrumadas = confirmadas.size ? `
    <p class="confirmed-strip">
      ${escapeHtml(t('source.confirmed', { n: confirmadas.size }))}
      <button id="toggle-confirmed">${escapeHtml(
        state.showConfirmed ? t('source.hide_confirmed') : t('source.show_confirmed'))}</button>
    </p>` : '';

  $('sources').innerHTML = arrumadas + visiveis.map((source) => {
    const confirmada = confirmadas.has(source.id);
    const rows = source.columns.map((column) => {
      const papel = roleOf(column);
      return `
      <tr class="${papel === 'final' ? 'is-final' : ''}">
        <td><b>${escapeHtml(column.header)}</b></td>
        <td>
          <select data-src="${source.id}" data-col="${column.index}" data-field="role">
            ${papeis.map(([value, label]) =>
              `<option value="${value}" ${papel === value ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('')}
          </select>
        </td>
        <td>
          ${papel === 'final' ? `
          <select data-src="${source.id}" data-col="${column.index}" data-field="epoca">
            ${epocas.map(([value, label]) =>
              `<option value="${value}" ${(column.epoca || '') === value ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('')}
          </select>` : '<span class="plain">—</span>'}
        </td>
        <td class="samples" title="${escapeHtml(column.samples.join(' · '))}">
          ${escapeHtml(column.samples.join(' · ')) || '—'}</td>
        <td><span class="badge ${column.confidence >= 0.7 ? 'green' : column.confidence >= 0.5 ? 'amber' : 'grey'}"
                  title="${escapeHtml(column.reason)}">${Math.round(column.confidence * 100)}%</span></td>
      </tr>`;
    }).join('');

    return `
      <div class="source-block ${confirmada ? 'is-confirmed' : ''}">
        <div class="source-head">
          <span class="title">${escapeHtml(source.filename)}</span>
          <div class="badge-row">
            ${source.location ? `<span class="badge">${escapeHtml(source.location)}</span>` : ''}
            <span class="badge accent">${escapeHtml(source.subject.value || t('source.no_subject'))}</span>
            ${source.academic_year.value ? `<span class="badge">${escapeHtml(source.academic_year.value)}</span>` : ''}
            ${source.document_date ? `<span class="badge">${escapeHtml(t('source.document_of', { date: source.document_date }))}</span>` : ''}
            <span class="badge">${escapeHtml(t('source.students', { n: source.row_count }))}</span>
            ${source.component_label
              ? `<span class="badge amber">${escapeHtml(t('source.only_component', { label: source.component_label, weight: source.component_weight }))}</span>`
              : ''}
          </div>
          <div class="source-tools">
            <a class="btn btn-ghost btn-sm" target="_blank" rel="noopener"
               href="/api/document/${encodeURIComponent(source.id)}">⧉ ${escapeHtml(t('source.open'))}</a>
            <button class="btn ${confirmada ? 'btn-ghost' : 'btn-ok'} btn-sm"
                    data-confirm="${source.id}" data-confirmed="${confirmada ? '1' : ''}"
                    title="${escapeHtml(t('source.confirm_hint'))}">${escapeHtml(
              confirmada ? t('source.reopen') : t('source.confirm'))}</button>
          </div>
        </div>
        ${(source.notes || []).length ? `<p class="source-note">${
          source.notes.map(escapeHtml).join('<br>')}</p>` : ''}
        <div class="table-scroll">
          <table class="col-table">
            <thead><tr>
              <th>${escapeHtml(t('col.header'))}</th><th>${escapeHtml(t('col.role'))}</th>
              <th>${escapeHtml(t('col.epoca'))}</th><th>${escapeHtml(t('col.samples'))}</th>
              <th>${escapeHtml(t('col.confidence'))}</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
  }).join('');

  const alternar = $('sources').querySelector('#toggle-confirmed');
  if (alternar) alternar.addEventListener('click', () => {
    state.showConfirmed = !state.showConfirmed;
    renderSources();
  });

  $('sources').querySelectorAll('[data-confirm]').forEach((button) => {
    button.addEventListener('click', async () => {
      busy(true, t('busy.applying'));
      try {
        state.review = await postJSON('/api/sources/confirm', {
          source_id: button.dataset.confirm, confirmed: !button.dataset.confirmed,
        });
        renderSources();
      } catch (error) { toast(error.message, true); } finally { busy(false); }
    });
  });

  $('sources').querySelectorAll('select').forEach((select) => {
    select.addEventListener('change', () => {
      const { src, col, field } = select.dataset;
      if (field !== 'role') { saveOverride(src, col, { [field]: select.value }); return; }

      const source = (state.review.sources || []).find((s) => s.id === src);
      const column = source?.columns.find((c) => String(c.index) === String(col));
      if (select.value === 'final') {
        // Marcar como nota final sem dizer a época deixava-a sem efeito nenhum.
        saveOverride(src, col, {
          role: 'grade', kind: 'final', epoca: column?.epoca || 'epoca1',
        });
      } else if (select.value === 'ignore') {
        saveOverride(src, col, { role: 'ignore', kind: 'component' });
      } else {
        saveOverride(src, col, { role: select.value });
      }
    });
  });
}

/* ---------------------------------------------------------- resultados */

async function loadResults() {
  busy(true, t('busy.joining'));
  try {
    state.results = await api('/api/results');
    renderResults();
    goto('results');
  } catch (error) { toast(error.message, true); } finally { busy(false); }
}

function renderResults() {
  const data = state.results;
  if (!data) return;

  const stats = data.stats;
  $('stats').innerHTML = `
    <div class="stat"><div class="value">${stats.students}</div><div class="label">${escapeHtml(t('stats.students'))}</div></div>
    <div class="stat"><div class="value">${stats.subjects}</div><div class="label">${escapeHtml(t('stats.subjects'))}</div></div>
    <div class="stat green"><div class="value">${stats.approved}</div><div class="label">${escapeHtml(t('stats.approved'))}</div></div>
    <div class="stat red"><div class="value">${stats.failed}</div><div class="label">${escapeHtml(t('stats.failed'))}</div></div>
    <div class="stat"><div class="value">${stats.average ?? '—'}</div><div class="label">${escapeHtml(t('stats.average'))}</div></div>`;

  $('pending-warning').innerHTML = (data.questions || []).length ? `
    <div class="notice warning">
      <span class="icon">!</span>
      <span><b>${escapeHtml(t('results.pending', { n: data.questions.length }))}</b>
      ${escapeHtml(t('results.pending_lead'))}</span>
    </div>` : '';

  renderPassMarks();

  $('subject-filters').innerHTML = groupsOf(data.subjects).map((grupo) => `
    <span class="chip-group">
      ${grupo.year != null || grupo.semester != null
        ? `<span class="chip-group-label">${escapeHtml(groupLabel(grupo))}</span>` : ''}
      ${grupo.subjects.map((subject) => `
        <button class="chip ${state.hiddenSubjects.has(subject) ? '' : 'is-on'}"
                data-subject="${escapeHtml(subject)}">${escapeHtml(subject)}</button>`).join('')}
    </span>`).join('');
  $('subject-filters').querySelectorAll('[data-subject]').forEach((chip) => {
    chip.addEventListener('click', () => {
      const subject = chip.dataset.subject;
      if (state.hiddenSubjects.has(subject)) state.hiddenSubjects.delete(subject);
      else state.hiddenSubjects.add(subject);
      renderResults();
    });
  });

  renderTable();
  renderNotices();
}

function renderPassMarks() {
  const data = state.results;
  const marks = data.pass_marks || {};
  const padrao = data.settings?.pass_mark ?? 9.5;
  const proprias = data.settings?.subject_pass_marks || {};

  if (!data.subjects.length) { $('pass-marks').innerHTML = ''; return; }

  $('pass-marks').innerHTML = `
    <div class="minimos">
      <span class="titulo">${escapeHtml(t('results.pass_marks'))}</span>
      ${data.subjects.map((subject) => `
        <label>
          <span>${escapeHtml(subject)}</span>
          <input type="number" min="0" max="20" step="0.5"
                 value="${marks[subject] ?? padrao}"
                 data-pass-mark="${escapeHtml(subject)}">
        </label>`).join('')}
      <span class="nota">${escapeHtml(t('results.pass_marks_hint', { value: padrao }))}</span>
    </div>`;

  $('pass-marks').querySelectorAll('[data-pass-mark]').forEach((input) => {
    input.addEventListener('change', async () => {
      const subject = input.dataset.passMark;
      const raw = input.value.trim();
      const value = raw === '' ? '' : parseFloat(raw);
      if (raw !== '' && Number.isNaN(value)) { input.value = proprias[subject] ?? padrao; return; }
      busy(true, t('busy.applying'));
      try {
        await postJSON('/api/answers', { settings: { subject_pass_marks: { [subject]: value } } });
        state.results = await api('/api/results');
        renderResults();
      } catch (error) { toast(error.message, true); } finally { busy(false); }
    });
  });
}

const visibleSubjects = () =>
  (state.results?.subjects || []).filter((s) => !state.hiddenSubjects.has(s));

const groupLabel = (grupo) => {
  if (grupo.year != null && grupo.semester != null)
    return t('group.year_semester', { year: grupo.year, semester: grupo.semester });
  if (grupo.year != null) return t('group.year', { year: grupo.year });
  if (grupo.semester != null) return t('group.semester', { semester: grupo.semester });
  return t('group.none');
};

/* As cadeiras chegam já ordenadas por ano, semestre e nome: aqui só se juntam
   as seguidas que pertencem ao mesmo ano e semestre. */
function groupsOf(subjects) {
  const curriculum = state.results?.curriculum || {};
  const grupos = [];
  for (const subject of subjects) {
    const meta = curriculum[subject] || {};
    const year = meta.year ?? null;
    const semester = meta.semester ?? null;
    const key = `${year}|${semester}`;
    const ultimo = grupos[grupos.length - 1];
    if (ultimo && ultimo.key === key) ultimo.subjects.push(subject);
    else grupos.push({ key, year, semester, subjects: [subject] });
  }
  return grupos;
}

function filteredStudents() {
  const term = state.search.trim().toLowerCase();
  const subjects = visibleSubjects();
  return (state.results?.students || []).filter((student) => {
    if (state.onlySelected && !state.selected.has(student.key)) return false;
    if (subjects.length && !subjects.some((s) => student.subjects[s])) return false;
    if (!term) return true;
    return student.name.toLowerCase().includes(term)
      || (student.student_id || '').includes(term)
      || student.all_names.some((n) => n.toLowerCase().includes(term));
  });
}

function renderTable() {
  const subjects = visibleSubjects();
  const students = filteredStudents();

  const grupos = groupsOf(subjects);
  const temGrupos = grupos.some((g) => g.year != null || g.semester != null);
  const linhaGrupos = temGrupos ? `
    <tr class="group-row">
      <th colspan="3"></th>
      ${grupos.map((g) => `<th class="group" colspan="${g.subjects.length}">${
        escapeHtml(groupLabel(g))}</th>`).join('')}
      <th></th>
    </tr>` : '';

  $('grades-head').innerHTML = `
    ${linhaGrupos}
    <tr class="${temGrupos ? 'below-groups' : ''}">
      <th style="width:34px"></th>
      <th style="width:92px">${escapeHtml(t('results.col.id'))}</th>
      <th class="who">${escapeHtml(t('results.col.student'))}</th>
      ${subjects.map((s) => `<th class="num">${escapeHtml(s)}</th>`).join('')}
      <th class="num" style="width:92px">${escapeHtml(t('results.col.average'))}</th>
    </tr>`;

  $('grades-body').innerHTML = students.map((student) => {
    const cells = subjects.map((subject) =>
      `<td class="num">${gradePill(student.subjects[subject])}</td>`).join('');

    const values = subjects
      .map((s) => student.subjects[s]?.best_rounded)
      .filter((v) => typeof v === 'number');
    const average = values.length
      ? num((values.reduce((a, b) => a + b, 0) / values.length).toFixed(2))
      : '—';

    const open = state.openRows.has(student.key);
    return `
      <tr class="${open ? 'is-open' : ''}" data-key="${escapeHtml(student.key)}">
        <td><input type="checkbox" data-select="${escapeHtml(student.key)}"
                   ${state.selected.has(student.key) ? 'checked' : ''}
                   aria-label="${escapeHtml(student.name)}"></td>
        <td class="student-id">${escapeHtml(student.student_id || '—')}</td>
        <td>
          <div class="name-cell">
            <button class="toggle" data-toggle="${escapeHtml(student.key)}"
                    aria-label="${escapeHtml(t('results.detail'))}">▸</button>
            <span class="student-name">${escapeHtml(student.name)}</span>
          </div>
        </td>
        ${cells}
        <td class="num strong">${average}</td>
      </tr>
      ${open ? detailRow(student, subjects) : ''}`;
  }).join('');

  $('no-rows').hidden = students.length > 0;
  $('selected-count').textContent = state.selected.size;

  $('grades-body').querySelectorAll('[data-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      const key = button.dataset.toggle;
      if (state.openRows.has(key)) state.openRows.delete(key);
      else state.openRows.add(key);
      renderTable();
    });
  });
  $('grades-body').querySelectorAll('[data-select]').forEach((box) => {
    box.addEventListener('change', () => {
      if (box.checked) state.selected.add(box.dataset.select);
      else state.selected.delete(box.dataset.select);
      $('selected-count').textContent = state.selected.size;
      if (state.onlySelected) renderTable();
    });
  });
}

function gradePill(data) {
  if (!data || !data.best) return '<span class="grade-pill none">—</span>';
  const cls = data.approved === true ? 'pass' : data.approved === false ? 'fail' : 'none';
  const epoca = data.best_epoca === 'epoca1' ? '1'
    : data.best_epoca === 'epoca2' ? '2'
    : data.best_epoca === 'especial' ? 'E' : '';
  // A nota que fica é a arredondada; a da pauta aparece na dica e no detalhe.
  const nota = data.best_rounded != null ? String(data.best_rounded) : data.best.label;
  const dica = data.best_rounded != null && data.best.label !== nota
    ? `${data.best_epoca_label} · ${t('detail.rounded', { value: data.best.label })}`
    : data.best_epoca_label;
  return `<span class="grade-pill ${cls}" title="${escapeHtml(dica)}">
    ${escapeHtml(nota)}${epoca ? `<small>${epoca}</small>` : ''}</span>`;
}

function detailRow(student, subjects) {
  const cards = subjects.filter((s) => student.subjects[s]).map((subject) => {
    const data = student.subjects[subject];
    const lines = (state.results.epocas || []).map((epoca) => {
      const info = data.epocas[epoca.key];
      if (!info) return '';
      const best = data.best_epoca === epoca.key;
      return `
        <div class="epoca-line ${best ? 'is-best' : ''}">
          <span>${escapeHtml(epoca.label)}${
            info.route_label ? `<span class="via">${escapeHtml(info.route_label)}</span>` : ''}</span>
          <span>${escapeHtml(info.grade.label)}
            ${best ? `<span class="tag">${escapeHtml(t('detail.best_tag'))}</span>` : ''}</span>
        </div>`;
    }).join('');

    const bestInfo = data.epocas[data.best_epoca] || {};
    return `
      <div class="detail-card">
        <h4>${escapeHtml(subject)}</h4>
        ${lines || `<p class="components">${escapeHtml(t('detail.no_grades'))}</p>`}
        <div class="source-note">
          ${escapeHtml(t('detail.best'))}: <b>${escapeHtml(
            data.best_rounded != null ? String(data.best_rounded) : (data.best?.label ?? '—'))}</b>
          ${data.best_rounded != null && data.best.label !== String(data.best_rounded)
            ? ` (${escapeHtml(t('detail.rounded', { value: data.best.label }))})` : ''}
          · ${escapeHtml(t('detail.pass_mark'))}: <b>${data.pass_mark}</b>
          ${bestInfo.column ? `<br>${escapeHtml(t('detail.column'))}: ${escapeHtml(bestInfo.column)}` : ''}
          ${bestInfo.source_label ? `<br>${escapeHtml(t('detail.source'))}: ${escapeHtml(bestInfo.source_label)}` : ''}
          ${(bestInfo.other_routes || []).length ? `<br>${escapeHtml(t('detail.other_route'))}: ${
            bestInfo.other_routes.map((a) =>
              escapeHtml(`${a.route || a.column}: ${a.label}`)).join(' · ')}` : ''}
          ${(bestInfo.other_versions || []).length ? `<br>${escapeHtml(t('detail.other_files'))}: ${
            bestInfo.other_versions.map((a) =>
              escapeHtml(`${a.label} (${a.source})`)).join(' · ')}` : ''}
        </div>
      </div>`;
  }).join('');

  const alternates = student.all_names.length > 1 || student.all_ids.length > 1 ? `
    <div class="detail-card">
      <h4>${escapeHtml(t('detail.identity'))}</h4>
      <div class="components">
        ${escapeHtml(t('detail.names'))}: <b>${escapeHtml(student.all_names.join(' · ') || '—')}</b><br>
        ${escapeHtml(t('detail.ids'))}: <b>${escapeHtml(student.all_ids.join(' · ') || '—')}</b>
      </div>
    </div>` : '';

  return `<tr class="detail-row"><td colspan="${subjects.length + 4}">
    <div class="detail-inner">${mediasCard(student)}${cards}${alternates}</div></td></tr>`;
}

function mediasCard(student) {
  const media = student.averages;
  if (!media || (!media.final && !media.semesters.length)) return '';

  const linha = (rotulo, entrada) => `
    <div class="item"><span>${escapeHtml(rotulo)}</span>
      <b>${num(entrada.value)}</b>
      <span class="components">${escapeHtml(t('medias.count', {
        n: entrada.count,
        ects: entrada.weighted ? t('medias.ects', { value: num(entrada.ects) }) : '',
      }))}</span></div>`;

  const semestres = media.semesters.map((s) =>
    linha(t('medias.semester', { year: s.year, semester: s.semester }), s)).join('');
  const anos = media.years.map((a) => linha(t('medias.year', { year: a.year }), a)).join('');
  const cobertura = media.coverage || {};

  return `
    <div class="detail-card medias-card">
      <h4>${escapeHtml(t('medias.title'))}</h4>
      <div class="medias">
        ${semestres}${anos}
        ${media.final ? `<div class="item final"><span>${escapeHtml(t('medias.final'))}</span>
          <b>${num(media.final.value)}</b>
          <span class="components">(${escapeHtml(t('medias.rounded', { value: media.final.rounded }))})</span></div>` : ''}
      </div>
      <div class="source-note">
        ${media.course ? `<b>${escapeHtml(t('medias.course', { name: media.course }))}</b><br>` : ''}
        ${cobertura.total ? escapeHtml(t('medias.coverage', {
          have: cobertura.have, total: cobertura.total })) : ''}
        ${(cobertura.missing || []).length
          ? `<br>${escapeHtml(t('medias.coverage_missing', { list: cobertura.missing.join(' · ') }))}` : ''}
        <br>${escapeHtml(t('medias.note'))}
        ${media.final && media.final.weighted
          ? escapeHtml(t('medias.weighted')) : escapeHtml(t('medias.simple'))}
        ${(media.missing_curriculum || []).length
          ? `<br>${escapeHtml(t('medias.missing', { list: media.missing_curriculum.join(' · ') }))}` : ''}
      </div>
    </div>`;
}

function renderNotices() {
  const data = state.results;
  const entries = [...(data.conflicts || []), ...(data.warnings || [])];
  if (!entries.length) {
    $('notices').innerHTML = `
      <div class="notice info"><span class="icon">✓</span>
      <span>${escapeHtml(t('notices.none'))}</span></div>`;
    return;
  }
  $('notices').innerHTML = `
    <details class="notice-group">
      <summary>${escapeHtml(t('notices.title', { n: entries.length }))}</summary>
      <div>${entries.map((entry) => `
        <div class="notice ${entry.severity === 'warning' ? 'warning' : 'info'}">
          <span class="icon">${entry.severity === 'warning' ? '!' : 'i'}</span>
          <span>
            <b>${escapeHtml(entry.student || entry.type_label || entry.type)}${
              entry.subject ? ' — ' + escapeHtml(entry.subject) : ''}${
              entry.epoca ? ' (' + escapeHtml(entry.epoca) + ')' : ''}</b>
            ${escapeHtml(entry.detail)}
            ${entry.chosen ? `<br><small>${escapeHtml(t('notices.chosen'))} <b>${escapeHtml(entry.chosen)}</b></small>` : ''}
          </span>
        </div>`).join('')}</div>
    </details>`;
}

/* -------------------------------------------------------------- exportar */

async function exportExcel() {
  const students = state.selected.size ? [...state.selected] : null;
  const filename = t('excel.filename');
  busy(true, t('busy.excel'));
  try {
    const response = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ students, subjects: visibleSubjects(), filename }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || `Erro ${response.status}`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    toast(students ? t('toast.excel_students', { n: students.length }) : t('toast.excel'));
  } catch (error) { toast(error.message, true); } finally { busy(false); }
}

/* ------------------------------------------------------------- arranque */

function setup() {
  let saved = null;
  try { saved = localStorage.getItem('gradeorg.lang'); } catch (error) { /* privado */ }
  setLanguage(saved || 'pt');
  paintLanguage();
  applyStaticText();

  setupDropzone();

  document.querySelectorAll('#lang button').forEach((button) => {
    button.addEventListener('click', () => switchLanguage(button.dataset.lang));
  });

  document.querySelectorAll('.step').forEach((button) => {
    button.addEventListener('click', () => {
      if (button.disabled) return;
      const step = button.dataset.step;
      if (step === 'results') loadResults();
      else goto(step);
    });
  });

  $('btn-to-review').addEventListener('click', () => { renderReview(); goto('review'); });
  $('btn-back-upload').addEventListener('click', () => goto('upload'));
  $('btn-back-review').addEventListener('click', () => { renderReview(); goto('review'); });
  $('btn-to-results').addEventListener('click', loadResults);
  $('btn-add-more').addEventListener('click', () => goto('upload'));
  $('btn-export').addEventListener('click', exportExcel);

  $('btn-reset').addEventListener('click', async () => {
    if (!window.confirm(t('memory.confirm'))) return;
    busy(true, t('busy.clearing'));
    try {
      state.review = await postJSON('/api/reset');
      state.results = null;
      state.selected.clear();
      state.openRows.clear();
      state.hiddenSubjects.clear();
      renderFiles();
      renderUploadErrors([]);
      refreshStepAvailability();
      goto('upload');
    } catch (error) { toast(error.message, true); } finally { busy(false); }
  });

  let searchTimer;
  $('search').addEventListener('input', (event) => {
    state.search = event.target.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(renderTable, 130);
  });

  $('only-selected').addEventListener('change', (event) => {
    state.onlySelected = event.target.checked;
    renderTable();
  });
  $('btn-select-visible').addEventListener('click', () => {
    filteredStudents().forEach((student) => state.selected.add(student.key));
    renderTable();
  });
  $('btn-clear-selection').addEventListener('click', () => {
    state.selected.clear();
    state.onlySelected = false;
    $('only-selected').checked = false;
    renderTable();
  });

  $('pass-mark').addEventListener('change', (event) =>
    saveSettings({ pass_mark: parseFloat(event.target.value) }));
  $('merge-by-name').addEventListener('change', (event) =>
    saveSettings({ merge_by_name: event.target.checked }));

  // A sessão anterior é retomada tal como ficou -- língua incluída, porque
  // quem manda é o que ficou guardado no servidor.
  api('/api/state').then((data) => {
    state.review = data;
    if (data.language && data.language !== LANG) {
      setLanguage(data.language);
      try { localStorage.setItem('gradeorg.lang', data.language); } catch (e) { /* privado */ }
      paintLanguage();
      applyStaticText();
    }
    renderFiles();
    refreshStepAvailability();
    if (data.files.length) { renderReview(); goto('review'); }
  }).catch(() => {});
}

document.addEventListener('DOMContentLoaded', setup);
