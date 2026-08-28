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
  busy(true, `A ler ${fileList.length} ficheiro(s)…`);
  try {
    const data = await postJSON_form(form);
    state.review = data;
    state.results = null;
    renderFiles();
    renderUploadErrors(data.rejected || []);
    refreshStepAvailability();
    if ((data.accepted || []).length) {
      toast(`${data.accepted.length} ficheiro(s) lido(s).`);
      renderReview();
      goto('review');
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    busy(false);
  }
}

const postJSON_form = (form) =>
  api('/api/upload', { method: 'POST', body: form });

function renderFiles() {
  const files = state.review?.files || [];
  $('file-list').innerHTML = files.map((file) => {
    const sources = (state.review.sources || []).filter((s) => s.filename === file.name);
    const subjects = [...new Set(sources.map((s) => s.subject.value).filter(Boolean))];
    return `
      <div class="file-card">
        <div class="file-kind">${escapeHtml(file.kind.toUpperCase())}</div>
        <div class="grow">
          <div class="name">${escapeHtml(file.name)}</div>
          <div class="meta">
            ${file.tables} tabela(s)
            ${subjects.length ? ' · ' + escapeHtml(subjects.join(', ')) : ''}
            ${sources.length ? ' · ' + sources.reduce((n, s) => n + s.row_count, 0) + ' linhas' : ''}
          </div>
        </div>
        <button class="icon-btn" data-remove="${escapeHtml(file.name)}"
                title="Remover ficheiro">✕</button>
      </div>`;
  }).join('');

  $('file-list').querySelectorAll('[data-remove]').forEach((button) => {
    button.addEventListener('click', async () => {
      busy(true, 'A remover…');
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
      <span class="icon">⚠</span>
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
      <div class="card">
        <h2 class="section-title">Está tudo identificado ✓</h2>
        <p class="section-lead">Todas as unidades curriculares e épocas foram
        reconhecidas automaticamente. Pode ver as notas consolidadas — ou abrir os
        ajustes avançados para confirmar coluna a coluna.</p>
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
        <input type="text" placeholder="…ou escreva o nome da unidade curricular"
               data-custom="${escapeHtml(question.id)}"
               value="${escapeHtml(customValue(question))}">
        <button class="btn btn-ghost btn-sm" data-custom-save="${escapeHtml(question.id)}">Usar</button>
      </div>` : '';

    return `
      <div class="card question ${question.severity === 'warning' ? 'is-warning' : ''}"
           data-question="${escapeHtml(question.id)}">
        <h3>${escapeHtml(question.title)}</h3>
        ${question.detail ? `<p class="detail">${escapeHtml(question.detail)}</p>` : ''}
        <div class="choices">${choices}</div>
        ${custom}
      </div>`;
  }).join('');

  container.innerHTML = `
    <div class="card">
      <h2 class="section-title">Faltam ${questions.length} confirmação(ões)</h2>
      <p class="section-lead">Os ficheiros não dizem tudo o que é preciso saber.
      A opção já marcada é o palpite da aplicação — clique nela para a confirmar,
      ou escolha outra. O que não for confirmado fica com o palpite.</p>
      <button class="btn btn-ghost btn-sm" id="accept-all">✓ Aceitar todos os palpites</button>
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
  busy(true, 'A aplicar…');
  try {
    state.review = await postJSON('/api/answers', { answers });
    state.results = null;
    renderReview();
    renderFiles();
  } catch (error) { toast(error.message, true); } finally { busy(false); }
}

async function saveSettings(settings) {
  busy(true, 'A aplicar…');
  try {
    state.review = await postJSON('/api/answers', { settings });
    state.results = null;
    renderReview();
  } catch (error) { toast(error.message, true); } finally { busy(false); }
}

async function saveOverride(sourceId, columnIndex, spec) {
  busy(true, 'A aplicar…');
  try {
    state.review = await postJSON('/api/answers',
      { overrides: { [sourceId]: { [columnIndex]: spec } } });
    state.results = null;
    renderReview();
  } catch (error) { toast(error.message, true); } finally { busy(false); }
}

function renderCurriculum() {
  const data = state.review;
  const subjects = data.subjects || [];
  if (!subjects.length) { $('curriculum').innerHTML = ''; return; }

  const curriculum = data.curriculum || {};
  const detected = data.detected_semesters || {};
  const marks = data.pass_marks || {};
  const codes = data.subject_codes || {};
  const porPreencher = subjects.filter((s) => {
    const meta = curriculum[s] || {};
    return meta.year == null || meta.semester == null;
  }).length;

  const linhas = subjects.map((subject) => {
    const meta = curriculum[subject] || {};
    const semestre = meta.semester ?? (detected[subject] ? Number(detected[subject]) : null);
    return `
      <tr>
        <td>
          <div class="uc-nome">${escapeHtml(subject)}</div>
          ${codes[subject] ? `<div class="uc-codigo">${escapeHtml(codes[subject])}</div>` : ''}
        </td>
        <td class="num ${meta.year == null ? 'falta' : ''}">
          <select data-uc="${escapeHtml(subject)}" data-campo="year">
            <option value="">—</option>
            ${[1, 2, 3, 4, 5].map((y) =>
              `<option value="${y}" ${meta.year === y ? 'selected' : ''}>${y}.º</option>`).join('')}
          </select>
        </td>
        <td class="num ${semestre == null ? 'falta' : ''}">
          <select data-uc="${escapeHtml(subject)}" data-campo="semester">
            <option value="">—</option>
            ${[1, 2].map((n) =>
              `<option value="${n}" ${semestre === n ? 'selected' : ''}>${n}.º</option>`).join('')}
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
      </tr>`;
  }).join('');

  $('curriculum').innerHTML = `
    <div class="card">
      <h2 class="section-title">Unidades curriculares</h2>
      <p class="section-lead">
        Diga a que ano e semestre pertence cada cadeira — é isso que permite as
        médias por semestre, por ano e a média final de curso. Os ECTS são
        opcionais: se os preencher em todas, as médias passam a ser ponderadas
        por eles; se não, é a média simples.
        ${porPreencher ? `<b>Faltam o ano ou o semestre em ${porPreencher} cadeira(s).</b>` : ''}
      </p>
      <table class="uc-table">
        <thead><tr>
          <th>Unidade curricular</th><th class="num">Ano</th><th class="num">Semestre</th>
          <th class="num">ECTS</th><th class="num">Nota mínima</th>
        </tr></thead>
        <tbody>${linhas}</tbody>
      </table>
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
}

const ROLE_LABELS = {
  name: 'Nome do aluno', id: 'Nº de aluno', grade: 'Nota', ignore: 'Ignorar',
};
const EPOCA_OPTIONS = [
  ['', '— sem época (componente comum)'],
  ['epoca1', '1.ª Época'], ['epoca2', '2.ª Época'], ['especial', 'Época Especial'],
];
// Dentro de uma época pode haver mais do que um momento de avaliação: o 1.º
// teste e o 2.º, que se faz no dia do exame.
const MOMENT_OPTIONS = [
  ['', '—'],
  ['1', '1.º teste / momento'],
  ['2', '2.º teste / momento'],
  ['3', '3.º momento'],
];

function renderSources() {
  $('sources').innerHTML = (state.review.sources || []).map((source) => {
    const rows = source.columns.map((column) => `
      <tr>
        <td><b>${escapeHtml(column.header)}</b></td>
        <td>
          <select data-src="${source.id}" data-col="${column.index}" data-field="role">
            ${Object.entries(ROLE_LABELS).map(([value, label]) =>
              `<option value="${value}" ${column.role === value ? 'selected' : ''}>${label}</option>`).join('')}
          </select>
        </td>
        <td>
          <select data-src="${source.id}" data-col="${column.index}" data-field="epoca"
                  ${column.role !== 'grade' ? 'disabled' : ''}>
            ${EPOCA_OPTIONS.map(([value, label]) =>
              `<option value="${value}" ${(column.epoca || '') === value ? 'selected' : ''}>${label}</option>`).join('')}
          </select>
        </td>
        <td>
          <select data-src="${source.id}" data-col="${column.index}" data-field="kind"
                  ${column.role !== 'grade' ? 'disabled' : ''}>
            <option value="final" ${column.kind === 'final' ? 'selected' : ''}>Nota final</option>
            <option value="component" ${column.kind === 'component' ? 'selected' : ''}>Componente</option>
          </select>
        </td>
        <td>
          <select data-src="${source.id}" data-col="${column.index}" data-field="moment"
                  ${column.role !== 'grade' ? 'disabled' : ''}>
            ${MOMENT_OPTIONS.map(([value, label]) =>
              `<option value="${value}" ${String(column.moment || '') === value ? 'selected' : ''}>${label}</option>`).join('')}
          </select>
        </td>
        <td>${column.moment && column.moment > 1
              ? `<span class="badge amber" title="${escapeHtml(column.evidence || '')}">2.º momento</span>`
              : ''}${column.route
              ? `<span class="badge">${column.route === 'exame' ? 'Exame' : 'Contínua'}</span>`
              : ''}</td>
        <td class="samples" title="${escapeHtml(column.samples.join(' · '))}">
          ${escapeHtml(column.samples.join(' · ')) || '—'}</td>
        <td><span class="badge ${column.confidence >= 0.7 ? 'green' : column.confidence >= 0.5 ? 'amber' : 'red'}"
                  title="${escapeHtml(column.reason)}">${Math.round(column.confidence * 100)}%</span></td>
      </tr>`).join('');

    return `
      <div class="source-block">
        <div class="source-head">
          <span class="title">${escapeHtml(source.filename)}</span>
          <div class="badge-row">
            <span class="badge">${escapeHtml(source.location)}</span>
            <span class="badge accent">${escapeHtml(source.subject.value || 'UC por definir')}</span>
            ${source.academic_year.value ? `<span class="badge">${escapeHtml(source.academic_year.value)}</span>` : ''}
            ${source.document_date ? `<span class="badge">documento de ${escapeHtml(source.document_date)}</span>` : ''}
            <span class="badge">${source.row_count} alunos</span>
            ${source.component_label
              ? `<span class="badge amber">só «${escapeHtml(source.component_label)}» (${source.component_weight}%)</span>`
              : ''}
          </div>
        </div>
        ${(source.notes || []).length ? `<p class="source-note">${
          source.notes.map(escapeHtml).join('<br>')}</p>` : ''}
        <table class="col-table">
          <thead><tr>
            <th>Coluna</th><th>É</th><th>Época</th><th>Tipo</th><th>Momento</th>
            <th>Via</th><th>Exemplos</th><th>Confiança</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }).join('');

  $('sources').querySelectorAll('select').forEach((select) => {
    select.addEventListener('change', () => {
      const { src, col, field } = select.dataset;
      const spec = { [field]: select.value };
      // Marcar uma coluna como nota sem dizer mais nada deixava-a sem época e
      // sem tipo, e portanto sem efeito nenhum no resultado.
      if (field === 'role' && select.value === 'grade') {
        const source = (state.review.sources || []).find((s) => s.id === src);
        const column = source?.columns.find((c) => String(c.index) === String(col));
        if (column && !column.epoca) spec.epoca = 'epoca1';
        if (column && column.kind !== 'final') spec.kind = 'component';
      }
      saveOverride(src, col, spec);
    });
  });
}

/* ---------------------------------------------------------- resultados */

async function loadResults() {
  busy(true, 'A juntar as notas…');
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
    <div class="stat"><div class="value">${stats.students}</div><div class="label">alunos</div></div>
    <div class="stat"><div class="value">${stats.subjects}</div><div class="label">unidades curriculares</div></div>
    <div class="stat green"><div class="value">${stats.approved}</div><div class="label">aprovações</div></div>
    <div class="stat red"><div class="value">${stats.failed}</div><div class="label">reprovações</div></div>
    <div class="stat"><div class="value">${stats.average ?? '—'}</div><div class="label">média das melhores notas</div></div>`;

  $('pending-warning').innerHTML = (data.questions || []).length ? `
    <div class="notice warning">
      <span class="icon">⚠</span>
      <span><b>${data.questions.length} confirmação(ões) por responder</b>
      As notas abaixo usam os palpites automáticos. Volte a «Confirmar» para as rever.</span>
    </div>` : '';

  renderPassMarks();

  $('subject-filters').innerHTML = data.subjects.map((subject) => `
    <button class="chip ${state.hiddenSubjects.has(subject) ? '' : 'is-on'}"
            data-subject="${escapeHtml(subject)}">${escapeHtml(subject)}</button>`).join('');
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
      <span class="titulo">Nota mínima de aprovação</span>
      ${data.subjects.map((subject) => `
        <label>
          <span>${escapeHtml(subject)}</span>
          <input type="number" min="0" max="20" step="0.5"
                 value="${marks[subject] ?? padrao}"
                 data-pass-mark="${escapeHtml(subject)}">
        </label>`).join('')}
      <span class="nota">cada cadeira tem a sua — em branco usa ${padrao}</span>
    </div>`;

  $('pass-marks').querySelectorAll('[data-pass-mark]').forEach((input) => {
    input.addEventListener('change', async () => {
      const subject = input.dataset.passMark;
      const raw = input.value.trim();
      const value = raw === '' ? '' : parseFloat(raw);
      if (raw !== '' && Number.isNaN(value)) { input.value = proprias[subject] ?? padrao; return; }
      busy(true, 'A aplicar…');
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

  $('grades-head').innerHTML = `
    <tr>
      <th style="width:34px"></th>
      <th style="width:96px">Nº</th>
      <th>Aluno</th>
      ${subjects.map((s) => `<th class="num">${escapeHtml(s)}</th>`).join('')}
      <th class="num" style="width:90px">Média</th>
    </tr>`;

  $('grades-body').innerHTML = students.map((student) => {
    const cells = subjects.map((subject) => {
      const data = student.subjects[subject];
      return `<td class="num">${gradePill(data)}</td>`;
    }).join('');

    const values = subjects
      .map((s) => student.subjects[s]?.best?.value)
      .filter((v) => typeof v === 'number');
    const average = values.length
      ? (values.reduce((a, b) => a + b, 0) / values.length).toFixed(2).replace('.', ',')
      : '—';

    const open = state.openRows.has(student.key);
    return `
      <tr class="${open ? 'is-open' : ''}" data-key="${escapeHtml(student.key)}">
        <td><input type="checkbox" data-select="${escapeHtml(student.key)}"
                   ${state.selected.has(student.key) ? 'checked' : ''}
                   aria-label="Seleccionar ${escapeHtml(student.name)}"></td>
        <td class="student-id">${escapeHtml(student.student_id || '—')}</td>
        <td>
          <div class="name-cell">
            <button class="toggle" data-toggle="${escapeHtml(student.key)}"
                    aria-label="Ver detalhe">▶</button>
            <span class="student-name">${escapeHtml(student.name)}</span>
          </div>
        </td>
        ${cells}
        <td class="num">${average}</td>
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
  const epoca = data.best_epoca === 'epoca1' ? '1.ª'
    : data.best_epoca === 'epoca2' ? '2.ª'
    : data.best_epoca === 'especial' ? 'esp.' : '';
  return `<span class="grade-pill ${cls}" title="${escapeHtml(data.best_epoca_label)}">
    ${escapeHtml(data.best.label)}${epoca ? `<small>${epoca}</small>` : ''}</span>`;
}

function detailRow(student, subjects) {
  const cards = subjects.filter((s) => student.subjects[s]).map((subject) => {
    const data = student.subjects[subject];
    const lines = (state.results.epocas || []).map((epoca) => {
      const info = data.epocas[epoca.key];
      if (!info) return '';
      const best = data.best_epoca === epoca.key;
      const components = Object.entries(info.components || {});
      return `
        <div class="epoca-line ${best ? 'is-best' : ''}">
          <span>${escapeHtml(epoca.label)}${
            info.route_label ? `<span class="via">${escapeHtml(info.route_label)}</span>` : ''}</span>
          <span>${escapeHtml(info.grade.label)}
            ${best ? '<span class="tag">melhor</span>' : ''}</span>
        </div>
        ${components.length ? `<div class="components">${
          components.map(([name, grade]) =>
            `${escapeHtml(name)}: <b>${escapeHtml(grade.label)}</b>`).join(' · ')}</div>` : ''}`;
    }).join('');

    const bestInfo = data.epocas[data.best_epoca] || {};
    return `
      <div class="detail-card">
        <h4>${escapeHtml(subject)}</h4>
        ${lines || '<p class="components">Sem notas registadas.</p>'}
        <div class="source-note">
          Nota final: <b>${escapeHtml(data.best?.label ?? '—')}</b>
          ${data.best_rounded != null ? ` (arredondada: ${data.best_rounded})` : ''}
          · mínima para passar: <b>${data.pass_mark}</b>
          ${bestInfo.column ? `<br>Coluna: ${escapeHtml(bestInfo.column)}` : ''}
          ${bestInfo.source_label ? `<br>Origem: ${escapeHtml(bestInfo.source_label)}` : ''}
          ${(bestInfo.other_routes || []).length ? `<br>Outra via: ${
            bestInfo.other_routes.map((a) =>
              escapeHtml(`${a.route || a.column}: ${a.label}`)).join(' · ')}` : ''}
          ${(bestInfo.other_versions || []).length ? `<br>Noutros ficheiros: ${
            bestInfo.other_versions.map((a) =>
              escapeHtml(`${a.label} (${a.source})`)).join(' · ')}` : ''}
        </div>
      </div>`;
  }).join('');

  const medias = mediasCard(student);
  const alternates = student.all_names.length > 1 || student.all_ids.length > 1 ? `
    <div class="detail-card">
      <h4>Identificação</h4>
      <div class="components">
        Nomes: <b>${escapeHtml(student.all_names.join(' · ') || '—')}</b><br>
        Números: <b>${escapeHtml(student.all_ids.join(' · ') || '—')}</b>
      </div>
    </div>` : '';

  return `<tr class="detail-row"><td colspan="${subjects.length + 4}">
    <div class="detail-inner">${medias}${cards}${alternates}</div></td></tr>`;
}

function mediasCard(student) {
  const media = student.averages;
  if (!media || (!media.final && !media.semesters.length)) return '';

  const num = (valor) => String(valor).replace('.', ',');
  const linha = (rotulo, entrada) => `
    <div class="item">${escapeHtml(rotulo)}: <b>${num(entrada.value)}</b>
      <span class="components">(${entrada.count} UC${entrada.count === 1 ? '' : 's'}${
        entrada.weighted ? `, ${num(entrada.ects)} ECTS` : ''})</span></div>`;

  const semestres = media.semesters.map((s) =>
    linha(`${s.year}.º ano · ${s.semester}.º sem.`, s)).join('');
  const anos = media.years.map((a) => linha(`${a.year}.º ano`, a)).join('');

  return `
    <div class="detail-card">
      <h4>Médias</h4>
      <div class="medias">
        ${semestres}${anos}
        ${media.final ? `<div class="item final">Média de curso:
          <b>${num(media.final.value)}</b> (arredondada: ${media.final.rounded})</div>` : ''}
      </div>
      <div class="source-note">
        Contam as cadeiras aprovadas com nota numérica.
        ${media.final && media.final.weighted
          ? 'Ponderadas por ECTS.'
          : 'Média simples — preencha os ECTS de todas as cadeiras para ponderar.'}
        ${media.missing_curriculum.length
          ? `<br>Sem ano/semestre, por isso fora das médias parciais: ${
              media.missing_curriculum.map(escapeHtml).join(' · ')}` : ''}
      </div>
    </div>`;
}

function renderNotices() {
  const data = state.results;
  const entries = [...(data.conflicts || []), ...(data.warnings || [])];
  if (!entries.length) {
    $('notices').innerHTML = `
      <div class="notice info"><span class="icon">✓</span>
      <span>Nenhum conflito: os ficheiros encaixaram todos sem ambiguidades.</span></div>`;
    return;
  }
  $('notices').innerHTML = `
    <details class="notice-group">
      <summary>${entries.length} aviso(s) e conflito(s) — vale a pena espreitar</summary>
      <div>${entries.map((entry) => `
        <div class="notice ${entry.severity === 'warning' ? 'warning' : 'info'}">
          <span class="icon">${entry.severity === 'warning' ? '⚠' : 'ℹ'}</span>
          <span>
            <b>${escapeHtml(entry.student || entry.type)}${
              entry.subject ? ' — ' + escapeHtml(entry.subject) : ''}${
              entry.epoca ? ' (' + escapeHtml(entry.epoca) + ')' : ''}</b>
            ${escapeHtml(entry.detail)}
            ${entry.chosen ? `<br><small>Foi usado: <b>${escapeHtml(entry.chosen)}</b></small>` : ''}
          </span>
        </div>`).join('')}</div>
    </details>`;
}

/* -------------------------------------------------------------- exportar */

async function exportExcel() {
  const students = state.selected.size ? [...state.selected] : null;
  busy(true, 'A criar o Excel…');
  try {
    const response = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ students, subjects: visibleSubjects() }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || `Erro ${response.status}`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'notas-consolidadas.xlsx';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    toast(students ? `Excel criado com ${students.length} aluno(s).` : 'Excel criado.');
  } catch (error) { toast(error.message, true); } finally { busy(false); }
}

/* ------------------------------------------------------------- arranque */

function setup() {
  setupDropzone();

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
    busy(true, 'A limpar…');
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

  api('/api/state').then((data) => {
    state.review = data;
    renderFiles();
    refreshStepAvailability();
    if (data.files.length) { renderReview(); goto('review'); }
  }).catch(() => {});
}

document.addEventListener('DOMContentLoaded', setup);
