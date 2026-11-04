(async function () {
  const U = MDMUtils;
  const catalog = (MDM.policyCommands || MDM.commands || []).slice();

  /** @type {{ policy_code: string, param: object }[]} */
  let draftItems = [];
  /** @type {string[]} */
  let selectedGroupIds = [];
  /** @type {Set<string>} */
  let selectedMemberIds = new Set();
  let targetType = 'group';
  /** @type {any[]} */
  let groups = [];
  /** @type {any[]} */
  let memberOptions = [];
  let memberKeyword = '';
  let editingIndex = null;
  let submitting = false;

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function cmdOf(code) {
    return U.findCommand(U.normalizePolicyCode(code));
  }

  function defaultParams(cmd) {
    const vals = {};
    (cmd.params || []).forEach(p => {
      if (p.default != null) vals[p.key] = p.default;
      else if (
        p.type === 'array_string' ||
        p.type === 'array_object' ||
        p.type === 'app_multi_select' ||
        p.type === 'app_install_select' ||
        p.type === 'firewall_rules'
      ) {
        vals[p.key] = [];
      }
    });
    return vals;
  }

  function collectItemParam(cmd, box) {
    const raw = U.collectParamValues(box);
    try {
      const body = JSON.parse(U.buildCommandPayload(cmd, raw) || '{}');
      return (body && body.param) || raw || {};
    } catch (_) {
      return raw || {};
    }
  }

  function usedCodes(exceptIndex) {
    const set = new Set();
    draftItems.forEach((it, i) => {
      if (exceptIndex != null && i === exceptIndex) return;
      set.add(it.policy_code);
    });
    return set;
  }

  function itemSummary(item) {
    return U.policyItemSummary(item.policy_code, item.param || {});
  }

  function buildGroupTree() {
    const byParent = {};
    groups.forEach(g => {
      const pid = g.parent_id != null && g.parent_id !== '' ? String(g.parent_id) : '';
      if (!byParent[pid]) byParent[pid] = [];
      byParent[pid].push(g);
    });
    function walk(pid, depth) {
      return (byParent[pid] || []).map(g => ({
        ...g,
        depth,
        children: walk(String(g.id), depth + 1)
      }));
    }
    return walk('', 0);
  }

  function flattenTree(nodes, acc) {
    const out = acc || [];
    (nodes || []).forEach(n => {
      out.push(n);
      if (n.children && n.children.length) flattenTree(n.children, out);
    });
    return out;
  }

  function collectDescendantIds(rootId) {
    const ids = new Set([String(rootId)]);
    const byParent = {};
    groups.forEach(g => {
      const pid = g.parent_id != null && g.parent_id !== '' ? String(g.parent_id) : '';
      if (!byParent[pid]) byParent[pid] = [];
      byParent[pid].push(String(g.id));
    });
    const stack = [String(rootId)];
    while (stack.length) {
      const cur = stack.pop();
      (byParent[cur] || []).forEach(cid => {
        if (!ids.has(cid)) {
          ids.add(cid);
          stack.push(cid);
        }
      });
    }
    return ids;
  }

  function collectNodeDescendantIds(node, acc) {
    const out = acc || [];
    (node.children || []).forEach(c => {
      out.push(String(c.id));
      collectNodeDescendantIds(c, out);
    });
    return out;
  }

  function estimateGroupDevices() {
    // 粗略：所选各根分组的 device_count 相加（含子组统计已在后端按人聚合，前端仅提示）
    // 为避免重复计数，仅对「未被其他已选分组祖先覆盖」的分组累加
    const selected = new Set(selectedGroupIds.map(String));
    let total = 0;
    selectedGroupIds.forEach(gid => {
      const coveredByAncestor = selectedGroupIds.some(other => {
        if (String(other) === String(gid)) return false;
        return collectDescendantIds(other).has(String(gid));
      });
      if (coveredByAncestor) return;
      const g = groups.find(x => String(x.id) === String(gid));
      total += g ? (Number(g.device_count) || 0) : 0;
    });
    return total;
  }

  function groupLabelOf(id) {
    const g = groups.find(x => String(x.id) === String(id));
    return g ? (g.path || g.name) : String(id);
  }

  /** 已选人员缓存（搜索后仍能展示芯片） */
  const selectedMemberCache = {};

  function memberLabelOf(id) {
    const m = selectedMemberCache[String(id)];
    if (!m) return String(id);
    return m.employee_id ? `${m.name}（${m.employee_id}）` : (m.name || String(id));
  }

  function renderTargetSummary() {
    const wrap = document.getElementById('pd-target-summary');
    if (!wrap) return;

    const isGroup = targetType === 'group';
    const count = isGroup ? selectedGroupIds.length : selectedMemberIds.size;
    const previewIds = isGroup
      ? selectedGroupIds.slice(0, 8)
      : Array.from(selectedMemberIds).slice(0, 8);
    const more = Math.max(0, count - previewIds.length);

    let chipsHtml = '';
    if (!count) {
      chipsHtml = `<div class="pd-target-summary-empty">${isGroup ? '尚未选择分组' : '尚未选择人员'}，点击右侧按钮打开选择器</div>`;
    } else {
      chipsHtml = previewIds.map(id => {
        const label = isGroup ? groupLabelOf(id) : memberLabelOf(id);
        return `<span class="pd-chip pd-chip-static" title="${escapeHtml(label)}"><span class="pd-chip-text">${escapeHtml(label)}</span></span>`;
      }).join('');
      if (more > 0) {
        chipsHtml += `<span class="pd-chip pd-chip-more">+${more}</span>`;
      }
    }

    const hint = isGroup
      ? (count ? `已选 ${count} 个分组 · 约 ${estimateGroupDevices()} 台设备` : '按分组下发（含子组设备）')
      : (count ? `已选 ${count} 人 · 一人一设备` : '仅可选已绑定设备的人员');

    wrap.innerHTML = `
      <div class="pd-target-summary">
        <div class="pd-target-summary-main">
          <div class="pd-target-summary-meta">${escapeHtml(hint)}</div>
          <div class="pd-target-summary-chips">${chipsHtml}</div>
        </div>
        <div class="pd-target-summary-actions">
          <button type="button" class="btn btn-primary btn-sm" id="pd-open-target-modal">
            ${count ? (isGroup ? '修改分组' : '修改人员') : (isGroup ? '选择分组' : '选择人员')}
          </button>
          ${count ? `<button type="button" class="btn btn-sm btn-link" id="pd-clear-target">清空</button>` : ''}
        </div>
      </div>`;

    wrap.querySelector('#pd-open-target-modal')?.addEventListener('click', () => openTargetModal());
    wrap.querySelector('#pd-clear-target')?.addEventListener('click', () => {
      if (isGroup) selectedGroupIds = [];
      else selectedMemberIds.clear();
      renderTargetSummary();
    });
  }

  function openTargetModal() {
    if (targetType === 'group') openGroupPickerModal();
    else openMemberPickerModal();
  }

  function renderGroupTreeRows(tree, selectedSet, expandedSet) {
    if (!tree.length) {
      return '<div class="batch-group-empty">暂无成员分组</div>';
    }
    const rows = [];
    function walk(nodes, depth) {
      nodes.forEach(n => {
        const id = String(n.id);
        const hasChildren = !!(n.children && n.children.length);
        const expanded = hasChildren && expandedSet.has(id);
        const checked = selectedSet.has(id);
        const descIds = hasChildren ? collectNodeDescendantIds(n) : [];
        const descChecked = descIds.filter(x => selectedSet.has(x)).length;
        const indeterminate = !checked && descChecked > 0 && descChecked < descIds.length;
        const toggle = hasChildren
          ? `<button type="button" class="batch-group-toggle${expanded ? ' is-open' : ''}" data-toggle-id="${escapeHtml(id)}" aria-label="${expanded ? '收起' : '展开'}"></button>`
          : '<span class="batch-group-toggle is-leaf" aria-hidden="true"></span>';
        rows.push(`<div class="batch-group-option${checked ? ' is-checked' : ''}" style="--d:${depth}">
          ${toggle}
          <label class="batch-group-option-label">
            <input type="checkbox" class="pd-group-cb" value="${escapeHtml(id)}"${checked ? ' checked' : ''}${indeterminate ? ' data-indeterminate="1"' : ''}>
            <span class="batch-group-option-text">
              <span class="batch-group-option-name">${escapeHtml(n.name)}</span>
              <span class="batch-group-option-meta">${Number(n.device_count) || 0} 台</span>
            </span>
          </label>
        </div>`);
        if (expanded) walk(n.children, depth + 1);
      });
    }
    walk(tree, 0);
    return rows.join('');
  }

  function openGroupPickerModal() {
    const tree = buildGroupTree();
    const flat = flattenTree(tree);
    const nodeMap = Object.fromEntries(flat.map(n => [String(n.id), n]));
    let selected = new Set(selectedGroupIds.map(String));
    const expandedIds = new Set(
      tree.filter(n => n.children && n.children.length).map(n => String(n.id))
    );

    U.modal({
      title: '选择成员分组',
      okText: '确定',
      size: 'sm',
      body: `
        <div class="form-item" style="margin-bottom:0">
          <label class="form-label">目标分组 <span class="required">*</span></label>
          <div class="batch-group-picker is-open" id="pd-group-picker">
            <div class="batch-group-panel">
              <div class="batch-group-tools">
                <label class="batch-group-all">
                  <input type="checkbox" id="pd-group-all">
                  <span>全选</span>
                </label>
                <button type="button" class="btn-link" id="pd-group-clear">清空</button>
              </div>
              <div class="batch-group-options" id="pd-group-list"></div>
            </div>
          </div>
          <div class="batch-group-hint">勾选父组将自动选中全部子组</div>
        </div>`,
      onOk: () => {
        if (!selected.size) {
          U.toast('请至少选择一个成员分组', 'error');
          return false;
        }
        selectedGroupIds = Array.from(selected);
        renderTargetSummary();
        return true;
      }
    });

    const listEl = document.getElementById('pd-group-list');
    const allCb = document.getElementById('pd-group-all');
    const clearBtn = document.getElementById('pd-group-clear');

    function subtreeIds(id) {
      const node = nodeMap[id];
      if (!node) return [id];
      return [id, ...collectNodeDescendantIds(node)];
    }

    function clearAncestors(id) {
      let cur = nodeMap[id];
      while (cur && cur.parent_id != null && cur.parent_id !== '') {
        const pid = String(cur.parent_id);
        selected.delete(pid);
        cur = nodeMap[pid];
      }
    }

    function bubbleAncestors(id) {
      let cur = nodeMap[id];
      while (cur && cur.parent_id != null && cur.parent_id !== '') {
        const pid = String(cur.parent_id);
        const parent = nodeMap[pid];
        if (!parent) break;
        const childIds = (parent.children || []).map(c => String(c.id));
        if (childIds.length && childIds.every(cid => selected.has(cid))) {
          selected.add(pid);
          cur = parent;
        } else {
          break;
        }
      }
    }

    function syncAllCheckbox() {
      if (!allCb || !flat.length) return;
      const n = selected.size;
      allCb.checked = n > 0 && n === flat.length;
      allCb.indeterminate = n > 0 && n < flat.length;
    }

    function applyIndeterminate() {
      listEl?.querySelectorAll('.pd-group-cb').forEach(cb => {
        cb.indeterminate = cb.dataset.indeterminate === '1';
      });
    }

    function bindListEvents() {
      listEl?.querySelectorAll('.batch-group-toggle[data-toggle-id]').forEach(btn => {
        btn.addEventListener('click', e => {
          e.preventDefault();
          e.stopPropagation();
          const id = btn.dataset.toggleId;
          if (!id) return;
          if (expandedIds.has(id)) expandedIds.delete(id);
          else expandedIds.add(id);
          rerenderList();
        });
      });
      listEl?.querySelectorAll('.pd-group-cb').forEach(cb => {
        cb.addEventListener('change', () => {
          const id = String(cb.value);
          const ids = subtreeIds(id);
          if (cb.checked) {
            ids.forEach(x => selected.add(x));
            bubbleAncestors(id);
          } else {
            ids.forEach(x => selected.delete(x));
            clearAncestors(id);
          }
          rerenderList();
        });
      });
    }

    function rerenderList() {
      if (listEl) listEl.innerHTML = renderGroupTreeRows(tree, selected, expandedIds);
      bindListEvents();
      applyIndeterminate();
      syncAllCheckbox();
    }

    allCb?.addEventListener('change', () => {
      if (allCb.checked) selected = new Set(flat.map(g => String(g.id)));
      else selected = new Set();
      rerenderList();
    });
    clearBtn?.addEventListener('click', e => {
      e.preventDefault();
      selected = new Set();
      rerenderList();
    });

    rerenderList();
  }

  function renderMemberRows(rows, selectedSet) {
    if (!rows.length) {
      return '<div class="batch-group-empty">输入姓名筛选后勾选人员</div>';
    }
    return rows.map(m => {
      const id = String(m.id);
      const checked = selectedSet.has(id);
      const meta = [m.employee_id, m.department_path || m.department_name]
        .filter(Boolean)
        .join(' · ');
      return `<div class="batch-group-option${checked ? ' is-checked' : ''}" style="--d:0">
        <span class="batch-group-toggle is-leaf" aria-hidden="true"></span>
        <label class="batch-group-option-label">
          <input type="checkbox" class="pd-member-cb" value="${escapeHtml(id)}"${checked ? ' checked' : ''}>
          <span class="batch-group-option-text">
            <span class="batch-group-option-name">${escapeHtml(m.name || id)}</span>
            <span class="batch-group-option-meta">${escapeHtml(meta || '已绑定')}</span>
          </span>
        </label>
      </div>`;
    }).join('');
  }

  async function loadMembers() {
    try {
      const data = await MDMApi.listPolicyTargetMembers({
        keyword: memberKeyword,
        page: 1,
        page_size: 100
      });
      memberOptions = data.items || [];
      memberOptions.forEach(m => { selectedMemberCache[String(m.id)] = m; });
    } catch (e) {
      memberOptions = [];
      U.toast(e.message || '加载人员失败', 'error');
    }
  }

  async function openMemberPickerModal() {
    let selected = new Set(selectedMemberIds);
    memberKeyword = memberKeyword || '';
    await loadMembers();

    U.modal({
      title: '选择人员',
      okText: '确定',
      size: 'sm',
      body: `
        <div class="form-item" style="margin-bottom:0">
          <label class="form-label">目标人员 <span class="required">*</span></label>
          <div class="batch-group-picker is-open" id="pd-member-picker">
            <div class="batch-group-panel">
              <div class="batch-group-search-bar">
                <input type="search" class="form-input" id="pd-member-kw" placeholder="按姓名筛选" value="${escapeHtml(memberKeyword)}">
              </div>
              <div class="batch-group-tools">
                <label class="batch-group-all">
                  <input type="checkbox" id="pd-member-all">
                  <span>全选当前</span>
                </label>
                <button type="button" class="btn-link" id="pd-member-clear">清空</button>
              </div>
              <div class="batch-group-options" id="pd-member-list"></div>
            </div>
          </div>
          <div class="batch-group-hint" id="pd-member-hint">按姓名筛选后勾选（仅已绑定设备）</div>
        </div>`,
      onOk: () => {
        if (!selected.size) {
          U.toast('请至少选择一名人员', 'error');
          return false;
        }
        selectedMemberIds = new Set(selected);
        renderTargetSummary();
        return true;
      }
    });

    const listEl = document.getElementById('pd-member-list');
    const kwInput = document.getElementById('pd-member-kw');
    const allCb = document.getElementById('pd-member-all');
    const clearBtn = document.getElementById('pd-member-clear');
    const hintEl = document.getElementById('pd-member-hint');
    let searchTimer = null;

    function syncAllCheckbox() {
      const rows = memberOptions || [];
      if (!allCb) return;
      if (!rows.length) {
        allCb.checked = false;
        allCb.indeterminate = false;
        return;
      }
      const checkedN = rows.filter(m => selected.has(String(m.id))).length;
      allCb.checked = checkedN === rows.length;
      allCb.indeterminate = checkedN > 0 && checkedN < rows.length;
    }

    function syncHint() {
      if (!hintEl) return;
      const n = selected.size;
      hintEl.textContent = n
        ? `已选 ${n} 人 · 按姓名筛选后勾选（仅已绑定设备）`
        : '按姓名筛选后勾选（仅已绑定设备）';
    }

    function bindListEvents() {
      listEl?.querySelectorAll('.pd-member-cb').forEach(cb => {
        cb.addEventListener('change', () => {
          const id = String(cb.value);
          if (cb.checked) selected.add(id);
          else selected.delete(id);
          // 只更新勾选态与工具栏，避免整表重绘打断连续勾选
          cb.closest('.batch-group-option')?.classList.toggle('is-checked', cb.checked);
          syncAllCheckbox();
          syncHint();
        });
      });
    }

    function rerenderList() {
      if (listEl) listEl.innerHTML = renderMemberRows(memberOptions || [], selected);
      bindListEvents();
      syncAllCheckbox();
      syncHint();
    }

    async function doSearch() {
      memberKeyword = (kwInput?.value || '').trim();
      await loadMembers();
      rerenderList();
    }

    kwInput?.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(doSearch, 220);
    });
    kwInput?.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        clearTimeout(searchTimer);
        doSearch();
      }
    });

    allCb?.addEventListener('change', () => {
      const rows = memberOptions || [];
      if (allCb.checked) rows.forEach(m => selected.add(String(m.id)));
      else rows.forEach(m => selected.delete(String(m.id)));
      rerenderList();
    });
    clearBtn?.addEventListener('click', e => {
      e.preventDefault();
      selected = new Set();
      rerenderList();
    });

    rerenderList();
    kwInput?.focus();
  }

  function ensureModal() {
    let mask = document.getElementById('pd-cfg-mask');
    if (mask) return mask;
    mask = document.createElement('div');
    mask.id = 'pd-cfg-mask';
    mask.className = 'modal-mask';
    mask.innerHTML = `<div class="modal modal-xl ip-item-config-modal">
      <div class="modal-header" id="pd-cfg-title">配置策略项</div>
      <div class="modal-body" id="pd-cfg-body"></div>
      <div class="modal-footer">
        <button type="button" class="btn" id="pd-cfg-cancel">取消</button>
        <button type="button" class="btn btn-primary" id="pd-cfg-ok">确定</button>
      </div>
    </div>`;
    document.body.appendChild(mask);
    document.getElementById('pd-cfg-cancel').onclick = closeModal;
    return mask;
  }

  function closeModal() {
    const mask = document.getElementById('pd-cfg-mask');
    if (mask) mask.classList.remove('show');
    editingIndex = null;
  }

  function mountModalParams(code, param) {
    const box = document.getElementById('pd-cfg-params');
    if (!box) return;
    const cmd = cmdOf(code);
    if (!cmd) {
      box.innerHTML = '<p class="cmd-param-empty">未找到策略定义</p>';
      return;
    }
    const vals = param && Object.keys(param).length ? param : defaultParams(cmd);
    U.mountCommandParamForm(box, cmd, vals, { dense: true, collapseOptional: true });
  }

  function policyTitle(code) {
    const cmd = cmdOf(code);
    return cmd ? `${cmd.name}（${code}）` : (code || '');
  }

  function openConfigModal(opts) {
    const { index, code, param } = opts || {};
    editingIndex = index != null ? index : null;
    const isNew = editingIndex == null;
    const mask = ensureModal();
    const titleEl = document.getElementById('pd-cfg-title');

    const used = usedCodes(editingIndex);
    const options = catalog.filter(c => !used.has(c.code) || c.code === code);
    const selected = isNew ? '' : (code || '');

    // 编辑：类型固定在标题；新增：标题通用，正文选类型
    if (isNew) {
      titleEl.textContent = '添加策略项';
      document.getElementById('pd-cfg-body').innerHTML = `
        <div class="ip-modal-pick">
          <label class="form-label" style="margin:0">策略类型</label>
          <select class="form-select" id="pd-cfg-code">
            <option value="">请选择策略…</option>
            ${options.map(c =>
              `<option value="${escapeHtml(c.code)}">${escapeHtml(c.name)}（${escapeHtml(c.code)}）</option>`
            ).join('')}
          </select>
        </div>
        <div class="ip-modal-params" id="pd-cfg-params"></div>`;
    } else {
      titleEl.textContent = `编辑策略 · ${policyTitle(selected)}`;
      document.getElementById('pd-cfg-body').innerHTML = `
        <select id="pd-cfg-code" hidden>
          <option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)}</option>
        </select>
        <div class="ip-modal-params" id="pd-cfg-params"></div>`;
    }

    const sel = document.getElementById('pd-cfg-code');
    const remount = () => {
      const c = sel.value;
      if (!c) {
        document.getElementById('pd-cfg-params').innerHTML =
          '<p class="cmd-param-empty">请先选择策略类型</p>';
        return;
      }
      if (isNew) {
        const emptyOpt = sel.querySelector('option[value=""]');
        if (emptyOpt) emptyOpt.remove();
        titleEl.textContent = `添加策略 · ${policyTitle(c)}`;
      }
      const keep = (!isNew && c === code) ? param : defaultParams(cmdOf(c) || { params: [] });
      mountModalParams(c, keep);
    };
    if (isNew) sel.addEventListener('change', remount);
    remount();

    document.getElementById('pd-cfg-ok').onclick = () => {
      const c = sel.value;
      if (!c) {
        U.toast('请选择策略类型', 'error');
        return;
      }
      const cmd = cmdOf(c);
      if (!cmd) {
        U.toast('策略定义不存在', 'error');
        return;
      }
      const box = document.getElementById('pd-cfg-params');
      const nextParam = collectItemParam(cmd, box);
      if (isNew) {
        if (usedCodes().has(c)) {
          U.toast('该策略类型已添加', 'error');
          return;
        }
        draftItems.push({ policy_code: c, param: nextParam });
      } else {
        draftItems[editingIndex] = { policy_code: c, param: nextParam };
      }
      closeModal();
      renderItemList();
    };

    mask.classList.add('show');
  }

  function renderItemList() {
    const wrap = document.getElementById('pd-item-list');
    if (!wrap) return;
    if (!draftItems.length) {
      wrap.innerHTML = '<p class="text-muted" style="margin:0">尚未添加策略项，点击下方「添加策略」在弹窗中配置</p>';
      return;
    }
    wrap.innerHTML = `<table class="ip-item-table">
      <thead><tr>
        <th style="width:48px">#</th>
        <th>策略</th>
        <th>摘要</th>
        <th style="width:220px;text-align:right">操作</th>
      </tr></thead>
      <tbody>${draftItems.map((it, i) => {
        const cmd = cmdOf(it.policy_code);
        const name = cmd ? cmd.name : it.policy_code;
        const summary = itemSummary(it);
        return `<tr data-index="${i}">
          <td>${i + 1}</td>
          <td>${escapeHtml(name)}</td>
          <td><div class="ip-item-summary" title="${escapeHtml(summary)}">${escapeHtml(summary)}</div></td>
          <td><div class="ip-item-actions">
            <button type="button" class="btn btn-sm btn-primary pd-edit">编辑</button>
            <button type="button" class="btn btn-sm pd-up"${i === 0 ? ' disabled' : ''}>上移</button>
            <button type="button" class="btn btn-sm pd-down"${i === draftItems.length - 1 ? ' disabled' : ''}>下移</button>
            <button type="button" class="btn btn-sm btn-link pd-del">删除</button>
          </div></td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;

    wrap.querySelectorAll('tr[data-index]').forEach(tr => {
      const i = Number(tr.dataset.index);
      tr.querySelector('.pd-edit')?.addEventListener('click', () => {
        const it = draftItems[i];
        openConfigModal({ index: i, code: it.policy_code, param: it.param });
      });
      tr.querySelector('.pd-up')?.addEventListener('click', () => {
        if (i <= 0) return;
        const t = draftItems[i - 1];
        draftItems[i - 1] = draftItems[i];
        draftItems[i] = t;
        renderItemList();
      });
      tr.querySelector('.pd-down')?.addEventListener('click', () => {
        if (i >= draftItems.length - 1) return;
        const t = draftItems[i + 1];
        draftItems[i + 1] = draftItems[i];
        draftItems[i] = t;
        renderItemList();
      });
      tr.querySelector('.pd-del')?.addEventListener('click', () => {
        draftItems.splice(i, 1);
        renderItemList();
      });
    });
  }

  // 预加载分组
  try {
    const gdata = await MDMApi.listMemberGroups();
    groups = gdata.items || [];
  } catch (e) {
    groups = [];
    U.toast(e.message || '加载分组失败', 'error');
  }

  MDMLayout.mount({
    pageId: 'scene-dispatch-create',
    title: '策略下发',
    content: `
      <div class="panel">
        <div class="panel-header"><h3>创建策略任务</h3></div>
        <div class="panel-body">
          <div class="form-grid">
            <div class="form-item"><label class="form-label">任务名称 <span style="color:var(--error)">*</span></label>
              <input class="form-input" id="task-name" value="策略批量下发" placeholder="任务名称"></div>
            ${U.renderPolicyDispatchFields({ level: 'normal', deadlineHours: 4 })}
          </div>

          <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border)">
            <div class="form-label" style="margin-bottom:10px">目标范围 <span style="color:var(--error)">*</span></div>
            <div class="pd-target-mode" id="target-type-mode" role="group" aria-label="目标范围">
              <button type="button" class="pd-target-mode-btn is-active" data-type="group">按成员分组</button>
              <button type="button" class="pd-target-mode-btn" data-type="member">手动选择人员</button>
            </div>
            <input type="hidden" id="target-type" value="group">
            <div id="pd-target-summary" style="margin-top:12px"></div>
          </div>
        </div>
      </div>

      <div class="panel" style="margin-top:16px">
        <div class="panel-header">
          <h3>策略项</h3>
        </div>
        <div class="panel-body">
          <div id="pd-item-list"></div>
          <div style="margin-top:14px">
            <button type="button" class="btn btn-primary" id="pd-add-btn">+ 添加策略</button>
          </div>
        </div>
      </div>

      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="btn btn-primary btn-submit" type="button" id="btn-submit">创建并下发策略</button>
        <a class="btn" href="${U.href('sceneDispatch')}">取消</a>
      </div>`,
    onMount() {
      const policyApi = U.bindPolicyDispatchFields();
      renderTargetSummary();
      renderItemList();

      const modeWrap = document.getElementById('target-type-mode');
      const targetTypeInput = document.getElementById('target-type');
      modeWrap?.querySelectorAll('.pd-target-mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const next = btn.dataset.type || 'group';
          if (next === targetType) return;
          targetType = next;
          if (targetTypeInput) targetTypeInput.value = next;
          modeWrap.querySelectorAll('.pd-target-mode-btn').forEach(b => {
            b.classList.toggle('is-active', b.dataset.type === next);
          });
          renderTargetSummary();
        });
      });

      document.getElementById('pd-add-btn')?.addEventListener('click', () => {
        if (usedCodes().size >= catalog.length) {
          U.toast('已添加全部策略类型', 'info');
          return;
        }
        openConfigModal({});
      });

      document.getElementById('btn-submit')?.addEventListener('click', async () => {
        if (submitting) return;
        const name = (document.getElementById('task-name')?.value || '').trim();
        if (!name) {
          U.toast('请填写任务名称', 'error');
          return;
        }
        if (!draftItems.length) {
          U.toast('请至少添加一条策略项', 'error');
          return;
        }
        if (targetType === 'group' && !selectedGroupIds.length) {
          U.toast('请选择成员分组', 'error');
          return;
        }
        if (targetType === 'member' && !selectedMemberIds.size) {
          U.toast('请选择人员', 'error');
          return;
        }

        const level = policyApi.getLevel();
        const payload = {
          name,
          policy_level: level,
          wait_hours: level === 'normal' ? (policyApi.getDeadlineHours() || 4) : null,
          target_type: targetType,
          group_ids: targetType === 'group' ? selectedGroupIds.slice() : [],
          member_ids: targetType === 'member' ? Array.from(selectedMemberIds) : [],
          items: draftItems.map((it, i) => ({
            policy_code: it.policy_code,
            param: it.param || {},
            sort: i + 1
          }))
        };

        submitting = true;
        const btn = document.getElementById('btn-submit');
        if (btn) {
          btn.disabled = true;
          btn.textContent = '下发中…';
        }
        try {
          const created = await MDMApi.createPolicyTask(payload);
          U.toast('策略任务已创建并下发');
          location.href = `${U.href('sceneDispatch')}?_=${Date.now()}`;
        } catch (e) {
          U.toast(e.message || '下发失败', 'error');
          submitting = false;
          if (btn) {
            btn.disabled = false;
            btn.textContent = '确认下发';
          }
        }
      });
    }
  });
})();
