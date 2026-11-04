async function renderUsers() {
  const U = MDMUtils;
  let admins = [];
  let total = 0;
  let roles = [];
  let adminPage = 1;
  let rolePage = 1;
  let cardPageSize = U.cardGridPageSize('cols-4');
  let adminKeyword = '';
  let mqtt = null;
  let mqttError = '';
  /** 本次表单是否已「尝试连接」成功；改表单后失效，未验证不可保存 */
  let mqttProbeOk = false;
  let logConfig = null;
  let logConfigError = '';
  let loadError = '';
  let logs = [];
  let logsTotal = 0;
  let logsPage = 1;
  const logsPageSize = 10;
  let logsKeyword = '';
  let logsSuccess = ''; // '' | '1' | '0'
  let logsViewAll = false;
  let logsError = '';
  let mdmVersions = [];
  let mdmError = '';

  function escapeHtml(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function pageSlice(items, page) {
    const list = items || [];
    const pages = Math.max(1, Math.ceil(list.length / cardPageSize) || 1);
    const cur = Math.min(Math.max(1, page), pages);
    const start = (cur - 1) * cardPageSize;
    return {
      page: cur,
      pages,
      total: list.length,
      items: list.slice(start, start + cardPageSize)
    };
  }

  function pagerHtml(totalCount, page, pageItems, id) {
    return `<div class="panel-foot platform-card-pager">
      <span>第 ${page} 页 · 每页 ${cardPageSize} 个</span>
      <div id="${id}">${U.pagination(totalCount, page, cardPageSize, {
        unit: '个',
        pageItems
      })}</div>
    </div>`;
  }

  async function loadAdmins(kw, page) {
    try {
      adminKeyword = (kw || '').trim();
      const data = await MDMApi.listAdmins({
        keyword: adminKeyword,
        page: page || adminPage,
        page_size: cardPageSize
      });
      // 后端已排除内置超管；前端再兜底一次
      admins = (data.items || []).filter(a => a.username !== 'admin' && Number(a.is_admin) !== 1);
      total = Number(data.total) || 0;
      adminPage = Number(data.page) || page || adminPage;
      loadError = '';
    } catch (e) {
      admins = [];
      total = 0;
      loadError = e.message || '加载失败';
    }
  }

  async function loadRoles(kw) {
    try {
      roles = await MDMApi.listRoles(kw || '') || [];
    } catch (e) {
      roles = [];
      U.toast(e.message || '角色加载失败', 'error');
    }
  }

  async function loadMqtt() {
    try {
      mqtt = await MDMApi.getMqttConfig();
      mqttError = '';
    } catch (e) {
      mqtt = null;
      mqttError = e.message || 'MQTT 配置加载失败';
    }
  }

  async function loadLogConfig() {
    try {
      logConfig = await MDMApi.getLogConfig();
      logConfigError = '';
    } catch (e) {
      logConfig = null;
      logConfigError = e.message || '日志保留配置加载失败';
    }
  }

  async function loadLogs() {
    try {
      const params = {
        keyword: logsKeyword,
        page: logsPage,
        page_size: logsPageSize
      };
      if (logsSuccess === '0' || logsSuccess === '1') params.success = Number(logsSuccess);
      const data = await MDMApi.listOpLogs(params);
      logs = data.items || [];
      logsTotal = data.total || 0;
      logsPage = data.page || logsPage;
      logsViewAll = !!data.view_all;
      logsError = '';
    } catch (e) {
      logs = [];
      logsTotal = 0;
      logsError = e.message || '操作日志加载失败';
    }
  }

  async function loadMdm() {
    try {
      mdmVersions = await MDMApi.listMdmVersions() || [];
      mdmError = '';
    } catch (e) {
      mdmVersions = [];
      mdmError = e.message || 'MDM 版本加载失败';
    }
  }

  function mdmVerStatus(s) {
    const n = Number(s);
    if (n === 2) return U.badgeStatus('published');
    if (n === 3) return '<span class="badge badge-off">已下架</span>';
    return U.badgeStatus('draft');
  }

  function mdmFmtSize(n) {
    if (n == null) return '—';
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / 1024 / 1024).toFixed(2) + ' MB';
  }

  function mdmVersionsHtml() {
    if (!mdmVersions.length) {
      return '<div class="text-muted">暂无版本，请新建</div>';
    }
    return `<div class="card-grid">${mdmVersions.map(v => `
      <div class="entity-card version-card">
        <div class="entity-card-badges">${mdmVerStatus(v.status)}</div>
        <div class="entity-card-head entity-card-head--vcenter">
          <div>
            <div class="entity-title entity-title-ellipsis" title="${escapeHtml(v.version_name)}">${escapeHtml(v.version_name || '—')}</div>
            <div class="entity-sub">版本号 ${escapeHtml(v.version_code || '—')}</div>
          </div>
        </div>
        <div class="entity-card-body">
          <div class="entity-stats">
            <span>安装包大小 <strong>${v.has_package ? mdmFmtSize(v.file_size) : '未上传'}</strong></span>
          </div>
        </div>
        <div class="entity-card-foot">
          <div class="entity-card-actions-main">
            <button class="btn btn-sm btn-primary btn-mdm-edit" type="button"
              data-id="${escapeHtml(v.id)}"
              data-name="${escapeHtml(v.version_name || '')}"
              data-code="${escapeHtml(v.version_code || '')}"
              data-file="${escapeHtml(v.file_name || '')}"
              data-size="${v.file_size != null ? escapeHtml(v.file_size) : ''}"
              data-has-pkg="${v.has_package ? '1' : '0'}">编辑</button>
            ${Number(v.status) === 2
              ? `<button class="btn btn-sm btn-mdm-unpublish" type="button" data-id="${escapeHtml(v.id)}" data-name="${escapeHtml(v.version_name || '')}">下架</button>`
              : `<button class="btn btn-sm btn-mdm-publish" type="button" data-id="${escapeHtml(v.id)}" data-name="${escapeHtml(v.version_name || '')}" ${v.has_package ? '' : 'disabled title="请先上传安装包"'}>发布</button>`}
          </div>
          <div class="entity-card-actions-more">
            ${Number(v.status) === 2
              ? `<button class="btn btn-sm btn-link" type="button" disabled title="请先下架后再删除">删除</button>`
              : `<button class="btn btn-sm btn-link btn-text-danger btn-mdm-del-ver" type="button" data-id="${escapeHtml(v.id)}" data-name="${escapeHtml(v.version_name || '')}">删除</button>`}
          </div>
        </div>
      </div>`).join('')}</div>`;
  }

  function mdmPanelHtml() {
    if (mdmError) {
      return `<div class="panel"><div class="panel-body text-muted">${escapeHtml(mdmError)}</div></div>`;
    }
    const published = mdmVersions.filter(v => Number(v.status) === 2);
    const latestHint = published.length
      ? `<span class="extra">已发布 ${published.length} 个</span>`
      : '<span class="extra">暂无已发布版本</span>';
    return `
      <div class="panel">
        <div class="panel-header">
          <div style="display:flex;align-items:center;gap:10px"><h3>MDM 版本</h3>${latestHint}</div>
          <button type="button" class="btn btn-sm btn-primary" id="btn-add-mdm-version">+ 新建版本</button>
        </div>
        <div class="panel-body" style="padding:16px" id="mdm-version-list">
          ${mdmVersionsHtml()}
        </div>
      </div>`;
  }

  /** @param {object|null} ver 传入则编辑，否则新建 */
  function openMdmVersionModal(ver) {
    const isEdit = !!(ver && ver.id);
    let mask = document.getElementById('mdm-version-mask');
    if (!mask) {
      mask = document.createElement('div');
      mask.id = 'mdm-version-mask';
      mask.className = 'modal-mask';
      mask.innerHTML = `
      <div class="modal" style="width:min(520px,94vw)">
        <div class="modal-header" id="mdm-ver-modal-title">新建 MDM 版本</div>
        <div class="modal-body">
          <div class="form-item"><label class="form-label">版本名称 <span style="color:var(--error)">*</span></label>
            <input class="form-input" id="mdm-ver-name" placeholder="如 1.0.0"></div>
          <div class="form-item" style="margin-top:12px"><label class="form-label">版本号 <span style="color:var(--error)">*</span></label>
            <input class="form-input" id="mdm-ver-code" placeholder="如 100"></div>
          <div class="form-item" style="margin-top:12px"><label class="form-label" id="mdm-ver-pkg-label">安装包（.hap） <span style="color:var(--error)">*</span></label>
            <div id="mdm-ver-hap-host"></div>
          </div>
          <p class="text-muted" id="mdm-ver-err" style="color:var(--error);margin-top:10px;display:none"></p>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn" id="mdm-ver-cancel">取消</button>
          <button type="button" class="btn btn-primary" id="btn-mdm-ver-submit">保存</button>
        </div>
      </div>`;
      document.body.appendChild(mask);
    }

    mask.querySelector('#mdm-ver-modal-title').textContent = isEdit ? '编辑 MDM 版本' : '新建 MDM 版本';
    mask.querySelector('#btn-mdm-ver-submit').textContent = isEdit ? '保存' : '创建';
    mask.querySelector('#mdm-ver-name').value = isEdit ? (ver.name || '') : '';
    mask.querySelector('#mdm-ver-code').value = isEdit ? (ver.code || '') : '';
    mask.dataset.versionId = isEdit ? String(ver.id) : '';
    mask.dataset.hasPkg = isEdit && ver.hasPackage ? '1' : '0';

    const pkgLabel = mask.querySelector('#mdm-ver-pkg-label');
    pkgLabel.innerHTML = isEdit && ver.hasPackage
      ? '安装包（.hap）'
      : '安装包（.hap） <span style="color:var(--error)">*</span>';

    const host = mask.querySelector('#mdm-ver-hap-host');
    host.innerHTML = U.hapPackageFieldHtml({
      fieldId: 'mdm-hap-pkg-field',
      zoneId: 'mdm-pkg-upload',
      inputId: 'mdm-pkg-file',
      pickerWrapId: 'mdm-pkg-picker-wrap',
      previewId: 'mdm-pkg-preview',
      fileName: isEdit ? (ver.fileName || '') : '',
      fileSize: isEdit ? ver.fileSize : null
    });
    const zone = document.getElementById('mdm-pkg-upload');
    if (zone) delete zone.dataset.pickerBound;
    mask._mdmHapField = U.bindHapPackageField({
      zoneId: 'mdm-pkg-upload',
      inputId: 'mdm-pkg-file',
      pickerWrapId: 'mdm-pkg-picker-wrap',
      previewId: 'mdm-pkg-preview',
      fileName: isEdit ? (ver.fileName || '') : '',
      fileSize: isEdit ? ver.fileSize : null
    });

    const err = mask.querySelector('#mdm-ver-err');
    err.style.display = 'none';
    err.textContent = '';
    mask.classList.add('show');

    const close = () => mask.classList.remove('show');
    mask.querySelector('#mdm-ver-cancel').onclick = close;
    mask.onclick = e => { if (e.target === mask) close(); };
    mask.querySelector('#btn-mdm-ver-submit').onclick = async () => {
      const name = mask.querySelector('#mdm-ver-name').value.trim();
      const code = mask.querySelector('#mdm-ver-code').value.trim();
      const hap = mask._mdmHapField;
      const file = hap && hap.getFile ? hap.getFile() : null;
      const hasPkg = hap && hap.hasPackage ? hap.hasPackage() : false;
      if (!name || !code) {
        err.textContent = '请填写版本名称与版本号';
        err.style.display = 'block';
        return;
      }
      if (!isEdit && !file) {
        err.textContent = '请上传 .hap 安装包';
        err.style.display = 'block';
        return;
      }
      if (isEdit && !hasPkg) {
        err.textContent = '请上传 .hap 安装包';
        err.style.display = 'block';
        return;
      }
      const btn = mask.querySelector('#btn-mdm-ver-submit');
      btn.disabled = true;
      try {
        if (isEdit) {
          await MDMApi.updateMdmVersion(mask.dataset.versionId, {
            version_name: name,
            version_code: code
          });
          if (file) {
            await MDMApi.uploadMdmPackage(mask.dataset.versionId, file);
          }
          U.toast('版本已保存');
        } else {
          // 后端要求先建草稿再上传；上传后自动发布为上架
          const created = await MDMApi.createMdmVersion({
            version_name: name,
            version_code: code,
            status: 0
          });
          await MDMApi.uploadMdmPackage(created.id, file);
          await MDMApi.updateMdmVersion(created.id, { status: 2 });
          U.toast('版本已创建并上架');
        }
        close();
        await refreshMdmPanel();
      } catch (e) {
        err.textContent = e.message || (isEdit ? '保存失败' : '创建失败');
        err.style.display = 'block';
      } finally {
        btn.disabled = false;
      }
    };
  }

  async function refreshMdmPanel() {
    await loadMdm();
    const wrap = document.getElementById('mdm-panel-wrap');
    if (wrap) {
      wrap.innerHTML = mdmPanelHtml();
      bindMdmActions();
    }
  }

  function bindMdmActions() {
    const wrap = document.getElementById('mdm-panel-wrap');
    if (!wrap) return;

    document.getElementById('btn-add-mdm-version')?.addEventListener('click', () => openMdmVersionModal(null));

    wrap.querySelectorAll('.btn-mdm-edit').forEach(btn => {
      btn.addEventListener('click', () => {
        openMdmVersionModal({
          id: btn.dataset.id,
          name: btn.dataset.name || '',
          code: btn.dataset.code || '',
          fileName: btn.dataset.file || '',
          fileSize: btn.dataset.size ? Number(btn.dataset.size) : null,
          hasPackage: btn.dataset.hasPkg === '1'
        });
      });
    });

    wrap.querySelectorAll('.btn-mdm-publish').forEach(btn => {
      btn.addEventListener('click', () => {
        U.confirm(`确认发布版本「${btn.dataset.name || ''}」？`, async () => {
          try {
            await MDMApi.updateMdmVersion(btn.dataset.id, { status: 2 });
            U.toast('已发布');
            await refreshMdmPanel();
          } catch (e) {
            U.toast(e.message || '发布失败', 'error');
          }
        });
      });
    });

    wrap.querySelectorAll('.btn-mdm-unpublish').forEach(btn => {
      btn.addEventListener('click', () => {
        U.confirm(`确认下架版本「${btn.dataset.name || ''}」？`, async () => {
          try {
            await MDMApi.updateMdmVersion(btn.dataset.id, { status: 3 });
            U.toast('已下架');
            await refreshMdmPanel();
          } catch (e) {
            U.toast(e.message || '操作失败', 'error');
          }
        });
      });
    });

    wrap.querySelectorAll('.btn-mdm-del-ver').forEach(btn => {
      btn.addEventListener('click', () => {
        U.confirm(`确认删除版本「${btn.dataset.name || ''}」？`, async () => {
          try {
            await MDMApi.deleteMdmVersion(btn.dataset.id);
            U.toast('已删除');
            await refreshMdmPanel();
          } catch (e) {
            U.toast(e.message || '删除失败', 'error');
          }
        });
      });
    });
  }

  function logsTableHtml() {
    if (logsError) {
      return `<div class="panel"><div class="panel-body text-muted">${logsError}</div></div>`;
    }
    if (!logs.length) {
      return `<div class="panel"><div class="panel-body text-muted">暂无操作日志</div></div>`;
    }
    return `<div class="panel"><div class="panel-body" style="padding:0"><table class="data-table"><thead><tr>
      <th>时间</th><th>操作人</th><th>动作</th><th>模块</th><th>结果</th><th>IP</th><th>操作</th>
    </tr></thead><tbody>${logs.map(l => {
      const who = l.user_name || l.username || '—';
      const ok = Number(l.success) === 1;
      return `<tr>
      <td class="text-muted">${l.create_time || '—'}</td>
      <td>${who}${l.username && l.user_name ? `<div class="text-muted" style="font-size:12px">${l.username}</div>` : ''}</td>
      <td>${l.action || '—'}</td>
      <td>${l.module || '—'}</td>
      <td>${U.badgeStatus(ok ? 'success' : 'failed')}</td>
      <td><code>${l.client_ip || '—'}</code></td>
      <td><button class="btn btn-sm btn-link btn-log-detail" data-id="${l.id}">查看详情</button></td>
    </tr>`;
    }).join('')}</tbody></table>
    <div id="logs-pagination">${U.pagination(logsTotal, logsPage, logsPageSize, { unit: '条', pageItems: logs.length })}</div>
    </div></div>`;
  }

  function statusKey(status) {
    return Number(status) === 1 ? 'active' : 'disabled';
  }

  function adminCardsHtml() {
    if (loadError) {
      return `<div class="panel"><div class="panel-body text-muted">${escapeHtml(loadError)}</div></div>`;
    }
    if (!admins.length) {
      return `<div class="panel"><div class="panel-body text-muted">暂无管理员账号</div></div>`;
    }
    const pages = Math.max(1, Math.ceil(total / cardPageSize) || 1);
    if (adminPage > pages) adminPage = pages;
    return `<div class="card-grid cols-4">${admins.map(a => {
      const name = a.name || '—';
      const initial = (String(name).trim()[0] || '?').toUpperCase();
      const contact = a.phone || a.email || '—';
      const enabled = Number(a.status) === 1;
      return `<div class="entity-card platform-card">
        <div class="entity-card-badges">${U.badgeStatus(statusKey(a.status))}</div>
        <div class="entity-card-head entity-card-head--vcenter">
          <div class="entity-icon blue">${escapeHtml(initial)}</div>
          <div>
            <div class="entity-title" title="${escapeHtml(name)}">${escapeHtml(name)}</div>
            <div class="entity-sub"><code>${escapeHtml(a.username || '')}</code></div>
          </div>
        </div>
        <div class="entity-card-body">
          <div class="platform-card-meta">
            <div><span class="k">角色</span><span class="v" title="${escapeHtml(a.role_label || '')}">${escapeHtml(a.role_label || '—')}</span></div>
            <div><span class="k">联系</span><span class="v" title="${escapeHtml(contact)}">${escapeHtml(contact)}</span></div>
          </div>
        </div>
        <div class="entity-card-foot">
          <div class="entity-card-actions-main">
            <a class="btn btn-sm btn-primary" href="${U.href('userForm', { id: a.id })}">编辑</a>
            <button type="button" class="btn btn-sm btn-reset-pwd" data-id="${escapeHtml(a.id)}" data-name="${escapeHtml(name)}" data-username="${escapeHtml(a.username || '')}">重置密码</button>
          </div>
          <div class="entity-card-actions-more">
            <button type="button" class="btn-link btn-toggle-admin" data-id="${escapeHtml(a.id)}" data-status="${a.status}">${enabled ? '禁用' : '启用'}</button>
            <button type="button" class="btn-link btn-text-danger btn-del-admin" data-id="${escapeHtml(a.id)}" data-name="${escapeHtml(name)}">删除</button>
          </div>
        </div>
      </div>`;
    }).join('')}</div>
    ${pagerHtml(total, adminPage, admins.length, 'admin-pagination')}`;
  }

  function openResetPwdModal(admin) {
    let mask = document.getElementById('admin-reset-pwd-mask');
    if (!mask) {
      mask = document.createElement('div');
      mask.id = 'admin-reset-pwd-mask';
      mask.className = 'modal-mask';
      mask.innerHTML = `<div class="modal" style="width:min(480px,94vw)">
        <div class="modal-header">重置管理员密码</div>
        <div class="modal-body">
          <p class="text-muted" id="arp-target" style="margin-bottom:12px;font-size:12px"></p>
          <div class="form-item">
            <label class="form-label">新密码 <span style="color:var(--error)">*</span></label>
            ${U.passwordInputHtml({ id: 'arp-password', placeholder: U.PLATFORM_PASSWORD_HINT, autocomplete: 'new-password' })}
          </div>
          <div class="form-item" style="margin-top:10px">
            <label class="form-label">确认新密码 <span style="color:var(--error)">*</span></label>
            ${U.passwordInputHtml({ id: 'arp-confirm', placeholder: '再次输入新密码', autocomplete: 'new-password' })}
          </div>
          <p class="text-muted" id="arp-error" style="color:var(--error);margin-top:10px;display:none"></p>
        </div>
        <div class="modal-footer">
          <button class="btn" type="button" id="arp-cancel">取消</button>
          <button class="btn btn-primary" type="button" id="arp-ok">确认重置</button>
        </div>
      </div>`;
      document.body.appendChild(mask);
      U.bindPasswordToggles(mask);
    }

    mask.querySelector('#arp-target').textContent =
      `将把「${admin.name || ''}」（${admin.username || ''}）的密码重置为下方指定密码，并使其现有登录失效。`;
    mask.querySelector('#arp-password').value = '';
    mask.querySelector('#arp-confirm').value = '';
    mask.querySelectorAll('.password-field input').forEach(input => { input.type = 'password'; });
    mask.querySelectorAll('[data-pwd-toggle]').forEach(btn => {
      btn.innerHTML = U._eyeOpen;
    });
    const err = mask.querySelector('#arp-error');
    err.style.display = 'none';
    err.textContent = '';
    mask.classList.add('show');

    const close = () => mask.classList.remove('show');
    mask.querySelector('#arp-cancel').onclick = close;
    mask.querySelector('#arp-ok').onclick = async () => {
      const password = mask.querySelector('#arp-password').value;
      const confirm = mask.querySelector('#arp-confirm').value;
      if (!password) {
        err.textContent = '请输入新密码';
        err.style.display = 'block';
        return;
      }
      const pwdErr = U.validatePlatformPassword(password);
      if (pwdErr) {
        err.textContent = pwdErr;
        err.style.display = 'block';
        return;
      }
      if (password !== confirm) {
        err.textContent = '两次输入的密码不一致';
        err.style.display = 'block';
        return;
      }
      const btn = mask.querySelector('#arp-ok');
      btn.disabled = true;
      err.style.display = 'none';
      try {
        await MDMApi.resetAdminPassword(admin.id, password);
        U.toast('密码已重置');
        close();
      } catch (e) {
        err.textContent = e.message || '重置失败';
        err.style.display = 'block';
        U.toast(e.message || '重置失败', 'error');
      } finally {
        btn.disabled = false;
      }
    };
  }

  function rolesHtml() {
    if (!roles.length) {
      return `<div class="panel"><div class="panel-body text-muted">暂无角色</div></div>`;
    }
    const slice = pageSlice(roles, rolePage);
    rolePage = slice.page;
    return `<div class="card-grid cols-4">${slice.items.map(r => {
      const enabled = Number(r.status) === 1;
      const isSystem = Number(r.is_system) === 1;
      const desc = (r.description || '').trim();
      const menus = (r.menu_codes || []).length;
      return `<div class="entity-card platform-card">
        <div class="entity-card-badges">${isSystem ? '<span class="tag tag-orange">系统</span>' : ''}${U.badgeStatus(statusKey(r.status))}</div>
        <div class="entity-card-head entity-card-head--vcenter">
          <div class="entity-icon ${enabled ? 'green' : 'gray'}">R</div>
          <div>
            <div class="entity-title" title="${escapeHtml(r.role_name || '')}">${escapeHtml(r.role_name || '—')}</div>
            <div class="entity-sub"><code>${escapeHtml(r.role_code || '')}</code></div>
          </div>
        </div>
        <div class="entity-card-body">
          <p class="platform-card-desc${desc ? '' : ' is-empty'}">${escapeHtml(desc || '暂无说明')}</p>
          <div class="platform-card-tags">
            <span class="tag tag-blue">${Number(r.user_count) || 0} 账号</span>
            <span class="tag tag-gray">${menus} 菜单</span>
          </div>
        </div>
        <div class="entity-card-foot">
          <div class="entity-card-actions-main">
            <a class="btn btn-sm btn-primary" href="${U.href('rolePermission', { id: r.id })}">${isSystem ? '查看权限' : '配置权限'}</a>
            ${isSystem ? '' : `<button type="button" class="btn btn-sm btn-edit-role" data-id="${escapeHtml(r.id)}">编辑</button>`}
          </div>
          ${isSystem ? '' : `<div class="entity-card-actions-more">
            <button type="button" class="btn-link btn-toggle-role" data-id="${escapeHtml(r.id)}" data-status="${r.status}" data-code="${escapeHtml(r.role_code || '')}">${enabled ? '禁用' : '启用'}</button>
            <button type="button" class="btn-link btn-text-danger btn-del-role" data-id="${escapeHtml(r.id)}" data-name="${escapeHtml(r.role_name || '')}">删除</button>
          </div>`}
        </div>
      </div>`;
    }).join('')}</div>
    ${pagerHtml(slice.total, slice.page, slice.items.length, 'role-pagination')}`;
  }

  function mqttStatusLabel(m) {
    if (!m) return '';
    if (m.connected) return '<span class="tag tag-green">运行中已连接</span>';
    if (m.connect_enabled) {
      const tip = m.last_error ? ` title="${String(m.last_error).replace(/"/g, '&quot;')}"` : '';
      return `<span class="tag tag-orange"${tip}>运行中未连接（自动重试）</span>`;
    }
    return '<span class="tag tag-gray">未启用</span>';
  }

  function mqttFormHtml() {
    if (mqttError) {
      return `<div class="panel"><div class="panel-body text-muted">${mqttError}</div></div>`;
    }
    const m = mqtt || {};
    return `
      <div class="panel">
        <div class="panel-header"><h3>MQTT 通道配置</h3>
          <span class="extra">${mqttStatusLabel(m)}</span>
        </div>
        <div class="panel-body settings-form-body">
          <div class="form-grid">
            <div class="form-item"><label class="form-label">Broker 地址 <span style="color:var(--error)">*</span></label>
              <input class="form-input mqtt-field" id="mqtt-host" value="${m.host || ''}" placeholder="如 mqtt.example.com"></div>
            <div class="form-item"><label class="form-label">端口 <span style="color:var(--error)">*</span></label>
              <input class="form-input mqtt-field" id="mqtt-port" type="number" value="${m.port != null ? m.port : 1883}"></div>
            <div class="form-item"><label class="form-label">用户名</label>
              <input class="form-input mqtt-field" id="mqtt-username" value="${m.username || ''}" autocomplete="off"></div>
            <div class="form-item"><label class="form-label">密码</label>
              ${U.passwordInputHtml({ id: 'mqtt-password', placeholder: m.has_password ? '已设置，留空则不修改' : '可选', autocomplete: 'new-password' })}
            </div>
          </div>
          <div class="settings-form-actions" style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
            <button class="btn" type="button" id="btn-test-mqtt">尝试连接</button>
            <span id="btn-save-mqtt-wrap"${mqttProbeOk ? '' : ' title="请先点击「尝试连接」，成功后再保存。"'} style="display:inline-flex">
              <button class="btn btn-primary" type="button" id="btn-save-mqtt"${mqttProbeOk ? '' : ' disabled'}>保存配置</button>
            </span>
          </div>
        </div>
      </div>`;
  }

  function logConfigFormHtml() {
    if (logConfigError) {
      return `<div class="panel" style="margin-top:16px"><div class="panel-body text-muted">${logConfigError}</div></div>`;
    }
    const c = logConfig || {};
    const days = c.retention_days != null ? c.retention_days : 90;
    return `
      <div class="panel" style="margin-top:16px">
        <div class="panel-header"><h3>操作日志保留</h3></div>
        <div class="panel-body settings-form-body">
          <div class="form-grid">
            <div class="form-item">
              <label class="form-label">保留天数 <span style="color:var(--error)">*</span></label>
              <input class="form-input" id="log-retention-days" type="number" min="1" max="3650" value="${days}" placeholder="默认 90">
            </div>
          </div>
          <div class="settings-form-actions" style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
            <button class="btn btn-primary" type="button" id="btn-save-log-config">保存配置</button>
          </div>
        </div>
      </div>`;
  }

  function openRoleModal(role) {
    let mask = document.getElementById('role-form-mask');
    if (!mask) {
      mask = document.createElement('div');
      mask.id = 'role-form-mask';
      mask.className = 'modal-mask';
      mask.innerHTML = `<div class="modal" style="width:min(520px,94vw)">
        <div class="modal-header" id="role-form-title">角色</div>
        <div class="modal-body">
          <div class="form-item"><label class="form-label">角色名称 *</label><input class="form-input" id="rf-name"></div>
          <div class="form-item" style="margin-top:10px"><label class="form-label">角色编码 *</label><input class="form-input" id="rf-code" placeholder="如 operator"></div>
          <div class="form-item" style="margin-top:10px"><label class="form-label">描述</label><input class="form-input" id="rf-desc"></div>
          <p class="text-muted" id="rf-error" style="color:var(--error);margin-top:10px;display:none"></p>
        </div>
        <div class="modal-footer">
          <button class="btn" id="rf-cancel">取消</button>
          <button class="btn btn-primary" id="rf-ok">保存</button>
        </div>
      </div>`;
      document.body.appendChild(mask);
    }
    const editing = !!role;
    mask.querySelector('#role-form-title').textContent = editing ? '编辑角色' : '添加角色';
    mask.querySelector('#rf-name').value = role ? role.role_name : '';
    const codeInput = mask.querySelector('#rf-code');
    codeInput.value = role ? role.role_code : '';
    codeInput.readOnly = editing;
    mask.querySelector('#rf-desc').value = role ? (role.description || '') : '';
    const err = mask.querySelector('#rf-error');
    err.style.display = 'none';
    mask.classList.add('show');
    const close = () => mask.classList.remove('show');
    mask.querySelector('#rf-cancel').onclick = close;
    mask.querySelector('#rf-ok').onclick = async () => {
      const role_name = mask.querySelector('#rf-name').value.trim();
      const role_code = mask.querySelector('#rf-code').value.trim();
      const description = mask.querySelector('#rf-desc').value.trim();
      if (!role_name || !role_code) {
        err.textContent = '请填写名称与编码';
        err.style.display = 'block';
        return;
      }
      try {
        if (editing) {
          await MDMApi.updateRole(role.id, { role_name, description });
        } else {
          await MDMApi.createRole({
            role_name, role_code, description, status: 1, menu_codes: ['dashboard']
          });
        }
        close();
        U.toast('角色已保存');
        await refreshRoles();
      } catch (e) {
        err.textContent = e.message || '保存失败';
        err.style.display = 'block';
      }
    };
  }

  await Promise.all([loadAdmins(), loadRoles(), loadMqtt(), loadLogConfig(), loadLogs(), loadMdm()]);

  function bindRoleActions() {
    document.querySelectorAll('.btn-edit-role').forEach(btn => {
      btn.addEventListener('click', () => {
        const role = roles.find(r => String(r.id) === String(btn.dataset.id));
        if (role) openRoleModal(role);
      });
    });
    document.querySelectorAll('.btn-toggle-role').forEach(btn => {
      btn.addEventListener('click', () => {
        const next = Number(btn.dataset.status) === 1 ? 0 : 1;
        const action = next === 1 ? '启用' : '禁用';
        U.confirm(`确认${action}该角色？`, async () => {
          try {
            await MDMApi.setRoleStatus(btn.dataset.id, next);
            U.toast(`已${action}`);
            await refreshRoles();
          } catch (e) {
            U.toast(e.message || '操作失败', 'error');
          }
        });
      });
    });
    document.querySelectorAll('.btn-del-role').forEach(btn => {
      btn.addEventListener('click', () => {
        U.confirm('确认删除该角色？', async () => {
          try {
            await MDMApi.deleteRole(btn.dataset.id);
            U.toast('已删除');
            await refreshRoles();
          } catch (e) {
            U.toast(e.message || '删除失败', 'error');
          }
        });
      });
    });
    document.querySelectorAll('#role-pagination .page-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const p = Number(btn.dataset.page);
        if (!p || p === rolePage) return;
        rolePage = p;
        const el = document.getElementById('role-list');
        if (el) el.innerHTML = rolesHtml();
        bindRoleActions();
      });
    });
  }

  async function refreshRoles() {
    const kw = (document.getElementById('role-search')?.value || '').trim();
    await loadRoles(kw);
    const el = document.getElementById('role-list');
    if (el) el.innerHTML = rolesHtml();
    bindRoleActions();
  }

  MDMLayout.mount({
    pageId: 'users',
    title: '平台基础管理',
    content: `
      <div id="tabs-wrap">
        <div class="tabs">
          <div class="tab-item active" data-tab="admins">管理员账号</div>
          <div class="tab-item" data-tab="roles">角色权限</div>
          <div class="tab-item" data-tab="mdm">MDM 版本</div>
          <div class="tab-item" data-tab="config">系统配置</div>
          <div class="tab-item" data-tab="logs">操作日志</div>
        </div>
        <div class="tab-panel active" data-panel="admins">
          <div class="toolbar">
            <div class="toolbar-left">
              <div class="search-box">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/></svg>
                <input id="admin-search" placeholder="搜索账号、姓名...">
              </div>
            </div>
            <div class="toolbar-right"><a class="btn btn-primary" href="${U.href('userForm')}">+ 新建管理员</a></div>
          </div>
          <div id="admin-list">${adminCardsHtml()}</div>
        </div>
        <div class="tab-panel" data-panel="mdm">
          <div id="mdm-panel-wrap">${mdmPanelHtml()}</div>
        </div>
        <div class="tab-panel" data-panel="config">
          <div id="mqtt-config-wrap">${mqttFormHtml()}</div>
          <div id="log-config-wrap">${logConfigFormHtml()}</div>
        </div>
        <div class="tab-panel" data-panel="roles">
          <div class="toolbar">
            <div class="toolbar-left"><div class="search-box"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/></svg><input id="role-search" placeholder="角色名称、Code..."></div></div>
            <div class="toolbar-right"><button class="btn btn-primary btn-add-role">+ 添加角色</button></div>
          </div>
          <div id="role-list">${rolesHtml()}</div>
        </div>
        <div class="tab-panel" data-panel="logs">
          <div class="toolbar">
            <div class="toolbar-left" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
              <div class="search-box">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/></svg>
                <input id="log-search" placeholder="操作人、动作、接口、IP..." value="${logsKeyword}">
              </div>
              <select class="form-select" id="log-success" style="width:120px">
                <option value=""${logsSuccess === '' ? ' selected' : ''}>全部结果</option>
                <option value="1"${logsSuccess === '1' ? ' selected' : ''}>成功</option>
                <option value="0"${logsSuccess === '0' ? ' selected' : ''}>失败</option>
              </select>
              <span class="text-muted" style="font-size:12px">${logsViewAll ? '可见：全部账号' : '可见：仅本人'}</span>
            </div>
            <div class="toolbar-right"><button class="btn" type="button" id="btn-export-logs">导出全部</button></div>
          </div>
          <div id="logs-list">${logsTableHtml()}</div>
        </div>
      </div>`,
    onMount() {
      const tabsWrap = document.getElementById('tabs-wrap');
      U.initTabs(tabsWrap);
      const activeTab = U.query('tab');
      if (activeTab) {
        const tabEl = tabsWrap.querySelector(`.tab-item[data-tab="${activeTab}"]`);
        if (tabEl) tabEl.click();
      }
      bindMdmActions();

      function bindMqttForm() {
        const wrap = document.getElementById('mqtt-config-wrap');
        if (!wrap) return;
        U.bindPasswordToggles(wrap);

        const saveBtn = document.getElementById('btn-save-mqtt');
        const saveWrap = document.getElementById('btn-save-mqtt-wrap');
        const SAVE_HINT = '请先点击「尝试连接」，成功后再保存。';
        const pwdInput = document.getElementById('mqtt-password');
        if (pwdInput) pwdInput.classList.add('mqtt-field');

        function syncSaveHint() {
          if (!saveBtn || !saveWrap) return;
          saveBtn.disabled = !mqttProbeOk;
          if (mqttProbeOk) saveWrap.removeAttribute('title');
          else saveWrap.setAttribute('title', SAVE_HINT);
        }

        function invalidateProbe() {
          if (!mqttProbeOk) return;
          mqttProbeOk = false;
          syncSaveHint();
        }

        wrap.querySelectorAll('.mqtt-field').forEach(el => {
          el.addEventListener('input', invalidateProbe);
          el.addEventListener('change', invalidateProbe);
        });

        function readMqttPayload() {
          const host = document.getElementById('mqtt-host').value.trim();
          const port = Number(document.getElementById('mqtt-port').value);
          if (!host) {
            U.toast('请填写 Broker 地址', 'error');
            return null;
          }
          if (!port || port < 1 || port > 65535) {
            U.toast('端口不合法', 'error');
            return null;
          }
          return {
            host,
            port,
            username: document.getElementById('mqtt-username').value.trim(),
            password: document.getElementById('mqtt-password').value
          };
        }

        document.getElementById('btn-test-mqtt')?.addEventListener('click', async () => {
          const payload = readMqttPayload();
          if (!payload) return;
          const btn = document.getElementById('btn-test-mqtt');
          if (btn) btn.disabled = true;
          try {
            const res = await MDMApi.testMqttConfig(payload);
            mqttProbeOk = true;
            syncSaveHint();
            U.toast((res && res.message) || '连接成功');
          } catch (e) {
            mqttProbeOk = false;
            syncSaveHint();
            U.toast(e.message || '连接失败', 'error');
          } finally {
            if (btn) btn.disabled = false;
          }
        });

        saveBtn?.addEventListener('click', async () => {
          if (!mqttProbeOk) {
            U.toast('请先尝试连接成功后再保存', 'error');
            return;
          }
          const payload = readMqttPayload();
          if (!payload) return;
          try {
            mqtt = await MDMApi.saveMqttConfig(payload);
            mqttProbeOk = false;
            U.toast('MQTT 配置已保存，并已切换连接');
            wrap.innerHTML = mqttFormHtml();
            bindMqttForm();
          } catch (e) {
            mqttProbeOk = false;
            syncSaveHint();
            U.toast(e.message || '保存失败', 'error');
          }
        });
      }
      bindMqttForm();

      function bindLogConfigForm() {
        const wrap = document.getElementById('log-config-wrap');
        if (!wrap) return;
        document.getElementById('btn-save-log-config')?.addEventListener('click', async () => {
          const days = Number(document.getElementById('log-retention-days')?.value);
          if (!Number.isInteger(days) || days < 1 || days > 3650) {
            U.toast('保留天数须为 1～3650 的整数', 'error');
            return;
          }
          try {
            logConfig = await MDMApi.saveLogConfig({ retention_days: days });
            U.toast('日志保留配置已保存');
            wrap.innerHTML = logConfigFormHtml();
            bindLogConfigForm();
          } catch (e) {
            U.toast(e.message || '保存失败', 'error');
          }
        });
      }
      bindLogConfigForm();

      const listEl = document.getElementById('admin-list');
      const searchInput = document.getElementById('admin-search');
      let timer = null;

      async function refreshAdmins(opts = {}) {
        if (opts.resetPage) adminPage = 1;
        await loadAdmins(searchInput?.value || '', adminPage);
        if (listEl) listEl.innerHTML = adminCardsHtml();
        bindAdminActions();
      }

      function bindAdminActions() {
        document.querySelectorAll('.btn-reset-pwd').forEach(btn => {
          btn.addEventListener('click', () => {
            openResetPwdModal({
              id: btn.dataset.id,
              name: btn.dataset.name,
              username: btn.dataset.username
            });
          });
        });
        document.querySelectorAll('.btn-toggle-admin').forEach(btn => {
          btn.addEventListener('click', () => {
            const id = btn.dataset.id;
            const cur = Number(btn.dataset.status);
            const next = cur === 1 ? 0 : 1;
            const action = next === 1 ? '启用' : '禁用';
            U.confirm(`确认${action}该管理员？`, async () => {
              try {
                await MDMApi.setAdminStatus(id, next);
                U.toast(`已${action}`);
                refreshAdmins();
              } catch (e) {
                U.toast(e.message || '操作失败', 'error');
              }
            });
          });
        });
        document.querySelectorAll('.btn-del-admin').forEach(btn => {
          btn.addEventListener('click', () => {
            U.confirm('确认删除该管理员？', async () => {
              try {
                await MDMApi.deleteAdmin(btn.dataset.id);
                U.toast('已删除');
                refreshAdmins();
              } catch (e) {
                U.toast(e.message || '删除失败', 'error');
              }
            });
          });
        });
        document.querySelectorAll('#admin-pagination .page-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            const p = Number(btn.dataset.page);
            if (!p || p === adminPage) return;
            adminPage = p;
            refreshAdmins();
          });
        });
      }

      bindAdminActions();
      bindRoleActions();
      searchInput?.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => refreshAdmins({ resetPage: true }), 300);
      });

      U.bindCardGridPageResize('cols-4', () => cardPageSize, (next, prev) => {
        const adminFirst = (adminPage - 1) * prev;
        const roleFirst = (rolePage - 1) * prev;
        cardPageSize = next;
        adminPage = Math.floor(adminFirst / cardPageSize) + 1;
        rolePage = Math.floor(roleFirst / cardPageSize) + 1;
        refreshAdmins();
        refreshRoles();
      });

      document.querySelector('.btn-add-role')?.addEventListener('click', () => openRoleModal(null));

      let roleTimer = null;
      document.getElementById('role-search')?.addEventListener('input', e => {
        clearTimeout(roleTimer);
        roleTimer = setTimeout(async () => {
          try {
            rolePage = 1;
            await loadRoles(e.target.value.trim());
            const el = document.getElementById('role-list');
            if (el) el.innerHTML = rolesHtml();
            bindRoleActions();
          } catch (err) {
            U.toast(err.message || '搜索失败', 'error');
          }
        }, 300);
      });

      const logsListEl = document.getElementById('logs-list');

      async function refreshLogs() {
        await loadLogs();
        if (logsListEl) logsListEl.innerHTML = logsTableHtml();
        bindLogActions();
        const hint = document.querySelector('#log-success')?.parentElement?.querySelector('.text-muted');
        // 更新可见范围提示：重新渲染工具栏文案较麻烦，列表区已够用
        void hint;
      }

      function bindLogActions() {
        document.querySelectorAll('.btn-log-detail').forEach(btn => {
          btn.addEventListener('click', async () => {
            try {
              const detail = await MDMApi.getOpLog(btn.dataset.id);
              U.showAuditLogDetail(detail);
            } catch (e) {
              U.toast(e.message || '加载详情失败', 'error');
            }
          });
        });
        document.querySelectorAll('#logs-pagination .page-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            const p = Number(btn.dataset.page);
            if (!p || p === logsPage) return;
            logsPage = p;
            refreshLogs();
          });
        });
      }
      bindLogActions();

      let logTimer = null;
      document.getElementById('log-search')?.addEventListener('input', e => {
        clearTimeout(logTimer);
        logTimer = setTimeout(() => {
          logsKeyword = e.target.value.trim();
          logsPage = 1;
          refreshLogs();
        }, 300);
      });
      document.getElementById('log-success')?.addEventListener('change', e => {
        logsSuccess = e.target.value;
        logsPage = 1;
        refreshLogs();
      });
      document.getElementById('btn-export-logs')?.addEventListener('click', async () => {
        try {
          const params = { keyword: logsKeyword };
          if (logsSuccess === '0' || logsSuccess === '1') params.success = Number(logsSuccess);
          await MDMApi.exportOpLogs(params);
          U.toast('导出已开始');
        } catch (e) {
          U.toast(e.message || '导出失败', 'error');
        }
      });
    }
  });
}
renderUsers();
