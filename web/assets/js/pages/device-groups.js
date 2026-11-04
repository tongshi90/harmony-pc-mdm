(async function () {
  const U = MDMUtils;

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  let allGroups = [];
  let policies = [];
  let loadError = '';
  let keyword = '';
  /** 已展开的分组 id（有子级时才有意义）；默认只显示顶级 */
  const expandedIds = new Set();

  async function loadData() {
    try {
      const [gData, pData] = await Promise.all([
        MDMApi.listMemberGroups({}),
        MDMApi.listInitialPolicies({ page: 1, page_size: 100 })
      ]);
      allGroups = (gData && gData.items) || [];
      // 接口已按 is_default desc；默认模板排在最前
      policies = (pData && pData.items) || [];
      loadError = '';
      const alive = new Set(allGroups.map(g => String(g.id)));
      Array.from(expandedIds).forEach(id => {
        if (!alive.has(id)) expandedIds.delete(id);
      });
    } catch (e) {
      allGroups = [];
      policies = [];
      loadError = e.message || '加载失败';
    }
  }

  function groupById() {
    return Object.fromEntries(allGroups.map(g => [String(g.id), g]));
  }

  /** 构建列表树；搜索时保留命中节点及其祖先 */
  function buildListTree() {
    const kw = (keyword || '').trim().toLowerCase();
    const byId = groupById();
    let keep = null;
    if (kw) {
      keep = new Set();
      allGroups.forEach(g => {
        const name = String(g.name || '').toLowerCase();
        const path = String(g.path || '').toLowerCase();
        if (!name.includes(kw) && !path.includes(kw)) return;
        keep.add(String(g.id));
        let pid = g.parent_id ? String(g.parent_id) : null;
        while (pid && byId[pid]) {
          keep.add(pid);
          const p = byId[pid];
          pid = p.parent_id ? String(p.parent_id) : null;
        }
      });
      keep.forEach(id => {
        const g = byId[id];
        if (!g) return;
        let pid = g.parent_id ? String(g.parent_id) : null;
        while (pid && byId[pid]) {
          expandedIds.add(pid);
          const p = byId[pid];
          pid = p.parent_id ? String(p.parent_id) : null;
        }
      });
    }

    const nodes = allGroups
      .filter(g => !keep || keep.has(String(g.id)))
      .map(g => ({
        id: String(g.id),
        parentId: g.parent_id ? String(g.parent_id) : null,
        path: g.path || g.name,
        data: g,
        children: []
      }));
    const map = Object.fromEntries(nodes.map(n => [n.id, n]));
    const roots = [];
    nodes.forEach(n => {
      if (n.parentId && map[n.parentId]) map[n.parentId].children.push(n);
      else roots.push(n);
    });
    const sortRec = list => {
      list.sort((a, b) => String(a.path).localeCompare(String(b.path), 'zh-CN'));
      list.forEach(n => sortRec(n.children));
    };
    sortRec(roots);
    return roots;
  }

  /** 按展开状态拍平为可见行 */
  function visibleRows() {
    const roots = buildListTree();
    const out = [];
    function walk(list, depth) {
      list.forEach(n => {
        const hasChildren = n.children.length > 0;
        const expanded = hasChildren && expandedIds.has(n.id);
        out.push({
          ...n.data,
          depth,
          hasChildren,
          expanded
        });
        if (expanded) walk(n.children, depth + 1);
      });
    }
    walk(roots, 0);
    return out;
  }

  function visibleGroupCount() {
    const kw = (keyword || '').trim().toLowerCase();
    if (!kw) return allGroups.length;
    return allGroups.filter(g => {
      const name = String(g.name || '').toLowerCase();
      const path = String(g.path || '').toLowerCase();
      return name.includes(kw) || path.includes(kw);
    }).length;
  }

  function policyOptionsHtml(selectedId) {
    const empty = `<option value="">无初始策略</option>`;
    const opts = policies.map(p => {
      const label = p.is_default ? `${p.name}（默认）` : p.name;
      const sel = String(selectedId || '') === String(p.id) ? ' selected' : '';
      return `<option value="${escapeHtml(p.id)}"${sel}>${escapeHtml(label)}</option>`;
    }).join('');
    return empty + opts;
  }

  function buildExcludeSet(excludeId) {
    const exclude = new Set();
    if (!excludeId) return exclude;
    const self = allGroups.find(g => String(g.id) === String(excludeId));
    if (!self) {
      exclude.add(String(excludeId));
      return exclude;
    }
    const prefix = (self.path || self.name) + '/';
    allGroups.forEach(g => {
      if (String(g.id) === String(excludeId)) exclude.add(String(g.id));
      else if ((g.path || '').startsWith(prefix) || g.path === self.path) exclude.add(String(g.id));
    });
    return exclude;
  }

  /** 扁平列表 → 树（按 path / parent_id） */
  function buildTree(excludeId) {
    const exclude = buildExcludeSet(excludeId);
    const nodes = allGroups
      .filter(g => !exclude.has(String(g.id)))
      .map(g => ({
        id: String(g.id),
        parentId: g.parent_id ? String(g.parent_id) : null,
        name: g.name,
        path: g.path || g.name,
        depth: Number(g.depth) || 0,
        children: []
      }));
    const map = Object.fromEntries(nodes.map(n => [n.id, n]));
    const roots = [];
    nodes.forEach(n => {
      if (n.parentId && map[n.parentId]) map[n.parentId].children.push(n);
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

  function parentLabel(parentId) {
    if (!parentId) return '（顶级机构）';
    const g = allGroups.find(x => String(x.id) === String(parentId));
    return g ? (g.path || g.name) : '（顶级机构）';
  }

  function renderParentTree(excludeId, selectedId) {
    const wrap = document.getElementById('group-parent-tree');
    if (!wrap) return;
    const selected = selectedId ? String(selectedId) : '';
    wrap.dataset.value = selected;
    wrap.className = 'member-group-picker';
    const label = parentLabel(selected || null);
    const flat = flattenTree(buildTree(excludeId));

    const rootSel = !selected ? ' is-selected' : '';
    let listBody = `<button type="button" class="mgp-node${rootSel}" data-id="" style="--d:0" role="option" aria-selected="${!selected ? 'true' : 'false'}">
        <span class="mgp-dot" aria-hidden="true"></span>
        <span class="mgp-name">（顶级机构）</span>
        <span class="mgp-check" aria-hidden="true"></span>
      </button>`;
    if (flat.length) {
      listBody += flat.map(n => {
        const sel = selected === n.id ? ' is-selected' : '';
        const branch = n.children && n.children.length ? ' is-branch' : '';
        return `<button type="button" class="mgp-node${sel}${branch}" data-id="${escapeHtml(n.id)}"
            style="--d:${n.depth + 1}" role="option" aria-selected="${selected === n.id ? 'true' : 'false'}">
          <span class="mgp-dot" aria-hidden="true"></span>
          <span class="mgp-name">${escapeHtml(n.name)}</span>
          <span class="mgp-check" aria-hidden="true"></span>
        </button>`;
      }).join('');
    }

    wrap.innerHTML = `
      <button type="button" class="form-input mgp-trigger" id="group-parent-trigger" aria-haspopup="listbox" aria-expanded="false">
        <span class="mgp-trigger-text${!selected ? ' is-placeholder' : ''}" id="group-parent-label">${escapeHtml(label)}</span>
        <span class="mgp-caret" aria-hidden="true"></span>
      </button>
      <div class="mgp-dropdown" id="group-parent-panel" role="listbox" hidden>${listBody}</div>`;

    const trigger = wrap.querySelector('#group-parent-trigger');
    const panel = wrap.querySelector('#group-parent-panel');
    const labelEl = wrap.querySelector('#group-parent-label');

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
        labelEl.textContent = parentLabel(id || null);
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

  function getParentValue() {
    const wrap = document.getElementById('group-parent-tree');
    return wrap ? (wrap.dataset.value || '') : '';
  }

  function groupRow(g) {
    const policyCell = g.initial_policy_id
      ? `<a class="btn-link" href="${U.href('initialPolicy')}">${escapeHtml(g.initial_policy_name || g.initial_policy_id)}</a>`
      : '<span class="text-muted">—</span>';
    const depth = Number(g.depth) || 0;
    const toggle = g.hasChildren
      ? `<button type="button" class="group-tree-toggle${g.expanded ? ' is-open' : ''}" data-toggle-id="${escapeHtml(g.id)}" aria-label="${g.expanded ? '收起' : '展开'}" title="${g.expanded ? '收起' : '展开'}"></button>`
      : '<span class="group-tree-toggle is-leaf" aria-hidden="true"></span>';
    return `<tr>
      <td>
        <div class="group-table-name" style="--d:${depth}">
          ${toggle}
          <span class="folder-icon">${depth === 0 ? '⌂' : '👥'}</span>
          <div class="name-text">${escapeHtml(g.name)}</div>
        </div>
      </td>
      <td class="text-muted" style="font-size:12px">${escapeHtml(g.path || '—')}</td>
      <td class="group-count-cell"><strong>${U.fmt(g.member_count || 0)}</strong></td>
      <td class="group-count-cell"><strong>${U.fmt(g.device_count || 0)}</strong></td>
      <td>${policyCell}</td>
      <td>
        <button class="btn btn-sm btn-link btn-edit-group" data-id="${escapeHtml(g.id)}">编辑</button>
        <button class="btn btn-sm btn-link btn-delete-group" data-id="${escapeHtml(g.id)}" data-name="${escapeHtml(g.name)}" style="color:var(--error)">删除</button>
      </td>
    </tr>`;
  }

  function tableHtml() {
    if (loadError) {
      return `<div class="panel"><div class="panel-body text-muted">${escapeHtml(loadError)}</div></div>`;
    }
    const rows = visibleRows();
    return `
      <div class="panel">
        <div class="panel-header"><h3>分组列表</h3><span class="extra" id="group-count">共 ${visibleGroupCount()} 个分组</span></div>
        <div class="panel-body" style="padding:0">
          <table class="data-table" id="group-table"><thead><tr>
            <th>分组名称</th><th>分组路径</th><th>成员数</th><th>绑定设备数</th><th>初始策略</th><th style="width:120px">操作</th>
          </tr></thead><tbody>
            ${rows.length ? rows.map(groupRow).join('') : '<tr><td colspan="6" class="text-muted" style="text-align:center;padding:24px">暂无分组，请新建</td></tr>'}
          </tbody></table>
        </div>
      </div>`;
  }

  await loadData();

  MDMLayout.mount({
    pageId: 'device-groups',
    title: '成员分组',
    content: `
      <div class="toolbar">
        <div class="toolbar-left">
          <div class="search-box"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/></svg>
            <input id="group-search" placeholder="分组名称、路径..." value="${escapeHtml(keyword)}"></div>
        </div>
        <div class="toolbar-right">
          <a class="btn" href="${U.href('initialPolicy')}">初始策略</a>
          <button class="btn btn-primary btn-add-group">+ 新建分组</button>
        </div>
      </div>
      <div id="group-list">${tableHtml()}</div>

      <div class="group-form-modal-mask">
        <div class="modal modal-lg">
          <div class="modal-header" id="group-modal-title">新建分组</div>
          <div class="modal-body">
            <div class="form-grid">
              <div class="form-item"><label class="form-label">分组名称 <span style="color:var(--error)">*</span></label><input class="form-input" id="group-name" placeholder="如 销售一部"></div>
              <div class="form-item"><label class="form-label">上级分组</label>
                <div class="member-group-picker" id="group-parent-tree" data-value=""></div>
              </div>
              <div class="form-item full"><label class="form-label">初始策略</label>
                <select class="form-select" id="group-initial-policy"></select>
              </div>
              <div class="form-item full"><label class="form-label">说明</label><textarea class="form-textarea" id="group-desc" style="min-height:72px" placeholder="分组用途说明（可选）"></textarea></div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn modal-cancel">取消</button>
            <button class="btn btn-primary modal-save">保存</button>
          </div>
        </div>
      </div>`,
    onMount() {
      const modal = document.querySelector('.group-form-modal-mask');
      const listEl = document.getElementById('group-list');
      let saving = false;

      document.addEventListener('click', e => {
        const wrap = document.getElementById('group-parent-tree');
        if (!wrap || !wrap.classList.contains('is-open')) return;
        if (wrap.contains(e.target)) return;
        if (typeof wrap._closeGroupPicker === 'function') wrap._closeGroupPicker();
      });
      document.addEventListener('keydown', e => {
        if (e.key !== 'Escape') return;
        const wrap = document.getElementById('group-parent-tree');
        if (wrap && typeof wrap._closeGroupPicker === 'function') wrap._closeGroupPicker();
      });
      window.addEventListener('resize', () => {
        const wrap = document.getElementById('group-parent-tree');
        if (wrap && wrap.classList.contains('is-open') && typeof wrap._placeGroupPicker === 'function') {
          wrap._placeGroupPicker();
        }
      });
      modal.querySelector('.modal-body')?.addEventListener('scroll', () => {
        const wrap = document.getElementById('group-parent-tree');
        if (wrap && wrap.classList.contains('is-open') && typeof wrap._placeGroupPicker === 'function') {
          wrap._placeGroupPicker();
        }
      }, { passive: true });

      function renderList() {
        if (listEl) listEl.innerHTML = tableHtml();
        bindList();
      }

      async function refresh() {
        await loadData();
        renderList();
      }

      function openModal(mode, group) {
        document.getElementById('group-modal-title').textContent = mode === 'edit' ? '编辑分组' : '新建分组';
        document.getElementById('group-name').value = group ? group.name : '';
        document.getElementById('group-desc').value = group ? (group.description || '') : '';
        renderParentTree(
          mode === 'edit' ? group.id : null,
          group ? group.parent_id : null
        );
        const policySel = document.getElementById('group-initial-policy');
        policySel.innerHTML = policyOptionsHtml(group ? group.initial_policy_id : null);
        modal.dataset.mode = mode;
        modal.dataset.id = group ? group.id : '';
        modal.classList.add('show');
      }

      function closeModal() {
        const wrap = document.getElementById('group-parent-tree');
        if (wrap && typeof wrap._closeGroupPicker === 'function') wrap._closeGroupPicker();
        modal.classList.remove('show');
      }

      document.querySelector('.btn-add-group').addEventListener('click', () => openModal('create'));
      modal.querySelector('.modal-cancel').onclick = closeModal;

      modal.querySelector('.modal-save').addEventListener('click', async () => {
        if (saving) return;
        const name = document.getElementById('group-name').value.trim();
        if (!name) {
          U.toast('请填写分组名称', 'error');
          return;
        }
        const parentRaw = getParentValue();
        const policyRaw = document.getElementById('group-initial-policy').value;
        const payload = {
          name,
          parent_id: parentRaw || null,
          initial_policy_id: policyRaw || null,
          description: document.getElementById('group-desc').value.trim() || null,
          status: 1
        };
        saving = true;
        try {
          if (modal.dataset.mode === 'edit') {
            await MDMApi.updateMemberGroup(modal.dataset.id, payload);
            U.toast('分组已更新');
          } else {
            await MDMApi.createMemberGroup(payload);
            U.toast('分组已创建');
          }
          closeModal();
          await refresh();
        } catch (e) {
          U.toast(e.message || '保存失败', 'error');
        } finally {
          saving = false;
        }
      });

      const searchInput = document.getElementById('group-search');
      let searchTimer = null;
      if (searchInput) {
        searchInput.addEventListener('input', () => {
          clearTimeout(searchTimer);
          searchTimer = setTimeout(() => {
            keyword = searchInput.value.trim();
            renderList();
          }, 300);
        });
      }

      function bindList() {
        const groupMap = Object.fromEntries(allGroups.map(g => [String(g.id), g]));
        document.querySelectorAll('.group-tree-toggle[data-toggle-id]').forEach(btn => {
          btn.addEventListener('click', e => {
            e.preventDefault();
            e.stopPropagation();
            const id = btn.dataset.toggleId;
            if (!id) return;
            if (expandedIds.has(id)) expandedIds.delete(id);
            else expandedIds.add(id);
            renderList();
          });
        });
        document.querySelectorAll('.btn-edit-group').forEach(btn => {
          btn.addEventListener('click', () => openModal('edit', groupMap[btn.dataset.id]));
        });
        document.querySelectorAll('.btn-delete-group').forEach(btn => {
          btn.addEventListener('click', () => {
            U.confirm('确认删除该分组？', async () => {
              try {
                await MDMApi.deleteMemberGroup(btn.dataset.id);
                U.toast('已删除');
                await refresh();
              } catch (e) {
                U.toast(e.message || '删除失败', 'error');
              }
            });
          });
        });
      }

      bindList();
    }
  });
})();
