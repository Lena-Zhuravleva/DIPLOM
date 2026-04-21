// ===== Logistician Calendar JS =====
const $ = (id) => document.getElementById(id);

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/[&<>"']/g, (m) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[m]);
}

// ----- modal helpers -----
function openModal(id) { const el = $(id); if (el) el.style.display = 'block'; }
function closeModal(id) { const el = $(id); if (el) el.style.display = 'none'; }

// close modal by [data-close]
document.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-close]');
  if (btn) closeModal(btn.dataset.close);
});

// ----- time helpers -----
function timeToMin(t) { // "08:15" -> 495
  const [h, m] = String(t || '00:00').split(':').map(Number);
  return h * 60 + m;
}
function minToTime(min) {
  const h = String(Math.floor(min / 60)).padStart(2, '0');
  const m = String(min % 60).padStart(2, '0');
  return `${h}:${m}`;
}

// ===== Calendar =====
async function loadCalendar(dateStr) {
  const thead = $('calendarThead');
  const tbody = $('calendarTbody');
  if (!thead || !tbody) return;

  thead.innerHTML = '';
  tbody.innerHTML = `<tr><td class="logi-loading">Загрузка…</td></tr>`;

  const res = await fetch(`/api/logistician/calendar?date=${dateStr}`);
  const data = await res.json();

  if (!data.success) {
    tbody.innerHTML = `<tr><td class="logi-error">Ошибка: ${escapeHtml(data.error || 'unknown')}</td></tr>`;
    return;
  }

  thead.innerHTML = `
    <tr>
      <th class="col-time">Время</th>
      ${data.places.map(p => `
        <th>
          <div class="th-title">${escapeHtml(p.title)}</div>
          <div class="th-sub">план / факт</div>
        </th>
      `).join('')}
    </tr>
  `;

  tbody.innerHTML = data.rows.map(row => {
    const time = row.time;

    const cellsHtml = data.places.map(p => {
      const cell = row.cells?.[p.id] || { plan: null, fact: null };
      const plan = cell.plan;
      const fact = cell.fact;

      let cellClass = 'cell free';
      let mainHtml = '';
      let actionHtml = '';

      if (plan) {
        if (plan.kind === 'delivery') {
          cellClass = 'cell busy';
          mainHtml = `
            <div class="cell-main">
              <div class="cell-line strong">${escapeHtml(plan.supplier || '')}</div>
              <div class="cell-line">${escapeHtml(plan.material || '')}${plan.quantity ? ' • ' + escapeHtml(plan.quantity) : ''}</div>
            </div>
          `;
          actionHtml = `
              <div class="cell-actions">
                <button class="btn btn-danger btn-sm js-delete-delivery"
                  data-id="${plan.id}">
                  Удалить
                </button>
              </div>
            `;
        } else {
          cellClass = 'cell pending';
          mainHtml = `
            <div class="cell-main">
              <div class="cell-line strong">${escapeHtml(plan.supplier || 'Заявка')}</div>
              <div class="cell-line">${escapeHtml(plan.material || '—')}${plan.quantity ? ' • ' + escapeHtml(plan.quantity) : ''}</div>
            </div>
          `;
        }
      }

      const factDot = fact ? `<span class="fact-dot" title="Есть факт разгрузки"></span>` : '';

      return `
        <td class="place-cell"
            data-date="${dateStr}"
            data-time="${time}"
            data-place="${p.id}"
            data-plan-kind="${plan ? plan.kind : ''}">
          <div class="${cellClass}">
            ${factDot}
            ${mainHtml}
            ${actionHtml}
          </div>
        </td>
      `;
    }).join('');

    return `
      <tr class="slot-row">
        <td class="logi-td-strong">${escapeHtml(time)}</td>
        ${cellsHtml}
      </tr>
    `;
  }).join('');
}

async function openCreateModal(date, time, place) {
  if ($('cmDate')) $('cmDate').value = date;
  if ($('cmTime')) $('cmTime').value = time;
  if ($('cmUnloadPlace')) $('cmUnloadPlace').value = place;
  if ($('cmDuration')) $('cmDuration').value = 15;

  if ($('cmQuantity')) $('cmQuantity').value = 1;
  if ($('cmNotes')) $('cmNotes').value = '';

  const hint = $('createHint');
  if (hint) hint.textContent = `Выбрано: ${date}, ${time}, ${place}`;

  await loadSuppliersForCreateModal();
  await loadAllMaterialsForCreateModal();

  openModal('createModal');
}

