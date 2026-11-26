/**
 * 应用管理 · 证书（卡片布局对齐「我的应用」）
 */
async function renderCerts() {
  const U = MDMUtils;
  let allCerts = [];
  let keyword = '';
  let loadError = '';

  function esc(s) {
    return U._escapeHtml ? U._escapeHtml(s) : String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function fmtSize(n) {
    const v = Number(n) || 0;
    if (v < 1024) return `${v} B`;
    if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
    return `${(v / 1024 / 1024).toFixed(2)} MB`;
  }

  function filteredCerts() {
    const kw = keyword.trim().toLowerCase();
    if (!kw) return allCerts;
    return allCerts.filter(c => {
      const hay = [
        c.cert_name,
        c.file_name,
        c.cert_type_label,
        c.expiration_date
      ].map(x => String(x || '').toLowerCase()).join(' ');
      return hay.includes(kw);
    });
  }

  async function loadCerts() {
    try {
      allCerts = (await MDMApi.listStoreCerts()) || [];
      loadError = '';
    } catch (e) {
      allCerts = [];
      loadError = e.message || '加载证书失败';
    }
  }

  function cardsHtml() {
    if (loadError) {
      return `<div class="panel"><div class="panel-body text-muted">${esc(loadError)}</div></div>`;
    }
    const certs = filteredCerts();
    if (!allCerts.length) {
      return `<div class="panel"><div class="panel-body text-muted">暂无证书，请点击右上角新增</div></div>`;
    }
    if (!certs.length) {
      return `<div class="panel"><div class="panel-body text-muted">未找到匹配的证书</div></div>`;
    }
    return `<div class="card-grid">${certs.map(c => `
      <div class="entity-card">
        <div class="entity-card-badges">
          ${c.has_pem
            ? '<span class="badge badge-ok">可用</span>'
            : '<span class="badge badge-off">未解析</span>'}
        </div>
        <div class="entity-card-head entity-card-head--vcenter">
          <div>
            <div class="entity-title entity-title-ellipsis" title="${esc(c.cert_name || '')}">${esc(c.cert_name || '—')}</div>
            <div class="entity-sub">${esc(c.cert_type_label || '发布证书')}</div>
          </div>
        </div>
        <div class="entity-card-body">
          <div class="entity-stats">
            <span>文件 <strong>${esc(c.file_name || '—')}${c.file_size != null ? ` · ${fmtSize(c.file_size)}` : ''}</strong></span>
            <span>过期 <strong>${esc(c.expiration_date || '—')}</strong></span>
          </div>
          ${c.create_time ? `<div class="entity-desc">创建于 ${esc(c.create_time)}</div>` : ''}
        </div>
        <div class="entity-card-foot">
          <div class="entity-card-actions-main">
            ${c.download_url
              ? `<button type="button" class="btn btn-sm btn-primary btn-dl-cert" data-url="${esc(c.download_url)}" data-name="${esc(c.file_name || c.cert_name || 'cert.cer')}">下载</button>`
              : `<button type="button" class="btn btn-sm" disabled>下载</button>`}
          </div>
          <div class="entity-card-actions-more">
            <button type="button" class="btn btn-sm btn-link btn-text-danger btn-del-cert" data-id="${esc(c.id)}" data-name="${esc(c.cert_name)}">删除</button>
          </div>
        </div>
      </div>`).join('')}</div>`;
  }

  function openAddCert() {
    U.modal({
      title: '新增证书',
      size: 'md',
      okText: '上传',
      body: `
        <div class="form-item" style="margin-bottom:16px">
          <label class="form-label">证书名称 <span style="color:var(--error)">*</span></label>
          <input id="cert-name" class="form-input" maxlength="128" placeholder="如：发布证书-1" autocomplete="off">
        </div>
        <div class="form-item" style="margin-bottom:0">
          <label class="form-label">证书文件 <span style="color:var(--error)">*</span></label>
          <input id="cert-file" type="file" accept=".csr,.cer,.pem,.crt">
        </div>
        <p id="cert-err" style="display:none;margin:12px 0 0;font-size:12px;color:var(--error)"></p>`,
      onOk: async () => {
        const nameEl = document.getElementById('cert-name');
        const fileEl = document.getElementById('cert-file');
        const err = document.getElementById('cert-err');
        const showErr = (m) => {
          if (err) { err.style.display = 'block'; err.textContent = m; }
        };
        if (err) { err.style.display = 'none'; err.textContent = ''; }
        const name = (nameEl && nameEl.value || '').trim();
        const file = fileEl && fileEl.files && fileEl.files[0];
        if (!name) { showErr('请填写证书名称'); return false; }
        if (!file) { showErr('请选择证书文件'); return false; }
        try {
          await MDMApi.addStoreCert(name, file);
          U.toast('证书已添加');
          await refresh();
          return true;
        } catch (e) {
          showErr(e.message || '添加失败');
          return false;
        }
      }
    });
  }

  let listEl = null;

  async function refresh() {
    await loadCerts();
    if (listEl) listEl.innerHTML = cardsHtml();
    bindList();
  }

  function redrawList() {
    if (listEl) listEl.innerHTML = cardsHtml();
    bindList();
  }

  function bindList() {
    document.querySelectorAll('.btn-dl-cert').forEach(btn => {
      btn.addEventListener('click', async () => {
        try {
          await MDMApi.downloadStoreFile(btn.dataset.url, btn.dataset.name || 'cert.cer');
        } catch (e) {
          U.toast(e.message || '下载失败', 'error');
        }
      });
    });
    document.querySelectorAll('.btn-del-cert').forEach(btn => {
      btn.addEventListener('click', () => {
        U.confirm(`确认删除证书「${btn.dataset.name || ''}」？`, async () => {
          try {
            await MDMApi.deleteStoreCert(btn.dataset.id);
            U.toast('已删除');
            await refresh();
          } catch (e) {
            U.toast(e.message || '删除失败', 'error');
          }
        });
      });
    });
  }

  await loadCerts();

  MDMLayout.mount({
    pageId: 'certs',
    title: '证书',
    content: `
      <div class="toolbar">
        <div class="toolbar-left">
          <div class="search-box"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/></svg>
            <input id="cert-search" placeholder="证书名称、文件名..." value="${esc(keyword)}"></div>
        </div>
        <div class="toolbar-right">
          <button type="button" class="btn btn-primary" id="btn-add-cert">+ 新增证书</button>
        </div>
      </div>
      <div id="cert-list">${cardsHtml()}</div>`,
    onMount() {
      listEl = document.getElementById('cert-list');
      document.getElementById('btn-add-cert')?.addEventListener('click', openAddCert);
      let timer = null;
      document.getElementById('cert-search')?.addEventListener('input', e => {
        clearTimeout(timer);
        timer = setTimeout(() => {
          keyword = (e.target.value || '').trim();
          redrawList();
        }, 300);
      });
      bindList();
    }
  });
}

renderCerts();
