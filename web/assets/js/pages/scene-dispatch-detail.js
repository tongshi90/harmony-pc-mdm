(async function () {
  const U = MDMUtils;
  const taskId = U.query('id');
  if (!taskId) {
    U.toast('缺少任务 ID', 'error');
    location.href = U.href('sceneDispatch');
    return;
  }

  let task = null;

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

  function cmdName(code) {
    const cmd = cmdOf(code);
    return cmd ? cmd.name : (U.normalizePolicyCode(code) || code);
  }

  function itemSummary(item) {
    return U.displayPolicyItemSummary(item);
  }

  function deadlineText() {
    if (task.policy_level === 'urgent' && !task.deadline) return '立刻执行';
    const parts = [];
    if (task.wait_hours != null && Number(task.wait_hours) > 0) {
      parts.push(`${escapeHtml(String(task.wait_hours))} 小时`);
    }
    if (task.deadline) parts.push(escapeHtml(task.deadline));
    return parts.length ? parts.join(' · ') : '—';
  }

  function targetTypeLabel() {
    const groups = task.group_ids || task.target_ids || [];
    return groups.length ? '按成员分组（含子组）' : '手动选择人员';
  }

  function ensureViewModal() {
    let mask = document.getElementById('pd-view-mask');
    if (mask) return mask;
    mask = document.createElement('div');
    mask.id = 'pd-view-mask';
    mask.className = 'modal-mask';
    mask.innerHTML = `<div class="modal modal-xl ip-item-config-modal">
      <div class="modal-header" id="pd-view-title">策略详情</div>
      <div class="modal-body" id="pd-view-body"></div>
      <div class="modal-footer">
        <button type="button" class="btn" id="pd-view-close">关闭</button>
      </div>
    </div>`;
    document.body.appendChild(mask);
    document.getElementById('pd-view-close').onclick = () => mask.classList.remove('show');
    return mask;
  }

  function openItemView(index) {
    const items = task.items || [];
    const it = items[index];
    if (!it) return;
    const mask = ensureViewModal();
    const cmd = cmdOf(it.policy_code);
    const title = cmd ? cmd.name : (it.policy_code || '策略项');
    document.getElementById('pd-view-title').textContent = `查看策略 · ${title}`;
    document.getElementById('pd-view-body').innerHTML = `<div class="ip-modal-params" id="pd-view-params"></div>`;
    const box = document.getElementById('pd-view-params');
    if (!cmd) {
      box.innerHTML = `<pre class="json-preview" style="margin:0;max-height:360px;overflow:auto">${escapeHtml(JSON.stringify(it.param || {}, null, 2))}</pre>`;
    } else {
      U.mountCommandParamForm(box, cmd, it.param || {}, {
        mode: 'view',
        dense: true,
        hideHints: true
      });
    }
    mask.classList.add('show');
  }

  function renderPage() {
    const items = task.items || [];
    const devices = task.devices || [];

    return `
      <div class="panel mb-16">
        <div class="panel-header"><h3>任务信息</h3></div>
        <div class="panel-body" style="padding:0">
          <table class="kv-table"><tbody>
            <tr><th>任务名称</th><td><strong>${escapeHtml(task.name || '—')}</strong></td></tr>
            <tr><th>策略来源</th><td>${escapeHtml(task.op_type_label || task.op_type || '—')}</td></tr>
            <tr><th>最晚延迟执行时间</th><td>${deadlineText()}</td></tr>
            <tr><th>目标类型</th><td>${escapeHtml(targetTypeLabel())}</td></tr>
            <tr><th>目标范围</th><td>${escapeHtml(task.target_desc || '—')}</td></tr>
            <tr><th>目标终端数</th><td>${task.targets || devices.length || 0} 台</td></tr>
            <tr><th>创建人</th><td>${escapeHtml(task.creator || '—')}</td></tr>
            <tr><th>创建时间</th><td>${escapeHtml(task.create_time || '—')}</td></tr>
          </tbody></table>
        </div>
      </div>

      <div class="panel mb-16">
        <div class="panel-header">
          <h3>策略配置</h3>
          <span class="extra">共 ${items.length} 项 · 点击查看详情</span>
        </div>
        <div class="panel-body">
          ${items.length ? `<table class="ip-item-table">
            <thead><tr>
              <th style="width:48px">#</th>
              <th>策略</th>
              <th>摘要</th>
              <th style="width:100px;text-align:right">操作</th>
            </tr></thead>
            <tbody>${items.map((it, i) => {
              const summary = itemSummary(it);
              return `<tr data-index="${i}">
                <td>${it.sort != null ? it.sort : i + 1}</td>
                <td>${escapeHtml(cmdName(it.policy_code))}</td>
                <td><div class="ip-item-summary" title="${escapeHtml(summary)}">${escapeHtml(summary)}</div></td>
                <td><div class="row-act">
                  <button type="button" class="link-btn pd-view-item">查看</button>
                </div></td>
              </tr>`;
            }).join('')}</tbody>
          </table>` : '<p class="text-muted" style="margin:0">暂无策略项</p>'}
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h3>所选设备</h3>
          <span class="extra">共 ${devices.length} 台 · 仅记录下发目标；对齐与合规请到「设备管理」查看</span>
        </div>
        <div class="panel-body" style="padding:0">
          ${devices.length ? `<table class="data-table"><thead><tr>
            <th>终端 SN</th><th>使用人</th><th>工号</th><th>所属分组</th>
          </tr></thead><tbody>
            ${devices.map(d => `<tr>
              <td><a class="btn-link" href="${U.href('deviceDetail', { sn: d.sn })}"><code>${escapeHtml(d.sn)}</code></a></td>
              <td>${escapeHtml(d.member_name || '—')}</td>
              <td class="text-muted">${escapeHtml(d.employee_id || '—')}</td>
              <td class="text-muted" style="font-size:12px">${escapeHtml(d.department_path || '—')}</td>
            </tr>`).join('')}
          </tbody></table>` : '<div class="panel-body text-muted">无目标设备</div>'}
        </div>
      </div>`;
  }

  try {
    task = await MDMApi.getPolicyTask(taskId);
  } catch (e) {
    U.toast(e.message || '加载任务失败', 'error');
    location.href = U.href('sceneDispatch');
    return;
  }

  MDMLayout.mount({
    pageId: 'scene-dispatch-detail',
    title: '任务详情',
    actions: `<a class="btn" href="${U.href('sceneDispatch')}">返回</a>`,
    content: renderPage(),
    onMount() {
      document.querySelectorAll('.pd-view-item').forEach(btn => {
        btn.addEventListener('click', () => {
          const tr = btn.closest('tr[data-index]');
          if (!tr) return;
          openItemView(Number(tr.dataset.index));
        });
      });
    }
  });
})();