document.addEventListener('click', (e) => {
  const td = e.target.closest('.place-cell');
  if (!td) return;

  if (e.target.closest('button')) return;

  const planKind = td.getAttribute('data-plan-kind');
  if (planKind === 'delivery') return;

  const date = td.getAttribute('data-date');
  const time = td.getAttribute('data-time');
  const place = td.getAttribute('data-place');

  openCreateModal(date, time, place);
});
//функция загрузки всех поставщиков
async function loadSuppliersForCreateModal() {
  const s = $('cmSupplier');
  if (!s) return;

  s.innerHTML = `<option>Загрузка…</option>`;

  const res = await fetch('/api/logistician/all_suppliers');
  const list = await res.json();

  if (!Array.isArray(list) || !list.length) {
    s.innerHTML = `<option value="">Нет поставщиков</option>`;
    return;
  }

  s.innerHTML =
    `<option value="">— Выберите поставщика —</option>` +
    list.map(x => `<option value="${x.id}">${escapeHtml(x.company_name)}</option>`).join('');
}
//функция загрузки всех материалов
async function loadAllMaterialsForCreateModal() {
  const matSel = $('cmMaterialId');
  if (!matSel) return;

  matSel.innerHTML = `<option>Загрузка…</option>`;

  const res = await fetch('/api/logistician/all_materials');
  const list = await res.json();

  if (!Array.isArray(list) || !list.length) {
    matSel.innerHTML = `<option value="">Нет материалов</option>`;
    return;
  }

  matSel.innerHTML =
    `<option value="">— Выберите материал —</option>` +
    list.map(m => `<option value="${m.id}">${escapeHtml(m.name)} (${escapeHtml(m.unit)})</option>`).join('');
}
// проверка сохранения заявки
const createBtn = $('createBtn');
if (createBtn) {
  createBtn.addEventListener('click', async () => {
    const err = $('createErr');
    if (err) err.textContent = '';

    const payload = {
      material_id: $('cmMaterialId')?.value || '',
      supplier_id: $('cmSupplier')?.value || '',
      quantity: $('cmQuantity')?.value || '',
      requested_date: $('cmDate')?.value || '',
      requested_time_slot: $('cmTime')?.value || '',
      duration_min: $('cmDuration')?.value || '15',
      unload_place: $('cmUnloadPlace')?.value || '',
      notes: $('cmNotes')?.value || ''
    };

    if (!payload.supplier_id) {
      if (err) err.textContent = 'Выберите поставщика.';
      return;
    }

    if (!payload.material_id) {
      if (err) err.textContent = 'Выберите материал.';
      return;
    }

    if (!payload.quantity || !payload.requested_date || !payload.requested_time_slot) {
      if (err) err.textContent = 'Заполните дату, время и количество.';
      return;
    }

    const res = await fetch('/api/logistician/create_request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (data.success) {
      closeModal('createModal');
      const d = $('calendarDate')?.value;
      if (d) await loadCalendar(d);
      alert('Заявка создана');
    } else {
      if (err) err.textContent = data.error || 'Ошибка при создании заявки';
    }
  });
}
// ===== Selection + Create modal =====
let sel = { isDown: false, startCell: null, endCell: null, place: null, date: null };

// ===== approve modal (optional, if you keep approveModal on calendar) =====
async function loadSuppliersForApprove(materialId) {
  const select = $('selectSupplier');
  if (!select) return;

  select.innerHTML = `<option>Загрузка…</option>`;
  const res = await fetch(`/api/logistician/suppliers?material_id=${materialId}`);
  const data = await res.json();

  if (!data.length) {
    select.innerHTML = `<option value="">Нет подходящих поставщиков</option>`;
    return;
  }

  select.innerHTML =
    `<option value="">— Выберите —</option>` +
    data.map(s => `
      <option value="${s.id}">
        ${escapeHtml(s.company_name)} | ${escapeHtml(s.delivery_zone)} | ⭐ ${s.rating}
      </option>
    `).join('');
}
//функция загрузки плана
function renderMaterialStatus(status) {
  if (!status) return '—';

  let text = status;
  if (status === 'normal') text = 'Обычный';
  if (status === 'warning') text = 'Внимание';
  if (status === 'critical') text = 'Критический';

  return `<span class="status-badge status-${status}">${text}</span>`;
}

function renderPlanStatus(status) {
  if (!status) return '—';

  let text = status;
  if (status === 'planned') text = 'Запланировано';
  if (status === 'in_progress') text = 'В работе';
  if (status === 'completed') text = 'Завершено';

  return `<span class="status-badge status-${status}">${text}</span>`;
}

