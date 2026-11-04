(async function () {
  const U = MDMUtils;

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  let members = [];
  let total = 0;
  let page = 1;
  const pageSize = 20;
  let keyword = '';
  let bindFilter = '';
  let loadError = '';
  let groups = [];
  let groupsLoadError = '';

  async function loadMembers() {
    try {
      const data = await MDMApi.listMembers({
        keyword,
        bind: bindFilter || undefined,
        page,
        page_size: pageSize
      });
      members = (data && data.items) || [];
      total = data.total || 0;
      page = data.page || page;
      loadError = '';
    } catch (e) {
      members = [];
      total = 0;
      loadError = e.message || '加载失败';
    }
  }

  async function loadGroups() {
    try {
      const data = await MDMApi.listMemberGroupOptions({});
      groups = (data && data.items) || [];
      groupsLoadError = '';
    } catch (e) {
      groups = [];
      groupsLoadError = e.message || '分组加载失败';
    }
  }

  function buildGroupTree() {
    const nodes = groups.map(g => ({
      id: String(g.id),
      parentId: g.parent_id ? String(g.parent_id) : null,
      name: g.name,
      path: g.path || g.name,
      depth: Number(g.depth) || 0,
      children: []
    }));
    const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
    const roots = [];
    nodes.forEach(n => {
      if (n.parentId && byId[n.parentId]) byId[n.parentId].children.push(n);
      else roots.push(n);
    });
    const sortRec = list => {
      list.sort((a, b) => a.path.localeCompare(b.path, 'zh-CN'));
      list.forEach(n => sortRec(n.children));
    };
    sortRec(roots);
    return roots;
  }

  function flattenTree(roots) {
    const out = [];
    function walk(list, depth) {
      list.forEach(n => {
        out.push({ ...n, depth });
        walk(n.children, depth + 1);
      });
    }
    walk(roots, 0);
    return out;
  }

  function groupLabel(groupId) {
    if (!groupId) return '请选择分组';
    const g = groups.find(x => String(x.id) === String(groupId));
    return g ? (g.path || g.name) : '请选择分组';
  }

  function renderGroupTree(selectedId) {
    const wrap = document.getElementById('member-group-tree');
    if (!wrap) return;
    const selected = selectedId ? String(selectedId) : '';
    wrap.dataset.value = selected;
    wrap.className = 'member-group-picker';
    const label = groupLabel(selected || null);
    const flat = flattenTree(buildGroupTree());

    let listBody;
    if (groupsLoadError) {
      listBody = `<div class="mgp-empty">${escapeHtml(groupsLoadError)}</div>`;
    } else if (!flat.length) {
      listBody = '<div class="mgp-empty">暂无分组，请先在成员分组中创建</div>';
    } else {
      listBody = flat.map(n => {
        const sel = selected === n.id ? ' is-selected' : '';
        const branch = n.children && n.children.length ? ' is-branch' : '';
        return `<button type="button" class="mgp-node${sel}${branch}" data-id="${escapeHtml(n.id)}"
            style="--d:${n.depth}" role="option" aria-selected="${selected === n.id ? 'true' : 'false'}">
          <span class="mgp-dot" aria-hidden="true"></span>
          <span class="mgp-name">${escapeHtml(n.name)}</span>
          <span class="mgp-check" aria-hidden="true"></span>
        </button>`;
      }).join('');
    }

    wrap.innerHTML = `
      <button type="button" class="form-input mgp-trigger" id="member-group-trigger" aria-haspopup="listbox" aria-expanded="false">
        <span class="mgp-trigger-text${!selected ? ' is-placeholder' : ''}" id="member-group-label">${escapeHtml(label)}</span>
        <span class="mgp-caret" aria-hidden="true"></span>
      </button>
      <div class="mgp-dropdown" id="member-group-panel" role="listbox" hidden>${listBody}</div>`;

    const trigger = wrap.querySelector('#member-group-trigger');
    const panel = wrap.querySelector('#member-group-panel');
    const labelEl = wrap.querySelector('#member-group-label');

    function placePanel() {
      const rect = trigger.getBoundingClientRect();
      const maxH = 220;
      const gap = 4;
      const spaceBelow = window.innerHeight - rect.bottom - 12;
      const spaceAbove = rect.top - 12;
      const openUp = spaceBelow < Math.min(maxH, 140) && spaceAbove > spaceBelow;
      const height = Math.min(maxH, Math.max(120, openUp ? spaceAbove : spaceBelow));
      panel.style.position = 'fixed';
      panel.style.left = `${Math.round(rect.left)}px`;
      panel.style.width = `${Math.round(rect.width)}px`;
      panel.style.maxHeight = `${Math.round(height)}px`;
      panel.style.zIndex = '1200';
      if (openUp) {
        panel.style.top = 'auto';
        panel.style.bottom = `${Math.round(window.innerHeight - rect.top + gap)}px`;
      } else {
        panel.style.bottom = 'auto';
        panel.style.top = `${Math.round(rect.bottom + gap)}px`;
      }
    }

    function setOpen(open) {
      wrap.classList.toggle('is-open', open);
      trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
      panel.hidden = !open;
      if (open) {
        placePanel();
        const selectedBtn = panel.querySelector('.mgp-node.is-selected');
        if (selectedBtn) {
          requestAnimationFrame(() => selectedBtn.scrollIntoView({ block: 'nearest' }));
        }
      } else {
        panel.style.top = '';
        panel.style.bottom = '';
        panel.style.left = '';
        panel.style.width = '';
        panel.style.maxHeight = '';
      }
    }

    function close() {
      setOpen(false);
    }

    trigger.addEventListener('click', e => {
      e.preventDefault();
      e.stopPropagation();
      setOpen(!wrap.classList.contains('is-open'));
    });

    panel.querySelectorAll('.mgp-node').forEach(btn => {
      btn.addEventListener('click', e => {
        e.preventDefault();
        e.stopPropagation();
        const id = btn.dataset.id || '';
        wrap.dataset.value = id;
        labelEl.textContent = groupLabel(id);
        labelEl.classList.toggle('is-placeholder', !id);
        panel.querySelectorAll('.mgp-node').forEach(n => {
          const on = n === btn;
          n.classList.toggle('is-selected', on);
          n.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        close();
      });
    });

    wrap._closeGroupPicker = close;
    wrap._placeGroupPicker = placePanel;
  }

  function getGroupValue() {
    const wrap = document.getElementById('member-group-tree');
    return wrap ? (wrap.dataset.value || '') : '';
  }

  function tableHtml() {
    if (loadError) {
      return `<div class="panel"><div class="panel-body text-muted">${escapeHtml(loadError)}</div></div>`;
    }
    return `
      <div class="panel">
        <div class="panel-header"><h3>成员列表</h3><span class="extra">共 ${U.fmt(total)} 人</span></div>
        <div class="panel-body" style="padding:0">
          <table class="data-table"><thead><tr>
            <th>姓名</th><th>工号</th><th>账号</th><th>分组</th><th>绑定设备</th><th style="width:120px">操作</th>
          </tr></thead><tbody>${members.length ? members.map(m => {
            const bound = !!m.bound;
            const sn = m.device_sn || '';
            return `<tr>
            <td><strong>${escapeHtml(m.name)}</strong></td>
            <td><code>${escapeHtml(m.employee_id)}</code></td>
            <td>${escapeHtml(m.account)}</td>
            <td class="text-muted" style="font-size:12px">${escapeHtml(m.department_path || '—')}</td>
            <td>${bound
              ? `<span class="badge badge-ok">已绑定</span>${sn ? ` <code style="font-size:11px">${escapeHtml(sn)}</code>` : ''}`
              : '<span class="text-muted">未绑定</span>'}</td>
            <td>
              <button class="btn btn-sm btn-link btn-edit" data-id="${escapeHtml(m.id)}">编辑</button>
              <button class="btn btn-sm btn-link btn-delete" data-id="${escapeHtml(m.id)}" data-name="${escapeHtml(m.name)}" style="color:var(--error)">删除</button>
            </td>
          </tr>`;
          }).join('') : '<tr><td colspan="6" class="text-muted" style="text-align:center;padding:24px">暂无成员</td></tr>'}</tbody></table>
          <div id="member-pagination">${U.pagination(total, page, pageSize, { unit: '人', pageItems: members.length })}</div>
        </div>
      </div>`;
  }

  await loadMembers();

  MDMLayout.mount({
    pageId: 'members',
    title: '人员管理',
    content: `
      <div class="toolbar">
        <div class="toolbar-left">
          <div class="search-box"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/></svg>
            <input id="member-search" placeholder="姓名、工号、账号..." value="${escapeHtml(keyword)}"></div>
          <div class="chips" id="member-bind-chips" style="margin-left:8px">
            <button class="chip${bindFilter === '' ? ' is-on' : ''}" type="button" data-bind="">全部</button>
            <button class="chip${bindFilter === 'bound' ? ' is-on' : ''}" type="button" data-bind="bound">已绑定</button>
            <button class="chip${bindFilter === 'unbound' ? ' is-on' : ''}" type="button" data-bind="unbound">未绑定</button>
          </div>
        </div>
        <div class="toolbar-right">
          <button class="btn btn-import">导入成员</button>
          <button class="btn btn-primary btn-add">+ 录入成员</button>
        </div>
      </div>
      <div id="member-list">${tableHtml()}</div>

      <div class="member-form-modal-mask">
        <div class="modal modal-lg">
          <div class="modal-header" id="member-modal-title">录入成员</div>
          <div class="modal-body">
            <div class="form-grid">
              <div class="form-item"><label class="form-label">姓名 <span style="color:var(--error)">*</span></label><input class="form-input" id="member-name" placeholder="如 张明"></div>
              <div class="form-item"><label class="form-label">工号 <span style="color:var(--error)">*</span></label><input class="form-input" id="member-employee-id" placeholder="如 E20190315"></div>
              <div class="form-item" id="member-account-item"><label class="form-label">账号 <span style="color:var(--error)">*</span></label><input class="form-input" id="member-account" placeholder="登录账号"></div>
              <div class="form-item" id="member-password-item"><label class="form-label">密码 <span style="color:var(--error)">*</span></label><input class="form-input" id="member-password" type="password" placeholder="请输入密码"></div>
              <div class="form-item full"><label class="form-label">分组 <span style="color:var(--error)">*</span></label>
                <div class="member-group-picker" id="member-group-tree" data-value=""></div>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn modal-cancel">取消</button>
            <button class="btn btn-primary modal-save">保存</button>
          </div>
        </div>
      </div>

      <div class="member-import-modal-mask modal-mask">
        <div class="modal">
          <div class="modal-header">导入成员</div>
          <div class="modal-body">
            <p class="param-hint" style="margin-bottom:12px">
              仅支持新增导入。表头须为：姓名、工号、账号、密码、分组（分组名须与「成员分组」中名称一致）。
              工号/账号与系统或表内重复、分组不存在等行将失败；成功行直接入库，失败行可下载 Excel 查看原因。
            </p>
            <div style="margin-bottom:12px">
              <button class="btn btn-sm" type="button" id="member-import-template">下载导入模板</button>
            </div>
            ${U.filePickerHtml({
              zoneId: 'member-import-zone',
              inputId: 'member-import-file',
              metaId: 'member-import-info',
              accept: '.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
              title: '点击选择 .xlsx 文件',
              hint: '仅支持新增导入的 Excel 模板',
              metaText: '尚未选择文件',
              compact: true
            })}
            <div id="member-import-result" style="display:none;margin-top:14px;padding:12px;border:1px solid var(--border);border-radius:8px;font-size:13px"></div>
          </div>
          <div class="modal-footer">
            <button class="btn" type="button" id="member-import-cancel">关闭</button>
            <button class="btn btn-primary" type="button" id="member-import-submit">开始导入</button>
          </div>
        </div>
      </div>`,
    onMount() {
      const modal = document.querySelector('.member-form-modal-mask');
      const listEl = document.getElementById('member-list');
      const accountItem = document.getElementById('member-account-item');
      const passwordItem = document.getElementById('member-password-item');
      const accountInput = document.getElementById('member-account');
      const passwordInput = document.getElementById('member-password');
      let saving = false;

      async function refresh() {
        await loadMembers();
        if (listEl) listEl.innerHTML = tableHtml();
        bindList();
      }

      async function openModal(mode, member) {
        const isEdit = mode === 'edit';
        document.getElementById('member-modal-title').textContent = isEdit ? '编辑成员' : '录入成员';
        document.getElementById('member-name').value = member ? member.name : '';
        document.getElementById('member-employee-id').value = member ? member.employee_id : '';
        accountInput.value = member ? member.account : '';
        passwordInput.value = '';
        accountItem.style.display = isEdit ? 'none' : '';
        passwordItem.style.display = isEdit ? 'none' : '';
        accountInput.disabled = isEdit;
        passwordInput.disabled = isEdit;
        await loadGroups();
        renderGroupTree(member ? member.department_id : null);
        modal.dataset.mode = mode;
        modal.dataset.id = member ? member.id : '';
        modal.classList.add('show');
      }

      function closeModal() {
        const wrap = document.getElementById('member-group-tree');
        if (wrap && typeof wrap._closeGroupPicker === 'function') wrap._closeGroupPicker();
        modal.classList.remove('show');
      }

      document.addEventListener('click', e => {
        const wrap = document.getElementById('member-group-tree');
        if (!wrap || !wrap.classList.contains('is-open')) return;
        if (wrap.contains(e.target)) return;
        if (typeof wrap._closeGroupPicker === 'function') wrap._closeGroupPicker();
      });
      document.addEventListener('keydown', e => {
        if (e.key !== 'Escape') return;
        const wrap = document.getElementById('member-group-tree');
        if (wrap && typeof wrap._closeGroupPicker === 'function') wrap._closeGroupPicker();
      });
      window.addEventListener('resize', () => {
        const wrap = document.getElementById('member-group-tree');
        if (wrap && wrap.classList.contains('is-open') && typeof wrap._placeGroupPicker === 'function') {
          wrap._placeGroupPicker();
        }
      });
      // 弹窗内容滚动时同步下拉位置，避免错位
      modal.querySelector('.modal-body')?.addEventListener('scroll', () => {
        const wrap = document.getElementById('member-group-tree');
        if (wrap && wrap.classList.contains('is-open') && typeof wrap._placeGroupPicker === 'function') {
          wrap._placeGroupPicker();
        }
      }, { passive: true });

      const importMask = document.querySelector('.member-import-modal-mask');
      const importResult = document.getElementById('member-import-result');
      let importFile = null;
      let importFailB64 = null;
      let importFailName = 'member-import-failures.xlsx';
      let importing = false;

      const importPicker = U.bindFilePicker({
        zoneId: 'member-import-zone',
        inputId: 'member-import-file',
        metaId: 'member-import-info',
        acceptExt: ['.xlsx'],
        emptyTitle: '点击选择 .xlsx 文件',
        emptyMeta: '尚未选择文件',
        onChange(f) {
          importFile = f;
          importFailB64 = null;
          if (importResult) {
            importResult.style.display = 'none';
            importResult.innerHTML = '';
          }
        }
      });

      function resetImportModal() {
        importFile = null;
        importFailB64 = null;
        importPicker.reset();
        if (importResult) {
          importResult.style.display = 'none';
          importResult.innerHTML = '';
        }
      }

      function downloadBase64Xlsx(b64, filename) {
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const blob = new Blob([bytes], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename || 'member-import-failures.xlsx';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      }

      function openImportModal() {
        resetImportModal();
        importMask?.classList.add('show');
      }

      function closeImportModal() {
        importMask?.classList.remove('show');
      }

      document.querySelector('.btn-import').addEventListener('click', openImportModal);
      document.getElementById('member-import-cancel')?.addEventListener('click', closeImportModal);
      document.getElementById('member-import-template')?.addEventListener('click', async () => {
        try {
          await MDMApi.downloadMemberImportTemplate();
          U.toast('模板已下载');
        } catch (e) {
          U.toast(e.message || '模板下载失败', 'error');
        }
      });
      document.getElementById('member-import-submit')?.addEventListener('click', async () => {
        if (importing) return;
        if (!importFile) {
          U.toast('请先选择要导入的 Excel 文件', 'error');
          return;
        }
        importing = true;
        const btn = document.getElementById('member-import-submit');
        if (btn) btn.disabled = true;
        try {
          const data = await MDMApi.importMembers(importFile);
          const okN = Number(data.success_count) || 0;
          const failN = Number(data.fail_count) || 0;
          importFailB64 = data.fail_file_base64 || null;
          importFailName = data.fail_file_name || 'member-import-failures.xlsx';
          let html = `<div>导入完成：成功 <strong>${okN}</strong> 人，失败 <strong>${failN}</strong> 人。</div>`;
          if (failN > 0 && importFailB64) {
            html += `<div style="margin-top:10px"><button class="btn btn-sm" type="button" id="member-import-fail-dl">下载失败名单</button></div>`;
          }
          if (importResult) {
            importResult.style.display = '';
            importResult.innerHTML = html;
            importResult.querySelector('#member-import-fail-dl')?.addEventListener('click', () => {
              if (importFailB64) downloadBase64Xlsx(importFailB64, importFailName);
            });
          }
          if (okN > 0) await refresh();
          if (failN === 0) {
            U.toast(`成功导入 ${okN} 人`);
          } else if (okN === 0) {
            U.toast(`全部失败（${failN} 人），请下载失败名单查看原因`, 'error');
          } else {
            U.toast(`成功 ${okN} 人，失败 ${failN} 人，可下载失败名单`, 'info');
          }
        } catch (e) {
          U.toast(e.message || '导入失败', 'error');
        } finally {
          importing = false;
          if (btn) btn.disabled = false;
        }
      });
      document.querySelector('.btn-add').addEventListener('click', () => openModal('create'));

      modal.querySelector('.modal-cancel').onclick = closeModal;

      modal.querySelector('.modal-save').addEventListener('click', async () => {
        if (saving) return;
        const isEdit = modal.dataset.mode === 'edit';
        const name = document.getElementById('member-name').value.trim();
        const employeeId = document.getElementById('member-employee-id').value.trim();
        const account = accountInput.value.trim();
        const password = passwordInput.value;
        const departmentId = getGroupValue();

        if (!name || !employeeId || !departmentId) {
          U.toast('请填写姓名、工号并选择分组', 'error');
          return;
        }
        if (!isEdit && !account) {
          U.toast('请填写账号', 'error');
          return;
        }
        if (!isEdit && !password) {
          U.toast('请填写密码', 'error');
          return;
        }

        saving = true;
        try {
          if (isEdit) {
            await MDMApi.updateMember(modal.dataset.id, {
              name,
              employee_id: employeeId,
              department_id: departmentId,
              status: 1
            });
            U.toast('成员已更新');
          } else {
            await MDMApi.createMember({
              name,
              employee_id: employeeId,
              account,
              password,
              department_id: departmentId,
              status: 1
            });
            U.toast('成员已创建');
          }
          closeModal();
          await refresh();
        } catch (e) {
          U.toast(e.message || '保存失败', 'error');
        } finally {
          saving = false;
        }
      });

      document.querySelectorAll('#member-bind-chips .chip').forEach(btn => {
        btn.addEventListener('click', () => {
          const next = btn.dataset.bind || '';
          if (next === bindFilter) return;
          bindFilter = next;
          document.querySelectorAll('#member-bind-chips .chip').forEach(c => {
            c.classList.toggle('is-on', (c.dataset.bind || '') === bindFilter);
          });
          page = 1;
          refresh();
        });
      });

      const searchInput = document.getElementById('member-search');
      let searchTimer = null;
      if (searchInput) {
        searchInput.addEventListener('input', () => {
          clearTimeout(searchTimer);
          searchTimer = setTimeout(() => {
            keyword = searchInput.value.trim();
            page = 1;
            refresh();
          }, 300);
        });
      }

      function bindList() {
        const memberMap = Object.fromEntries(members.map(m => [String(m.id), m]));
        document.querySelectorAll('.btn-edit').forEach(btn => {
          btn.addEventListener('click', () => openModal('edit', memberMap[btn.dataset.id]));
        });
        document.querySelectorAll('.btn-delete').forEach(btn => {
          btn.addEventListener('click', () => {
            U.confirm('确认删除该成员？', async () => {
              try {
                await MDMApi.deleteMember(btn.dataset.id);
                U.toast('已删除');
                await refresh();
              } catch (e) {
                U.toast(e.message || '删除失败', 'error');
              }
            });
          });
        });
        document.querySelectorAll('#member-pagination .page-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            const p = Number(btn.dataset.page);
            if (!p || p === page) return;
            page = p;
            refresh();
          });
        });
      }

      bindList();
    }
  });
})();
