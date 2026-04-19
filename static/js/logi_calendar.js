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

// init
document.addEventListener('DOMContentLoaded', async () => {
  if ($('calendarDate') && $('calendarTbody')) {
    setToday();
    await loadCalendar($('calendarDate').value);
  }
});