async function loadPlanInsideModal() {
  const tbody = $('planInsideTbody');
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="8" class="logi-loading">Загрузка…</td></tr>`;

  const res = await fetch('/api/logistician/procurement-plan');
  const data = await res.json();

  if (!data.success) {
    tbody.innerHTML = `<tr><td colspan="8" class="logi-error">Ошибка загрузки плана</td></tr>`;
    return;
  }

  if (!data.items || !data.items.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="logi-empty">План закупок пуст</td></tr>`;
    return;
  }

  tbody.innerHTML = data.items.map(item => `
    <tr>
      <td>${item.id}</td>
      <td>${escapeHtml(item.material || '—')}</td>
      <td>${item.current_stock ?? '—'}</td>
      <td>${item.min_stock_level ?? '—'}</td>
      <td>${renderMaterialStatus(item.material_status)}</td>
      <td>${item.quantity ?? '—'}</td>
      <td>${escapeHtml(item.planned_date || '—')}</td>
      <td>${renderPlanStatus(item.status)}</td>
    </tr>
  `).join('');
}
//обработчик кнопки
const togglePlanBtn = $('togglePlanBtn');
if (togglePlanBtn) {
  togglePlanBtn.addEventListener('click', async () => {
    const block = $('planInsideModal');
    if (!block) return;

    const isHidden = block.style.display === 'none' || block.style.display === '';
    if (isHidden) {
      block.style.display = 'block';
      togglePlanBtn.textContent = 'Скрыть план закупок';
      await loadPlanInsideModal();
    } else {
      block.style.display = 'none';
      togglePlanBtn.textContent = 'Открыть план закупок';
    }
  });
}

async function openApproveModal(reqId, materialId, prefDate, prefTime) {
  if (!$('approveModal')) return;

  $('requestId').value = reqId;
  $('approveHint').textContent = '';

  if (prefDate) $('deliveryDate').value = prefDate;
  if (prefTime) $('deliveryTime').value = prefTime;

  if (materialId) await loadSuppliersForApprove(materialId);
  openModal('approveModal');
}

document.addEventListener('click', async (e) => {
  const a = e.target.closest('.js-approve');
  if (a) {
    await openApproveModal(
      a.getAttribute('data-id'),
      a.getAttribute('data-material-id'),
      a.getAttribute('data-date'),
      a.getAttribute('data-time')
    );
  }
});

const rejectBtn = $('rejectBtn');
if (rejectBtn) {
  rejectBtn.addEventListener('click', async () => {
    const id = $('requestId')?.value;
    if (!id) return;
    await fetch(`/api/logistician/requests/${id}/reject`, { method: 'POST' });
    closeModal('approveModal');
    const d = $('calendarDate')?.value;
    if (d) await loadCalendar(d);
  });
}

const approveBtn = $('approveBtn');
if (approveBtn) {
  approveBtn.addEventListener('click', async () => {
    const id = $('requestId')?.value;
    if (!id) return;

    const payload = {
      delivery_date: $('deliveryDate')?.value,
      delivery_time: $('deliveryTime')?.value,
      supplier_id: $('selectSupplier')?.value,
      duration_min: $('deliveryDuration')?.value || 15,
    };

    if (!payload.delivery_date || !payload.delivery_time || !payload.supplier_id) {
      if ($('approveHint')) $('approveHint').textContent = 'Заполните дату, время и поставщика.';
      return;
    }

    const res = await fetch(`/api/logistician/requests/${id}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (data.success) {
      closeModal('approveModal');
      const d = $('calendarDate')?.value;
      if (d) await loadCalendar(d);
    } else {
      if ($('approveHint')) $('approveHint').textContent = data.error || 'Ошибка при одобрении';
    }
  });
}

// ===== date controls =====
function setToday() {
  const d = $('calendarDate');
  if (d) d.value = new Date().toISOString().slice(0, 10);
}

const todayBtn = $('todayBtn');
if (todayBtn) {
  todayBtn.addEventListener('click', async () => {
    setToday();
    const d = $('calendarDate')?.value;
    if (d) await loadCalendar(d);
  });
}

const calDate = $('calendarDate');
if (calDate) {
  calDate.addEventListener('change', async () => {
    if (calDate.value) await loadCalendar(calDate.value);
  });
}
//обработчик удаления поставки
document.addEventListener('click', async (e) => {
  const btn = e.target.closest('.js-delete-delivery');
  if (!btn) return;

  const ok = confirm('Удалить поставку?');
  if (!ok) return;

  const id = btn.getAttribute('data-id');

  const res = await fetch(`/api/logistician/deliveries/${id}/delete`, {
    method: 'POST'
  });

  const data = await res.json();
  if (data.success) {
    const d = $('calendarDate')?.value;
    if (d) await loadCalendar(d);
  } else {
    alert(data.error || 'Ошибка удаления');
  }
});

// init
document.addEventListener('DOMContentLoaded', async () => {
  if ($('calendarDate') && $('calendarTbody')) {
    setToday();
    await loadCalendar($('calendarDate').value);
  }
});
