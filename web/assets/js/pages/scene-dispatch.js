(async function () {
  const U = MDMUtils;

  let keyword = '';
  let opType = '';
  let startDate = '';
  let endDate = '';
  let page = 1;
  const pageSize = 20;
  let loading = false;
  let lastData = { items: [], total: 0 };

  const OP_TYPE_OPTIONS = [
    { value: '', label: '全部来源' },
    { value: 'dispatch', label: '自定义策略下发' },
    { value: 'app_batch', label: '应用批量操作' },
    { value: 'initial_bind', label: '初始策略下发' }
  ];

  const CAL_ICON = `<svg class="date-picker-trigger-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/></svg>`;

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function datePickerHtml(id, placeholder) {
    return `<div class="date-picker" id="${id}">
      <button type="button" class="date-picker-trigger" aria-haspopup="dialog">
        <span class="date-picker-trigger-text is-placeholder">${escapeHtml(placeholder)}</span>
        ${CAL_ICON}
      </button>
      <input type="hidden" value="">
      <div class="date-picker-panel" hidden></div>
    </div>`;
  }

  function hasActiveFilters() {
    return !!(keyword || opType || startDate || endDate);
  }

  function emptyStateHtml() {
    const createHref = U.href('sceneDispatchCreate');
    if (hasActiveFilters()) {
      return `<div class="empty-state">
        <div class="empty-state-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
        </div>
        <p class="empty-state-title">未找到匹配的策略记录</p>
        <p class="empty-state-desc">试试调整关键词、策略来源或时间范围后再查询</p>
      </div>`;
    }
    return `<div class="empty-state">
      <div class="empty-state-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M4 12h10M4 17h7"/><path d="M17 14v6M14 17h6"/></svg>
      </div>
      <p class="empty-state-title">暂无策略记录</p>
      <p class="empty-state-desc">下发策略、批量安装/卸载或绑定初始策略后，将在此查看记录</p>
      <div class="empty-state-action">
        <a class="btn btn-primary" href="${createHref}">下发策略</a>
      </div>
    </div>`;
  }

  function syncCreateAction(showHeaderBtn) {
    const btn = document.getElementById('pd-create-btn');
    if (!btn) return;
    btn.hidden = !showHeaderBtn;
    btn.style.display = showHeaderBtn ? '' : 'none';
    const wrap = btn.closest('.head-actions');
    if (wrap) wrap.style.display = showHeaderBtn ? '' : 'none';
  }

  function renderTaskTable() {
    const items = lastData.items || [];
    const total = lastData.total || 0;
    const content = document.getElementById('pd-task-content');
    const extra = document.getElementById('pd-task-extra');
    if (!content) return;

    if (extra) {
      extra.textContent = loading ? '加载中…' : `共 ${total} 条`;
    }

    if (loading && !items.length) {
      content.innerHTML = `<div class="empty-state"><p class="empty-state-desc">加载中…</p></div>`;
      syncCreateAction(false);
      return;
    }
    if (!items.length) {
      content.innerHTML = emptyStateHtml();
      syncCreateAction(hasActiveFilters());
      return;
    }

    syncCreateAction(true);

    content.innerHTML = `
      <table class="data-table pd-task-table"><thead><tr>
        <th style="width:22%">任务</th>
        <th style="width:16%">策略来源</th>
        <th style="width:20%">最晚延迟执行时间</th>
        <th style="width:22%">目标</th>
        <th style="width:14%">创建时间</th>
        <th style="width:6%">操作</th>
      </tr></thead><tbody id="pd-task-tbody"></tbody></table>
      <div class="panel-foot" id="pd-task-pager"></div>`;

    const tbody = document.getElementById('pd-task-tbody');
    const pager = document.getElementById('pd-task-pager');
    tbody.innerHTML = items.map(t => {
      const detailHref = U.href('sceneDispatchDetail', { id: t.id });
      const name = String(t.name || '—');
      const source = String(t.op_type_label || t.op_type || '—');
      const deadline = t.deadline
        ? String(t.deadline)
        : (t.policy_level === 'urgent' ? '立刻执行' : '—');
      // target_desc 已含台数（分组/选人后端均写入），勿再拼 targets
      const target = String(t.target_desc || '').trim() || `${t.targets || 0} 台`;
      const createTime = String(t.create_time || '—');
      return `<tr>
        <td><span class="cell-ellipsis" title="${escapeHtml(name)}"><a class="btn-link" href="${detailHref}"><strong>${escapeHtml(name)}</strong></a></span></td>
        <td><span class="cell-ellipsis" title="${escapeHtml(source)}">${escapeHtml(source)}</span></td>
        <td><span class="cell-ellipsis" title="${escapeHtml(deadline)}">${escapeHtml(deadline)}</span></td>
        <td><span class="cell-ellipsis" title="${escapeHtml(target)}">${escapeHtml(target)}</span></td>
        <td><span class="cell-ellipsis text-muted" title="${escapeHtml(createTime)}">${escapeHtml(createTime)}</span></td>
        <td><div class="row-act"><a class="link-btn" href="${detailHref}">详情</a></div></td>
      </tr>`;
    }).join('');

    if (pager) {
      pager.innerHTML = `
        <span>第 ${page} 页 · 每页 ${pageSize} 条</span>
        <div id="pd-task-pagination">${U.pagination(total, page, pageSize, {
          unit: '条',
          pageItems: items.length
        })}</div>`;
      pager.querySelectorAll('.page-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const p = Number(btn.dataset.page);
          if (!p || p === page) return;
          page = p;
          loadTasks();
        });
      });
    }
  }

  function readFiltersFromDom(startPicker, endPicker) {
    keyword = (document.getElementById('pd-keyword')?.value || '').trim();
    opType = (document.getElementById('pd-op-type')?.value || '').trim();
    startDate = (startPicker && startPicker.getValue()) || '';
    endDate = (endPicker && endPicker.getValue()) || '';
  }

  async function loadTasks() {
    loading = true;
    renderTaskTable();
    try {
      lastData = await MDMApi.listPolicyTasks({
        keyword,
        op_type: opType || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        page,
        page_size: pageSize
      });
    } catch (e) {
      lastData = { items: [], total: 0 };
      U.toast(e.message || '加载失败', 'error');
    } finally {
      loading = false;
      renderTaskTable();
    }
  }

  MDMLayout.mount({
    pageId: 'scene-dispatch',
    title: '策略记录',
    actions: `<a class="btn btn-primary" id="pd-create-btn" href="${U.href('sceneDispatchCreate')}" hidden style="display:none">下发策略</a>`,
    content: `
      <section class="panel">
        <div class="toolbar pd-toolbar">
          <div class="pd-toolbar-filters">
            <label class="search">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/></svg>
              <input type="search" id="pd-keyword" placeholder="任务名称 / 目标">
            </label>
            <select class="form-select toolbar-select" id="pd-op-type" aria-label="策略来源">
              ${OP_TYPE_OPTIONS.map(o => `<option value="${escapeHtml(o.value)}">${escapeHtml(o.label)}</option>`).join('')}
            </select>
            ${datePickerHtml('pd-start-picker', '开始日期')}
            <span class="toolbar-date-sep">至</span>
            ${datePickerHtml('pd-end-picker', '结束日期')}
            <button type="button" class="btn" id="pd-reset-btn">清空</button>
            <button type="button" class="btn btn-primary" id="pd-search-btn">搜索</button>
          </div>
          <span class="extra" id="pd-task-extra">加载中…</span>
        </div>
        <div style="padding:0" id="pd-task-content"></div>
      </section>
      <p class="text-muted" style="margin-top:12px">
        下发策略完成之后，请回到 <a class="btn-link" href="${U.href('devices')}">设备管理</a> 中检查设备的更新情况
      </p>`,
    onMount() {
      const startPicker = U.bindDatePicker(document.getElementById('pd-start-picker'), {
        placeholder: '开始日期'
      });
      const endPicker = U.bindDatePicker(document.getElementById('pd-end-picker'), {
        placeholder: '结束日期'
      });

      const searchTasks = () => {
        readFiltersFromDom(startPicker, endPicker);
        if (startDate && endDate && startDate > endDate) {
          U.toast('开始日期不能晚于结束日期', 'error');
          return;
        }
        page = 1;
        loadTasks();
      };
      const resetFiltersUi = () => {
        // 仅还原表单控件，不改已加载数据、不请求接口
        const kwEl = document.getElementById('pd-keyword');
        const typeEl = document.getElementById('pd-op-type');
        if (kwEl) kwEl.value = '';
        if (typeEl) typeEl.value = '';
        startPicker?.setValue('');
        endPicker?.setValue('');
        startPicker?.close?.();
        endPicker?.close?.();
      };
      document.getElementById('pd-search-btn')?.addEventListener('click', searchTasks);
      document.getElementById('pd-reset-btn')?.addEventListener('click', e => {
        e.preventDefault();
        resetFiltersUi();
      });
      document.getElementById('pd-keyword')?.addEventListener('keydown', e => {
        if (e.key === 'Enter') searchTasks();
      });
      loadTasks();
    }
  });
})();
