// ===== Logistician Requests JS =====
const $ = (id) => document.getElementById(id);

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/[&<>"']/g, (m) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[m]);
}

function openModal(id){ const el = $(id); if(el) el.style.display = 'block'; }
function closeModal(id){ const el = $(id); if(el) el.style.display = 'none'; }

document.addEventListener('click', e => {
  const btn = e.target.closest('[data-close]');
  if (btn) closeModal(btn.dataset.close);
});

async function loadSuppliers(materialId){
  const select = $('selectSupplier');
  if(!select) return;

  select.innerHTML = `<option>Загрузка…</option>`;
  const res = await fetch(`/api/logistician/suppliers?material_id=${materialId}`);
  const data = await res.json();

  if(!data.length){
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

async function loadRequests(){
  const tbody = $('requestsTbody');
  if(!tbody) return;

  tbody.innerHTML = `<tr><td colspan="6" class="logi-loading">Загрузка…</td></tr>`;

  const res = await fetch('/api/logistician/requests');
  const list = await res.json();

  if(!list.length){
    tbody.innerHTML = `<tr><td colspan="6" class="logi-empty">Нет заявок</td></tr>`;
    return;
  }

  tbody.innerHTML = list.map(r => {
    const dt = (r.requested_date && r.requested_time_slot) ? `${r.requested_date} ${r.requested_time_slot}` : '—';
    return `
      <tr>
        <td class="logi-td-strong">${escapeHtml(r.type)}</td>
        <td>${escapeHtml(r.material || '—')}</td>
        <td>${escapeHtml(r.quantity || '—')}</td>
        <td>${escapeHtml(dt)}</td>
        <td class="logi-muted">${escapeHtml(r.notes || '')}</td>
        <td class="logi-td-right">
          <button class="btn btn-primary btn-sm js-approve"
            data-id="${r.id}"
            data-material-id="${r.material_id || ''}"
            data-date="${r.requested_date || ''}"
            data-time="${r.requested_time_slot || ''}">
            Рассмотреть
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

async function openApproveModal(reqId, materialId, prefDate, prefTime){
  if(!$('approveModal')) return;

  $('requestId').value = reqId;
  if($('approveHint')) $('approveHint').textContent = '';

  if(prefDate) $('deliveryDate').value = prefDate;
  if(prefTime) $('deliveryTime').value = prefTime;

  if(materialId) await loadSuppliers(materialId);
  openModal('approveModal');
}

document.addEventListener('click', async (e) => {
  const a = e.target.closest('.js-approve');
  if(a){
    await openApproveModal(
      a.getAttribute('data-id'),
      a.getAttribute('data-material-id'),
      a.getAttribute('data-date'),
      a.getAttribute('data-time')
    );
  }
});

const rejectBtn = $('rejectBtn');
if(rejectBtn){
  rejectBtn.addEventListener('click', async () => {
    const id = $('requestId')?.value;
    if(!id) return;
    await fetch(`/api/logistician/requests/${id}/reject`, { method: 'POST' });
    closeModal('approveModal');
    await loadRequests();
  });
}

const approveBtn = $('approveBtn');
if(approveBtn){
  approveBtn.addEventListener('click', async () => {
    const id = $('requestId')?.value;
    if(!id) return;

    const payload = {
      delivery_date: $('deliveryDate')?.value,
      delivery_time: $('deliveryTime')?.value,
      supplier_id: $('selectSupplier')?.value,
      duration_min: $('deliveryDuration')?.value || 15,
    };

    if(!payload.delivery_date || !payload.delivery_time || !payload.supplier_id){
      if($('approveHint')) $('approveHint').textContent = 'Заполните дату, время и поставщика.';
      return;
    }

    const res = await fetch(`/api/logistician/requests/${id}/approve`, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if(data.success){
      closeModal('approveModal');
      await loadRequests();
    }else{
      if($('approveHint')) $('approveHint').textContent = data.error || 'Ошибка при одобрении';
    }
  });
}

document.addEventListener('DOMContentLoaded', async () => {
  await loadRequests();
});
