async function renderApps() {
  const U = MDMUtils;
  let apps = [];
  let total = 0;
  let page = 1;
  let keyword = '';
  let loadError = '';

  let pageSize = U.cardGridPageSize('default');

  const statusBadge = s => Number(s) === 1
    ? U.badgeStatus('published')
    : '<span class="badge badge-off">已下架</span>';

  async function loadApps() {
    try {
      const data = await MDMApi.listApps({ keyword, page, page_size: pageSize });
      apps = data.items || [];
      total = data.total || 0;
      page = data.page || page;
      loadError = '';
    } catch (e) {
      apps = [];
      total = 0;
      loadError = e.message || '加载失败';
    }
  }

  function cardsHtml() {
    if (loadError) return `<div class="panel"><div class="panel-body text-muted">${loadError}</div></div>`;
    if (!apps.length) return `<div class="panel"><div class="panel-body text-muted">暂无应用，请先新建应用，再在详情中上传版本安装包</div></div>`;
    return `<div class="card-grid">${apps.map(a => `
      <div class="entity-card">
        <div class="entity-card-badges">${statusBadge(a.status)}</div>
        <div class="entity-card-head">
          ${U.appIconHtml(a)}
          <div>
            <div class="entity-title entity-title-ellipsis"><a href="${U.href('appDetail', { id: a.id })}" title="${String(a.app_name || '').replace(/"/g, '&quot;')}">${a.app_name || '—'}</a></div>
            <div class="entity-sub entity-sub-ellipsis">${a.bundle_name ? String(a.bundle_name) : '未填写包名'}</div>
          </div>
        </div>
        <div class="entity-card-body">
          <div class="entity-stats">
            <span>最新版本 <strong>${a.latest_version || '—'}</strong></span>
            <span>共 <strong>${a.version_count || 0}</strong> 个版本</span>
          </div>
          ${a.description ? `<div class="entity-desc" title="${String(a.description).replace(/"/g, '&quot;')}">${a.description}</div>` : ''}
        </div>
        <div class="entity-card-foot">
          <div class="entity-card-actions-main">
            <a class="btn btn-sm btn-primary" href="${U.href('appDetail', { id: a.id })}">详情</a>
            <a class="btn btn-sm" href="${U.href('appForm', { id: a.id })}">编辑</a>
            <button type="button" class="btn btn-sm btn-toggle-app-status" data-id="${a.id}" data-status="${a.status}" data-name="${String(a.app_name || '').replace(/"/g, '&quot;')}">
              ${Number(a.status) === 1 ? '下架' : '上架'}
            </button>
          </div>
          <div class="entity-card-actions-more">
            <button type="button" class="btn btn-sm btn-link btn-text-danger btn-del-app" data-id="${a.id}" data-name="${a.app_name}">删除</button>
          </div>
        </div>
      </div>`).join('')}</div>
      <div id="app-pagination">${U.pagination(total, page, pageSize, { unit: '个', pageItems: apps.length })}</div>`;
  }

  await loadApps();

  MDMLayout.mount({
    pageId: 'apps',
    title: '我的应用',
    content: `
      <div class="toolbar">
        <div class="toolbar-left">
          <div class="search-box"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/></svg>
            <input id="app-search" placeholder="应用名称、编码..."></div>
        </div>
        <div class="toolbar-right">
          <a class="btn btn-primary" href="${U.href('appForm')}">+ 新建应用</a>
        </div>
      </div>
      <div id="app-list">${cardsHtml()}</div>`,
    onMount() {
      const listEl = document.getElementById('app-list');
      async function refresh() {
        await loadApps();
        if (listEl) listEl.innerHTML = cardsHtml();
        bind();
      }
      function bind() {
        document.querySelectorAll('.btn-toggle-app-status').forEach(btn => {
          btn.addEventListener('click', () => {
            const cur = Number(btn.dataset.status);
            const next = cur === 1 ? 0 : 1;
            const action = next === 1 ? '上架' : '下架';
            U.confirm(`确认${action}该应用？`, async () => {
              try {
                await MDMApi.updateApp(btn.dataset.id, { status: next });
                U.toast(`已${action}`);
                refresh();
              } catch (e) {
                U.toast(e.message || '操作失败', 'error');
              }
            });
          });
        });
        document.querySelectorAll('.btn-del-app').forEach(btn => {
          btn.addEventListener('click', () => {
            U.confirm('确认删除该应用？将同时删除其版本与安装包。', async () => {
              try {
                await MDMApi.deleteApp(btn.dataset.id);
                U.toast('已删除');
                refresh();
              } catch (e) {
                U.toast(e.message || '删除失败', 'error');
              }
            });
          });
        });
        document.querySelectorAll('#app-pagination .page-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            const p = Number(btn.dataset.page);
            if (!p || p === page) return;
            page = p;
            refresh();
          });
        });
      }
      bind();
      let timer = null;
      document.getElementById('app-search')?.addEventListener('input', e => {
        clearTimeout(timer);
        timer = setTimeout(() => {
          keyword = e.target.value.trim();
          page = 1;
          refresh();
        }, 300);
      });

      U.bindCardGridPageResize('default', () => pageSize, (next, prev) => {
        const first = (page - 1) * prev;
        pageSize = next;
        page = Math.floor(first / pageSize) + 1;
        refresh();
      });
    }
  });
}
renderApps();
