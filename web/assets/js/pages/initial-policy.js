(async function () {
  const U = MDMUtils;

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function cmdName(code) {
    const c = U.findCommand(U.normalizePolicyCode(code));
    return (c && c.name) || U.normalizePolicyCode(code) || code;
  }

  let policies = [];
  let loadError = '';

  async function loadList() {
    try {
      const data = await MDMApi.listInitialPolicies({ page: 1, page_size: 100 });
      policies = (data && data.items) || [];
      loadError = '';
    } catch (e) {
      policies = [];
      loadError = e.message || '加载失败';
    }
  }

  function cardsHtml() {
    if (loadError) {
      return `<div class="panel"><div class="panel-body text-muted">${escapeHtml(loadError)}</div></div>`;
    }
    if (!policies.length) {
      return `<div class="panel"><div class="panel-body text-muted">暂无策略模板，请新建</div></div>`;
    }
    return `<div class="ip-card-grid">${policies.map(p => {
      const desc = String(p.description || '').trim();
      const items = Number(p.item_count) || 0;
      const updated = p.update_time || '';
      return `
      <article class="ip-card" data-id="${escapeHtml(p.id)}" tabindex="0" role="button" aria-label="查看 ${escapeHtml(p.name)}">
        <div class="ip-card-main">
          <h3 class="ip-card-title">${escapeHtml(p.name)}</h3>
          <p class="ip-card-desc${desc ? '' : ' is-empty'}">${desc ? escapeHtml(desc) : '暂无说明'}</p>
        </div>
        <div class="ip-card-meta">
          <span class="ip-card-stat"><strong>${items}</strong> 项策略</span>
          ${updated ? `<span class="ip-card-time">更新于 ${escapeHtml(updated)}</span>` : ''}
        </div>
        <div class="ip-card-actions">
          <div class="ip-card-actions-main">
            <a class="btn btn-sm btn-primary" href="${U.href('initialPolicyForm', { id: p.id })}">编辑</a>
          </div>
          <div class="ip-card-actions-more">
            <button class="btn btn-sm btn-link btn-text-danger btn-del-policy" type="button" data-id="${escapeHtml(p.id)}" data-name="${escapeHtml(p.name)}">删除</button>
          </div>
        </div>
      </article>`;
    }).join('')}</div>`;
  }


  async function openViewModal(id) {
    let detail;
    try {
      detail = await MDMApi.getInitialPolicy(id);
    } catch (e) {
      U.toast(e.message || '加载失败', 'error');
      return;
    }
    const items = detail.items || [];
    const mask = document.getElementById('ip-modal-mask') || (() => {
      const el = document.createElement('div');
      el.id = 'ip-modal-mask';
      el.className = 'modal-mask';
      el.innerHTML = `<div class="modal modal-xl" id="ip-modal">
        <div class="modal-header" id="ip-modal-title"></div>
        <div class="modal-body" id="ip-modal-body"></div>
        <div class="modal-footer" id="ip-modal-footer"></div>
      </div>`;
      document.body.appendChild(el);
      return el;
    })();
    document.getElementById('ip-modal-title').textContent =
      detail.is_default ? `${detail.name}（默认策略）` : detail.name;
    document.getElementById('ip-modal-body').innerHTML = `
      <div class="detail-meta" style="margin-bottom:12px;display:flex;flex-wrap:wrap;gap:10px;font-size:12px">
        <span><code>${escapeHtml(detail.id)}</code></span>
        ${detail.is_default ? '<span class="badge badge-initial">全局默认</span>' : '<span class="tag tag-blue">策略模板</span>'}
        <span>更新 ${escapeHtml(detail.update_time || '—')}</span>
      </div>
      <p style="margin:0 0 14px;color:var(--text)">${escapeHtml(detail.description || '—')}</p>
      <div class="form-section-title" style="margin-top:0">策略项（${items.length}）· 按配置顺序</div>
      <table class="data-table"><thead><tr><th>#</th><th>策略</th><th>摘要</th></tr></thead>
      <tbody>${items.map((it, i) => {
        const summary = U.displayPolicyItemSummary(it);
        return `<tr>
        <td>${it.sort != null ? it.sort : i + 1}</td>
        <td>${escapeHtml(cmdName(it.policy_code))}</td>
        <td><div class="ip-item-summary" title="${escapeHtml(summary)}">${escapeHtml(summary)}</div></td>
      </tr>`;
      }).join('') || '<tr><td colspan="3" class="text-muted">暂无策略项</td></tr>'}</tbody></table>
      <p class="param-hint" style="margin-top:12px">分组与模板的绑定请在「成员分组」中设置。</p>`;
    document.getElementById('ip-modal-footer').innerHTML = `
      <button class="btn" id="ip-modal-close">关闭</button>
      <a class="btn btn-primary" href="${U.href('initialPolicyForm', { id: detail.id })}">编辑</a>`;
    mask.classList.add('show');
    document.getElementById('ip-modal-close').onclick = () => mask.classList.remove('show');
  }

  await loadList();

  MDMLayout.mount({
    pageId: 'initial-policy',
    title: '初始策略',
    breadcrumb: `<a href="${U.href('deviceGroups')}">成员分组</a> / 初始策略`,
    content: `
      <div class="toolbar" style="margin-bottom:12px">
        <div class="toolbar-left">
          <span class="text-muted" style="font-size:13px">维护可复用的初始策略模板；分组侧绑定请在「成员分组」中完成</span>
        </div>
        <div class="toolbar-right">
          <a class="btn btn-primary" href="${U.href('initialPolicyForm')}">+ 新建策略模板</a>
        </div>
      </div>
      <div id="policy-card-grid">${cardsHtml()}</div>`,
    onMount() {
      const grid = document.getElementById('policy-card-grid');

      grid?.querySelectorAll('.ip-card').forEach(card => {
        const open = () => openViewModal(card.dataset.id);
        card.addEventListener('click', e => {
          if (e.target.closest('a,button')) return;
          open();
        });
        card.addEventListener('keydown', e => {
          if (e.target.closest('a,button')) return;
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            open();
          }
        });
      });

      grid?.querySelectorAll('.btn-set-default').forEach(btn => {
        btn.addEventListener('click', async e => {
          e.stopPropagation();
          try {
            await MDMApi.setDefaultInitialPolicy(btn.dataset.id);
            U.toast('已设为默认策略');
            location.reload();
          } catch (err) {
            U.toast(err.message || '设置失败', 'error');
          }
        });
      });

      grid?.querySelectorAll('.btn-del-policy').forEach(btn => {
        btn.addEventListener('click', e => {
          e.stopPropagation();
          U.confirm('确认删除该策略模板？', async () => {
            try {
              await MDMApi.deleteInitialPolicy(btn.dataset.id);
              U.toast('已删除');
              location.reload();
            } catch (err) {
              U.toast(err.message || '删除失败', 'error');
            }
          });
        });
      });

      const preId = U.query('id');
      if (preId) setTimeout(() => openViewModal(preId), 50);
    }
  });
})();
