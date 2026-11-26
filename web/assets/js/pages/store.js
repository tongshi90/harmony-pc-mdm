/**
 * 应用商店调试页：证书 / Profile / 应用版本（与 MDM「应用管理」无关）
 */
async function renderStore() {
  const U = MDMUtils;
  let activeTab = 'certs';
  let certs = [];
  let apps = [];
  let appTotal = 0;
  let appPage = 1;
  let appKeyword = '';
  let certCount = 0;
  let loadError = '';
  let expandedAppId = '';
  let signStatus = null;
  const versionCache = {};
  const profileCache = {};

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

  async function loadSignStatus() {
    try {
      signStatus = await MDMApi.getStoreSignStatus();
    } catch (e) {
      signStatus = { ready: false, message: e.message || '无法读取签名工具状态' };
    }
  }

  async function loadCerts() {
    try {
      certs = (await MDMApi.listStoreCerts()) || [];
      certCount = certs.length;
      loadError = '';
    } catch (e) {
      certs = [];
      certCount = 0;
      loadError = e.message || '加载证书失败';
    }
  }

  async function loadApps() {
    try {
      const data = await MDMApi.listStoreApps({
        keyword: appKeyword,
        page: appPage,
        page_size: 10
      });
      apps = data.items || [];
      appTotal = data.total || 0;
      appPage = data.page || appPage;
      if (typeof data.cert_count === 'number') certCount = data.cert_count;
      loadError = '';
    } catch (e) {
      apps = [];
      appTotal = 0;
      loadError = e.message || '加载应用失败';
    }
  }

  async function ensureVersions(appId) {
    if (versionCache[appId]) return versionCache[appId];
    const list = (await MDMApi.listStoreVersions(appId)) || [];
    versionCache[appId] = list;
    return list;
  }

  async function ensureProfiles(appId) {
    if (profileCache[appId]) return profileCache[appId];
    const list = (await MDMApi.listStoreProfiles(appId)) || [];
    profileCache[appId] = list;
    return list;
  }

  function signBannerHtml() {
    if (!signStatus) return '';
    const ok = !!signStatus.ready;
    const color = ok ? 'var(--success, #1a7f37)' : 'var(--error)';
    const missing = (signStatus.missing || []).length
      ? `缺少：${(signStatus.missing || []).map(esc).join(', ')}`
      : '';
    return `<div class="panel" style="margin-bottom:12px">
      <div class="panel-body" style="font-size:13px">
        <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center">
          <div>
            <strong style="color:${color}">${ok ? '签名工具就绪' : '签名工具未就绪'}</strong>
            <span class="text-muted" style="margin-left:8px">${esc(signStatus.sign_dir || '')}</span>
            <div class="text-muted" style="margin-top:4px">
              Profile ${signStatus.profile_ready ? '✓' : '✗'} ·
              CSR 签发 ${signStatus.csr_ready ? '✓' : '✗'}
              ${missing ? ` · ${missing}` : ''}
            </div>
            <div class="text-muted" style="margin-top:4px;font-size:12px">
              需 hap-sign-tool.jar、OpenHarmony.p12、OpenHarmonyProfileRelease.pem（公开调试版可放 data/sign/）。
            </div>
          </div>
          <button type="button" class="btn btn-sm" id="btn-refresh-sign">刷新状态</button>
        </div>
      </div>
    </div>`;
  }

  function certsHtml() {
    if (loadError && activeTab === 'certs') {
      return `${signBannerHtml()}<div class="panel"><div class="panel-body text-muted">${esc(loadError)}</div></div>`;
    }
    const tip = `<p class="text-muted" style="margin:0 0 12px;font-size:13px">
      对齐 hm-appstore 应用证书：上传 <strong>.csr</strong> 时用 keytool 签发 .cer（需 OpenHarmony.p12）；
      也可直接上传已有 .cer/.pem。最多 ${3} 张。当前 <strong>${certCount}</strong> / 3。
    </p>`;
    if (!certs.length) {
      return `${signBannerHtml()}${tip}<div class="panel"><div class="panel-body text-muted">暂无证书，请先新增</div></div>`;
    }
    const rows = certs.map(c => `
      <tr>
        <td>${esc(c.cert_name)}</td>
        <td>${esc(c.cert_type_label || '发布证书')}</td>
        <td>${esc(c.file_name || '—')}</td>
        <td>${c.file_size != null ? fmtSize(c.file_size) : '—'}</td>
        <td>${c.has_pem ? '是' : '否'}</td>
        <td>${esc(c.expiration_date || '—')}</td>
        <td>${esc(c.create_time || '—')}</td>
        <td>
          ${c.download_url ? `<button type="button" class="btn btn-sm btn-dl-cert" data-url="${esc(c.download_url)}" data-name="${esc(c.file_name || c.cert_name)}">下载</button>` : ''}
          <button type="button" class="btn btn-sm btn-link btn-text-danger btn-del-cert" data-id="${esc(c.id)}" data-name="${esc(c.cert_name)}">删除</button>
        </td>
      </tr>`).join('');
    return `${signBannerHtml()}${tip}
      <div class="panel"><div class="panel-body" style="padding:0;overflow:auto">
        <table class="data-table">
          <thead><tr>
            <th>名称</th><th>类型</th><th>文件</th><th>大小</th><th>已解析 PEM</th><th>过期</th><th>创建时间</th><th>操作</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div></div>`;
  }

  function versionsBlock(app, versions) {
    if (!versions || !versions.length) {
      return `<div class="text-muted" style="padding:8px 0">暂无版本</div>`;
    }
    return `<table class="data-table" style="margin-top:8px">
      <thead><tr><th>版本名</th><th>版本号</th><th>文件</th><th>大小</th><th>MD5</th><th>时间</th><th>操作</th></tr></thead>
      <tbody>${versions.map(v => `
        <tr>
          <td>${esc(v.version_name)}</td>
          <td>${esc(v.version_code)}</td>
          <td>${esc(v.file_name || '—')}</td>
          <td>${v.file_size != null ? fmtSize(v.file_size) : '—'}</td>
          <td style="font-size:12px;max-width:140px;overflow:hidden;text-overflow:ellipsis" title="${esc(v.file_md5 || '')}">${esc(v.file_md5 || '—')}</td>
          <td>${esc(v.create_time || '—')}</td>
          <td>
            ${v.download_url ? `<button type="button" class="btn btn-sm btn-dl-ver" data-url="${esc(v.download_url)}" data-name="${esc(v.file_name || 'package')}">下载</button>` : ''}
            <button type="button" class="btn btn-sm btn-link btn-text-danger btn-del-ver"
              data-app="${esc(app.id)}" data-vid="${esc(v.id)}">删除</button>
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
  }

  function profilesBlock(app, profiles) {
    if (!profiles || !profiles.length) {
      return `<div class="text-muted" style="padding:8px 0">暂无 Profile</div>`;
    }
    return `<table class="data-table" style="margin-top:8px">
      <thead><tr><th>名称</th><th>证书</th><th>状态</th><th>文件</th><th>过期</th><th>操作</th></tr></thead>
      <tbody>${profiles.map(p => `
        <tr>
          <td>${esc(p.profile_name)}</td>
          <td>${esc(p.cert_name || '—')}</td>
          <td>${esc(p.profile_status_label || '—')}</td>
          <td>${esc(p.file_name || '—')} ${p.file_size != null ? `(${fmtSize(p.file_size)})` : ''}</td>
          <td>${esc(p.expiration_date || '—')}</td>
          <td>
            ${p.download_url ? `<button type="button" class="btn btn-sm btn-dl-ver" data-url="${esc(p.download_url)}" data-name="${esc(p.file_name || 'profile.p7b')}">下载</button>` : ''}
            <button type="button" class="btn btn-sm btn-link btn-text-danger btn-del-profile"
              data-app="${esc(app.id)}" data-pid="${esc(p.id)}">删除</button>
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
  }

  function appsHtml() {
    if (loadError && activeTab === 'apps') {
      return `${signBannerHtml()}<div class="panel"><div class="panel-body text-muted">${esc(loadError)}</div></div>`;
    }
    const tip = `<p class="text-muted" style="margin:0 0 12px;font-size:13px">
      与侧栏「应用管理」独立。可管理应用、版本与 Profile（对齐 Info / InfoVersion / InfoProfile）。
      上传版本前需至少 1 张证书；生成 Profile 需签名工具就绪。
      ${certCount < 1 ? '<span style="color:var(--error)">当前无证书。</span>' : ''}
    </p>`;
    if (!apps.length) {
      return `${signBannerHtml()}${tip}<div class="panel"><div class="panel-body text-muted">暂无应用</div></div>`;
    }
    const cards = apps.map(a => {
      const open = String(expandedAppId) === String(a.id);
      const vers = versionCache[a.id] || [];
      const profiles = profileCache[a.id] || [];
      return `<div class="panel" style="margin-bottom:12px" data-app-card="${esc(a.id)}">
        <div class="panel-body">
          <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap">
            <div>
              <div style="font-weight:600;font-size:15px">${esc(a.app_name)}</div>
              <div class="text-muted" style="font-size:12px;margin-top:4px">${esc(a.package_name)}</div>
              ${a.description ? `<div style="margin-top:6px;font-size:13px">${esc(a.description)}</div>` : ''}
              <div class="text-muted" style="margin-top:6px;font-size:12px">
                版本 ${a.version_count || 0} · Profile ${a.profile_count || 0} · 最新 ${esc(a.latest_version || '—')} · ${esc(a.create_time || '')}
              </div>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <button type="button" class="btn btn-sm btn-toggle-vers" data-id="${esc(a.id)}">${open ? '收起' : '详情'}</button>
              <button type="button" class="btn btn-sm btn-add-profile" data-id="${esc(a.id)}" data-name="${esc(a.app_name)}"
                ${!(signStatus && signStatus.profile_ready) || certCount < 1 ? 'disabled title="需证书 + 签名工具"' : ''}>+ Profile</button>
              <button type="button" class="btn btn-sm btn-primary btn-upload-ver" data-id="${esc(a.id)}" data-name="${esc(a.app_name)}" ${certCount < 1 ? 'disabled title="请先添加证书"' : ''}>上传版本</button>
              <button type="button" class="btn btn-sm btn-link btn-text-danger btn-del-app" data-id="${esc(a.id)}" data-name="${esc(a.app_name)}">删除</button>
            </div>
          </div>
          <div class="store-vers" data-vers-for="${esc(a.id)}" style="${open ? '' : 'display:none'}">
            ${open ? `
              <div style="margin-top:12px;font-weight:600;font-size:13px">版本</div>
              ${versionsBlock(a, vers)}
              <div style="margin-top:16px;font-weight:600;font-size:13px">Profile</div>
              ${profilesBlock(a, profiles)}
            ` : '<div class="text-muted" style="padding:8px 0">加载中…</div>'}
          </div>
        </div>
      </div>`;
    }).join('');
    return `${signBannerHtml()}${tip}${cards}
      <div id="store-app-pagination">${U.pagination(appTotal, appPage, 10, { unit: '个', pageItems: apps.length })}</div>`;
  }

  function panelHtml() {
    if (activeTab === 'certs') return certsHtml();
    return appsHtml();
  }

  function openAddCertModal() {
    U.modal({
      title: '新增证书',
      size: 'md',
      okText: '上传',
      body: `
        <div class="form-item" style="margin-bottom:16px">
          <label class="form-label">证书名称 <span style="color:var(--error)">*</span></label>
          <input id="store-cert-name" class="form-input" maxlength="128" placeholder="如：发布证书-1" autocomplete="off">
        </div>
        <div class="form-item" style="margin-bottom:0">
          <label class="form-label">证书文件 <span style="color:var(--error)">*</span></label>
          <input id="store-cert-file" type="file" accept=".csr,.cer,.pem,.crt">
          <p class="text-muted" style="margin:8px 0 0;font-size:12px">.csr 走 keytool 签发；.cer/.pem 直接解析叶子 PEM 用于 Profile</p>
        </div>
        <p id="store-cert-err" style="display:none;margin:12px 0 0;font-size:12px;color:var(--error)"></p>`,
      onOk: async () => {
        const nameEl = document.getElementById('store-cert-name');
        const fileEl = document.getElementById('store-cert-file');
        const err = document.getElementById('store-cert-err');
        const name = (nameEl && nameEl.value || '').trim();
        const file = fileEl && fileEl.files && fileEl.files[0];
        const showErr = (m) => {
          if (err) { err.textContent = m; err.style.display = 'block'; }
        };
        if (err) { err.style.display = 'none'; err.textContent = ''; }
        if (!name) { showErr('请填写证书名称'); return false; }
        if (!file) { showErr('请选择证书文件'); return false; }
        try {
          await MDMApi.addStoreCert(name, file);
          U.toast('证书已新增');
          await refresh();
          return true;
        } catch (e) {
          showErr(e.message || '上传失败');
          return false;
        }
      }
    });
  }

  function openCreateAppModal() {
    U.modal({
      title: '新建商店应用',
      size: 'md',
      okText: '创建',
      body: `
        <div class="form-item" style="margin-bottom:16px">
          <label class="form-label">应用名称 <span style="color:var(--error)">*</span></label>
          <input id="store-app-name" class="form-input" maxlength="128" placeholder="应用显示名">
        </div>
        <div class="form-item" style="margin-bottom:16px">
          <label class="form-label">包名 <span style="color:var(--error)">*</span></label>
          <input id="store-app-pkg" class="form-input" maxlength="128" placeholder="如 com.example.demo">
        </div>
        <div class="form-item" style="margin-bottom:0">
          <label class="form-label">描述</label>
          <textarea id="store-app-desc" class="form-textarea" rows="3" maxlength="2000" style="font-family:inherit;font-size:13px"></textarea>
        </div>
        <p id="store-app-err" style="display:none;margin:12px 0 0;font-size:12px;color:var(--error)"></p>`,
      onOk: async () => {
        const name = (document.getElementById('store-app-name')?.value || '').trim();
        const pkg = (document.getElementById('store-app-pkg')?.value || '').trim();
        const description = (document.getElementById('store-app-desc')?.value || '').trim();
        const err = document.getElementById('store-app-err');
        const showErr = (m) => { if (err) { err.textContent = m; err.style.display = 'block'; } };
        if (err) { err.style.display = 'none'; }
        if (!name) { showErr('请填写应用名称'); return false; }
        if (!pkg) { showErr('请填写包名'); return false; }
        try {
          await MDMApi.createStoreApp({ app_name: name, package_name: pkg, description });
          U.toast('已创建');
          await refresh();
          return true;
        } catch (e) {
          showErr(e.message || '创建失败');
          return false;
        }
      }
    });
  }

  function openAddProfileModal(appId, appName) {
    const certOpts = certs.filter(c => c.has_pem).map(c =>
      `<option value="${esc(c.id)}">${esc(c.cert_name)}</option>`
    ).join('');
    if (!certOpts) {
      U.toast('没有可用的已解析 PEM 证书，请先新增证书', 'error');
      return;
    }
    U.modal({
      title: `新增 Profile — ${appName || ''}`,
      size: 'md',
      okText: '生成',
      body: `
        <div class="form-item" style="margin-bottom:16px">
          <label class="form-label">Profile 名称 <span style="color:var(--error)">*</span></label>
          <input id="store-profile-name" class="form-input" maxlength="128" placeholder="如 app1-profile" value="app1-profile">
        </div>
        <div class="form-item" style="margin-bottom:0">
          <label class="form-label">关联证书 <span style="color:var(--error)">*</span></label>
          <select id="store-profile-cert" class="form-input">${certOpts}</select>
          <p class="text-muted" style="margin:8px 0 0;font-size:12px">将调用 hap-sign-tool sign-profile 生成 .p7b</p>
        </div>
        <p id="store-profile-err" style="display:none;margin:12px 0 0;font-size:12px;color:var(--error)"></p>`,
      onOk: async () => {
        const profileName = (document.getElementById('store-profile-name')?.value || '').trim();
        const certId = document.getElementById('store-profile-cert')?.value;
        const err = document.getElementById('store-profile-err');
        const showErr = (m) => { if (err) { err.textContent = m; err.style.display = 'block'; } };
        if (err) err.style.display = 'none';
        if (!profileName) { showErr('请填写 Profile 名称'); return false; }
        if (!certId) { showErr('请选择证书'); return false; }
        try {
          await MDMApi.createStoreProfile(appId, {
            profile_name: profileName,
            cert_id: String(certId)
          });
          U.toast('Profile 已生成');
          delete profileCache[appId];
          expandedAppId = String(appId);
          await refresh();
          return true;
        } catch (e) {
          showErr(e.message || '生成失败');
          return false;
        }
      }
    });
  }

  function openUploadVersionModal(appId, appName) {
    U.modal({
      title: `上传版本 — ${appName || ''}`,
      size: 'md',
      okText: '上传',
      body: `
        <div class="form-item" style="margin-bottom:16px">
          <label class="form-label">版本名称 <span style="color:var(--error)">*</span></label>
          <input id="store-ver-name" class="form-input" maxlength="64" placeholder="如 1.0.0" value="1.0.0">
        </div>
        <div class="form-item" style="margin-bottom:16px">
          <label class="form-label">版本号 <span style="color:var(--error)">*</span></label>
          <input id="store-ver-code" class="form-input" maxlength="32" placeholder="如 100" value="100">
        </div>
        <div class="form-item" style="margin-bottom:0">
          <label class="form-label">安装包 <span style="color:var(--error)">*</span></label>
          <input id="store-ver-file" type="file" accept=".app,.hap,.sap">
          <p class="text-muted" style="margin:8px 0 0;font-size:12px">.app / .hap / .sap；此处仅上传存档</p>
        </div>
        <p id="store-ver-err" style="display:none;margin:12px 0 0;font-size:12px;color:var(--error)"></p>`,
      onOk: async () => {
        const versionName = (document.getElementById('store-ver-name')?.value || '').trim();
        const versionCode = (document.getElementById('store-ver-code')?.value || '').trim();
        const file = document.getElementById('store-ver-file')?.files?.[0];
        const err = document.getElementById('store-ver-err');
        const showErr = (m) => { if (err) { err.textContent = m; err.style.display = 'block'; } };
        if (err) { err.style.display = 'none'; }
        if (!versionName) { showErr('请填写版本名称'); return false; }
        if (!versionCode) { showErr('请填写版本号'); return false; }
        if (!file) { showErr('请选择安装包'); return false; }
        try {
          await MDMApi.createStoreVersion(appId, { versionName, versionCode, file });
          U.toast('版本已上传');
          delete versionCache[appId];
          expandedAppId = String(appId);
          await refresh();
          return true;
        } catch (e) {
          showErr(e.message || '上传失败');
          return false;
        }
      }
    });
  }

  async function refresh() {
    await loadSignStatus();
    if (activeTab === 'certs') {
      await loadCerts();
    } else {
      await loadApps();
      await loadCerts();
      if (expandedAppId) {
        try {
          delete versionCache[expandedAppId];
          delete profileCache[expandedAppId];
          await ensureVersions(expandedAppId);
          await ensureProfiles(expandedAppId);
        } catch (e) {
          /* ignore */
        }
      }
    }
    const el = document.getElementById('store-panel');
    if (el) el.innerHTML = panelHtml();
    bindPanel();
    updateToolbar();
  }

  function updateToolbar() {
    const addCert = document.getElementById('btn-add-cert');
    const addApp = document.getElementById('btn-add-app');
    if (addCert) addCert.style.display = activeTab === 'certs' ? '' : 'none';
    if (addApp) addApp.style.display = activeTab === 'apps' ? '' : 'none';
  }

  function bindPanel() {
    document.getElementById('btn-refresh-sign')?.addEventListener('click', async () => {
      await loadSignStatus();
      await refresh();
    });

    document.querySelectorAll('.btn-dl-cert, .btn-dl-ver').forEach(btn => {
      btn.onclick = async () => {
        try {
          await MDMApi.downloadStoreFile(btn.dataset.url, btn.dataset.name || 'download');
        } catch (e) {
          U.toast(e.message || '下载失败', 'error');
        }
      };
    });

    document.querySelectorAll('.btn-del-cert').forEach(btn => {
      btn.onclick = () => {
        U.confirm(`确认删除证书「${btn.dataset.name || ''}」？`, async () => {
          try {
            await MDMApi.deleteStoreCert(btn.dataset.id);
            U.toast('已删除');
            await refresh();
          } catch (e) {
            U.toast(e.message || '删除失败', 'error');
          }
        });
      };
    });

    document.querySelectorAll('.btn-del-app').forEach(btn => {
      btn.onclick = () => {
        U.confirm(`确认删除应用「${btn.dataset.name || ''}」？需先无版本（Profile 会一并删除）。`, async () => {
          try {
            await MDMApi.deleteStoreApp(btn.dataset.id);
            U.toast('已删除');
            if (String(expandedAppId) === String(btn.dataset.id)) expandedAppId = '';
            delete versionCache[btn.dataset.id];
            delete profileCache[btn.dataset.id];
            await refresh();
          } catch (e) {
            U.toast(e.message || '删除失败', 'error');
          }
        });
      };
    });

    document.querySelectorAll('.btn-upload-ver').forEach(btn => {
      btn.onclick = () => openUploadVersionModal(btn.dataset.id, btn.dataset.name);
    });

    document.querySelectorAll('.btn-add-profile').forEach(btn => {
      btn.onclick = async () => {
        if (!certs.length) await loadCerts();
        openAddProfileModal(btn.dataset.id, btn.dataset.name);
      };
    });

    document.querySelectorAll('.btn-toggle-vers').forEach(btn => {
      btn.onclick = async () => {
        const id = String(btn.dataset.id);
        if (String(expandedAppId) === id) {
          expandedAppId = '';
          await refresh();
          return;
        }
        expandedAppId = id;
        try {
          await ensureVersions(id);
          await ensureProfiles(id);
        } catch (e) {
          U.toast(e.message || '加载失败', 'error');
        }
        await refresh();
      };
    });

    document.querySelectorAll('.btn-del-ver').forEach(btn => {
      btn.onclick = () => {
        U.confirm('确认删除该版本及安装包？', async () => {
          try {
            await MDMApi.deleteStoreVersion(btn.dataset.app, btn.dataset.vid);
            U.toast('已删除');
            delete versionCache[btn.dataset.app];
            await refresh();
          } catch (e) {
            U.toast(e.message || '删除失败', 'error');
          }
        });
      };
    });

    document.querySelectorAll('.btn-del-profile').forEach(btn => {
      btn.onclick = () => {
        U.confirm('确认删除该 Profile？', async () => {
          try {
            await MDMApi.deleteStoreProfile(btn.dataset.app, btn.dataset.pid);
            U.toast('已删除');
            delete profileCache[btn.dataset.app];
            await refresh();
          } catch (e) {
            U.toast(e.message || '删除失败', 'error');
          }
        });
      };
    });

    document.querySelectorAll('#store-app-pagination .page-btn').forEach(btn => {
      btn.onclick = () => {
        const p = Number(btn.dataset.page);
        if (!p || p === appPage) return;
        appPage = p;
        refresh();
      };
    });
  }

  await loadSignStatus();
  await loadCerts();

  MDMLayout.mount({
    pageId: 'store',
    title: '应用商店调试',
    content: `
      <div class="toolbar">
        <div class="toolbar-left">
          <span class="text-muted" style="font-size:13px">调试证书 / 应用版本 / Profile · 不影响现有「应用管理」</span>
        </div>
        <div class="toolbar-right">
          <button type="button" class="btn btn-primary" id="btn-add-cert">+ 新增证书</button>
          <button type="button" class="btn btn-primary" id="btn-add-app" style="display:none">+ 新建应用</button>
        </div>
      </div>
      <div class="tabs-wrap" id="store-tabs">
        <div class="tabs">
          <div class="tab-item active" data-tab="certs">证书管理</div>
          <div class="tab-item" data-tab="apps">应用管理</div>
        </div>
        <div id="store-panel" style="margin-top:16px">${certsHtml()}</div>
      </div>`,
    onMount() {
      updateToolbar();
      bindPanel();

      document.getElementById('btn-add-cert')?.addEventListener('click', openAddCertModal);
      document.getElementById('btn-add-app')?.addEventListener('click', openCreateAppModal);

      const tabsWrap = document.getElementById('store-tabs');
      tabsWrap?.querySelectorAll('.tab-item').forEach(tab => {
        tab.addEventListener('click', async () => {
          const t = tab.dataset.tab;
          if (!t || t === activeTab) return;
          activeTab = t;
          tabsWrap.querySelectorAll('.tab-item').forEach(x => {
            x.classList.toggle('active', x.dataset.tab === activeTab);
          });
          await refresh();
        });
      });
    }
  });
}
renderStore();
