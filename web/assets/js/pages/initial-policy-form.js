(async function () {
  const U = MDMUtils;
  const policyId = U.query('id');
  const isEdit = !!policyId;
  const catalog = (MDM.policyCommands || MDM.commands || []).slice();

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  /** @type {{ policy_code: string, param: object }[]} */
  let draftItems = [];
  let meta = { name: '', description: '', is_default: false };
  /** 弹窗编辑中的下标；null 表示新增 */
  let editingIndex = null;

  if (isEdit) {
    try {
      const detail = await MDMApi.getInitialPolicy(policyId);
      meta = {
        name: detail.name || '',
        description: detail.description || '',
        is_default: !!detail.is_default
      };
      draftItems = (detail.items || [])
        .slice()
        .sort((a, b) => (a.sort || 0) - (b.sort || 0))
        .map(it => ({
          policy_code: U.normalizePolicyCode(it.policy_code),
          param: it.param && typeof it.param === 'object' ? it.param : {}
        }));
    } catch (e) {
      U.toast(e.message || '加载失败', 'error');
      location.href = U.href('initialPolicy');
      return;
    }
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

  function cmdOf(code) {
    return U.findCommand(U.normalizePolicyCode(code));
  }

  function itemSummary(item) {
    // 编辑中以当前 param 为准，保证改参后摘要即时刷新
    return U.policyItemSummary(item.policy_code, item.param || {});
  }

  function ensureModal() {
    let mask = document.getElementById('ip-cfg-mask');
    if (mask) return mask;
    mask = document.createElement('div');
    mask.id = 'ip-cfg-mask';
    mask.className = 'modal-mask';
    mask.innerHTML = `<div class="modal modal-xl ip-item-config-modal">
      <div class="modal-header" id="ip-cfg-title">配置策略项</div>
      <div class="modal-body" id="ip-cfg-body"></div>
      <div class="modal-footer">
        <button type="button" class="btn" id="ip-cfg-cancel">取消</button>
        <button type="button" class="btn btn-primary" id="ip-cfg-ok">确定</button>
      </div>
    </div>`;
    document.body.appendChild(mask);
    document.getElementById('ip-cfg-cancel').onclick = closeModal;
    return mask;
  }

  function closeModal() {
    const mask = document.getElementById('ip-cfg-mask');
    if (mask) mask.classList.remove('show');
    editingIndex = null;
  }

  function mountModalParams(code, param) {
    const box = document.getElementById('ip-cfg-params');
    if (!box) return;
    const cmd = cmdOf(code);
    if (!cmd) {
      box.innerHTML = `<p class="cmd-param-empty">未找到策略定义</p>`;
      return;
    }
    const vals = param && Object.keys(param).length ? param : defaultParams(cmd);
    U.mountCommandParamForm(box, cmd, vals, { dense: true, collapseOptional: true });
  }

  function policyTitle(code) {
    const normalized = U.normalizePolicyCode(code);
    const cmd = cmdOf(normalized);
    return cmd ? cmd.name : (normalized || '');
  }

  function openConfigModal(opts) {
    const { index, code, param } = opts || {};
    editingIndex = index != null ? index : null;
    const isNew = editingIndex == null;
    const mask = ensureModal();
    const titleEl = document.getElementById('ip-cfg-title');

    const used = usedCodes(editingIndex);
    const options = catalog.filter(c => !used.has(c.code) || c.code === code);
    // 新增：默认不选类型；编辑：固定为当前类型（显示在标题）
    const selected = isNew ? '' : (code || '');

    if (isNew) {
      titleEl.textContent = '添加策略项';
      document.getElementById('ip-cfg-body').innerHTML = `
        <div class="ip-modal-pick">
          <label class="form-label" style="margin:0">策略类型</label>
          <select class="form-select" id="ip-cfg-code">
            <option value="">请选择策略…</option>
            ${options.map(c =>
              `<option value="${escapeHtml(c.code)}">${escapeHtml(c.name)}（${escapeHtml(c.code)}）</option>`
            ).join('')}
          </select>
        </div>
        <div class="ip-modal-params" id="ip-cfg-params"></div>`;
    } else {
      titleEl.textContent = `编辑策略 · ${policyTitle(selected)}`;
      document.getElementById('ip-cfg-body').innerHTML = `
        <select id="ip-cfg-code" hidden>
          <option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)}</option>
        </select>
        <div class="ip-modal-params" id="ip-cfg-params"></div>`;
    }

    const sel = document.getElementById('ip-cfg-code');
    const remount = () => {
      const c = sel.value;
      if (!c) {
        document.getElementById('ip-cfg-params').innerHTML =
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

    document.getElementById('ip-cfg-ok').onclick = () => {
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
      const box = document.getElementById('ip-cfg-params');
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
      renderList();
    };

    mask.classList.add('show');
  }

  function renderList() {
    const wrap = document.getElementById('ip-item-list');
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
            <button type="button" class="btn btn-sm btn-primary ip-edit">编辑</button>
            <button type="button" class="btn btn-sm ip-up"${i === 0 ? ' disabled' : ''}>上移</button>
            <button type="button" class="btn btn-sm ip-down"${i === draftItems.length - 1 ? ' disabled' : ''}>下移</button>
            <button type="button" class="btn btn-sm btn-link ip-del">删除</button>
          </div></td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;

    wrap.querySelectorAll('tr[data-index]').forEach(tr => {
      const i = Number(tr.dataset.index);
      tr.querySelector('.ip-edit')?.addEventListener('click', () => {
        const it = draftItems[i];
        openConfigModal({ index: i, code: it.policy_code, param: it.param });
      });
      tr.querySelector('.ip-up')?.addEventListener('click', () => {
        if (i <= 0) return;
        const t = draftItems[i - 1];
        draftItems[i - 1] = draftItems[i];
        draftItems[i] = t;
        renderList();
      });
      tr.querySelector('.ip-down')?.addEventListener('click', () => {
        if (i >= draftItems.length - 1) return;
        const t = draftItems[i + 1];
        draftItems[i + 1] = draftItems[i];
        draftItems[i] = t;
        renderList();
      });
      tr.querySelector('.ip-del')?.addEventListener('click', () => {
        draftItems.splice(i, 1);
        renderList();
      });
    });
  }

  MDMLayout.mount({
    pageId: 'initial-policy-form',
    title: '初始策略',
    breadcrumb: `<a href="${U.href('deviceGroups')}">成员分组</a> / <a href="${U.href('initialPolicy')}">初始策略</a> / ${isEdit ? '编辑模板' : '新建模板'}`,
    content: `
      <div class="panel">
        <div class="panel-header"><h3>${isEdit ? '编辑策略模板' : '新建策略模板'}</h3></div>
        <div class="panel-body">
          <div class="form-grid">
            <div class="form-item full"><label class="form-label">策略名称 <span style="color:var(--error)">*</span></label>
              <input class="form-input" id="f-name" value="${escapeHtml(meta.name)}" placeholder="如 全员默认初始策略"></div>
            <div class="form-item full"><label class="form-label">说明</label>
              <textarea class="form-textarea" id="f-desc" rows="2" placeholder="激活时下发说明">${escapeHtml(meta.description)}</textarea></div>
          </div>
          <p class="param-hint" style="margin-bottom:0">模板不绑定分组；分组侧后续在成员分组中关联本模板。</p>
        </div>
      </div>

      <div class="panel" style="margin-top:16px">
        <div class="panel-header">
          <h3>策略项</h3>
          <span class="extra">弹窗配置 · 列表仅展示摘要与顺序</span>
        </div>
        <div class="panel-body">
          <div id="ip-item-list"></div>
          <div style="margin-top:14px">
            <button type="button" class="btn btn-primary" id="ip-add-btn">+ 添加策略</button>
          </div>
        </div>
      </div>

      <div style="margin-top:20px;display:flex;gap:8px">
        <button class="btn btn-primary" type="button" id="btn-save">保存</button>
        <a class="btn" href="${U.href('initialPolicy')}">取消</a>
      </div>`,
    onMount() {
      renderList();

      document.getElementById('ip-add-btn')?.addEventListener('click', () => {
        if (usedCodes().size >= catalog.length) {
          U.toast('已添加全部策略类型', 'info');
          return;
        }
        openConfigModal({});
      });

      document.getElementById('btn-save')?.addEventListener('click', async () => {
        const name = (document.getElementById('f-name').value || '').trim();
        if (!name) {
          U.toast('请填写策略名称', 'error');
          return;
        }
        // 是否默认仅在列表卡片「设为默认」操作；表单不再勾选
        const payload = {
          name,
          description: (document.getElementById('f-desc').value || '').trim(),
          items: draftItems.map((it, i) => ({
            policy_code: it.policy_code,
            param: it.param || {},
            sort: i + 1
          }))
        };
        if (!isEdit) payload.is_default = false;
        try {
          if (isEdit) {
            await MDMApi.updateInitialPolicy(policyId, payload);
            U.toast('已保存');
            location.href = U.href('initialPolicy');
          } else {
            const created = await MDMApi.createInitialPolicy(payload);
            U.toast('已创建');
            location.href = U.href('initialPolicyForm', { id: created.id });
          }
        } catch (e) {
          U.toast(e.message || '保存失败', 'error');
        }
      });
    }
  });
})();
