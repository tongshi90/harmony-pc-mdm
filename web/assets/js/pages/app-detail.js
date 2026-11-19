(async function () {
  const U = MDMUtils;
  const appId = U.query('id');
  if (!appId) {
    location.href = U.href('apps');
    return;
  }

  let app;
  try {
    app = await MDMApi.getApp(appId);
  } catch (e) {
    U.toast(e.message || '加载失败', 'error');
    location.href = U.href('apps');
    return;
  }

  const versions = app.versions || [];
  let installData = null;
  let installPage = 1;
  const installPageSize = 20;
  let installKeyword = '';

  const esc = str => String(str == null ? '' : str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
  const verStatus = s => Number(s) === 2
    ? U.badgeStatus('published')
    : '<span class="badge badge-off">已下架</span>';
  const fmtSize = n => {
    if (n == null) return '—';
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / 1024 / 1024).toFixed(2) + ' MB';
  };
  const deviceStatusBadge = row => {
    const s = Number(row.device_status);
    if (s === 1) return U.badgeStatus('online');
    if (s === 3) return '<span class="badge badge-fail">已挂失</span>';
    return U.badgeStatus('offline');
  };

  async function loadInstalls() {
    try {
      installData = await MDMApi.listAppInstalls(app.id, {
        keyword: installKeyword,
        page: installPage,
        page_size: installPageSize
      });
    } catch (e) {
      installData = { summary: null, items: [], total: 0, error: e.message || '加载失败' };
    }
  }

  function versionsBlockHtml() {
    return `
      <div class="form-section-title" style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">
        <span>应用版本</span>
        <a class="btn btn-sm btn-primary" href="${U.href('appVersionForm', { appId: app.id })}">+ 新建版本</a>
      </div>
      <div class="card-grid">${versions.map(v => `
        <div class="entity-card version-card">
          <div class="entity-card-badges">${verStatus(v.status)}</div>
          <div class="entity-card-head entity-card-head--vcenter">
            <div>
              <div class="entity-title entity-title-ellipsis" title="${esc(v.version_name || '')}">${esc(v.version_name || '—')}</div>
              <div class="entity-sub">版本号 ${esc(v.version_code || '—')}</div>
            </div>
          </div>
          <div class="entity-card-body">
            <div class="entity-stats">
              <span>安装包 <strong>${v.has_package ? (esc(v.file_name || '已上传') + (v.file_size != null ? ` · ${fmtSize(v.file_size)}` : '')) : '未上传'}</strong></span>
            </div>
          </div>
          <div class="entity-card-foot">
            <div class="entity-card-actions-main">
              <a class="btn btn-sm btn-primary" href="${U.href('appVersionForm', { appId: app.id, versionId: v.id })}">编辑</a>
              <button type="button" class="btn btn-sm btn-toggle-ver-status"
                data-id="${v.id}" data-status="${v.status}" data-name="${esc(v.version_name || '')}">
                ${Number(v.status) === 2 ? '下架' : '发布'}
              </button>
            </div>
            <div class="entity-card-actions-more">
              ${Number(v.status) === 3
                ? `<button class="btn btn-sm btn-link btn-text-danger btn-del-ver" data-id="${v.id}" data-name="${esc(v.version_name || '')}">删除</button>`
                : `<button class="btn btn-sm btn-link" type="button" disabled title="请先下架后再删除">删除</button>`}
            </div>
          </div>
        </div>`).join('') || '<div class="text-muted">暂无版本，请新建</div>'}
      </div>`;
  }

  function installsPanelHtml() {
    const sum = (installData && installData.summary) || {
      device_total: 0, installed_count: 0, not_installed_count: 0, install_rate: 0
    };
    const items = (installData && installData.items) || [];
    const total = (installData && installData.total) || 0;
    const err = installData && installData.error;
    return `
      <div class="toolbar">
        <div class="toolbar-left">
          <div class="search-box"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/></svg>
            <input id="install-search" placeholder="搜索设备 SN、名称..." value="${installKeyword.replace(/"/g, '&quot;')}"></div>
        </div>
        <div class="toolbar-right" style="display:flex;gap:8px">
          <button class="btn btn-primary" type="button" id="btn-batch-install">批量安装</button>
          <button class="btn" type="button" id="btn-batch-uninstall">批量卸载</button>
        </div>
      </div>
      <div class="stat-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:16px">
        <div class="stat-card"><div class="label">设备总数</div><div class="value">${U.fmt(sum.device_total)}</div></div>
        <div class="stat-card accent-green"><div class="label">已安装</div><div class="value">${U.fmt(sum.installed_count)}</div>
          <div class="sub">覆盖率 ${sum.install_rate || 0}%</div></div>
        <div class="stat-card accent-gray"><div class="label">未安装</div><div class="value">${U.fmt(sum.not_installed_count)}</div></div>
      </div>
      ${err ? `<div class="panel"><div class="panel-body text-muted">${err}</div></div>` : `
      <div class="panel"><div class="panel-body" style="padding:0;overflow:auto">
        <table class="data-table">
          <thead>
            <tr>
              <th>设备 SN</th>
              <th>设备名称</th>
              <th>主机名</th>
              <th>状态</th>
              <th>安装版本</th>
              <th>安装方式</th>
              <th>安装时间</th>
            </tr>
          </thead>
          <tbody>
            ${items.length ? items.map(row => `
              <tr>
                <td><a class="btn-link" href="${U.href('deviceDetail', { sn: row.device_sn })}"><code>${row.device_sn || '—'}</code></a></td>
                <td>${row.device_name || '—'}</td>
                <td>${row.hostname || '—'}</td>
                <td>${deviceStatusBadge(row)}</td>
                <td><strong>${row.version_name || '—'}</strong>${row.version_code ? ` <code>${row.version_code}</code>` : ''}</td>
                <td>${row.install_type_label || '—'}</td>
                <td>${row.install_time || '—'}</td>
              </tr>`).join('') : `<tr><td colspan="7" class="text-muted" style="text-align:center;padding:24px">暂无安装记录</td></tr>`}
          </tbody>
        </table>
      </div></div>
      <div id="install-pagination">${U.pagination(total, installPage, installPageSize, { unit: '台', pageItems: items.length })}</div>`}
    `;
  }

  await loadInstalls();

  MDMLayout.mount({
    pageId: 'app-detail',
    title: '应用管理',
    content: `
      <div class="detail-header">
        <div style="display:flex;align-items:center;gap:14px;min-width:0">
          ${U.appIconHtml(app, { size: 56, className: 'app-icon app-icon-lg' })}
          <div style="min-width:0">
            <div class="detail-title">${esc(app.app_name)}</div>
            <div class="detail-meta">
              <span><code>${esc(app.app_code)}</code></span>
              <span>${Number(app.status) === 1 ? U.badgeStatus('published') : '<span class="badge badge-off">已下架</span>'}</span>
              ${app.update_time ? `<span>更新于 ${esc(app.update_time)}</span>` : ''}
            </div>
          </div>
        </div>
        <div class="detail-actions">
          <a class="btn" href="${U.href('apps')}">返回</a>
        </div>
      </div>
      <div id="tabs-wrap">
        <div class="tabs">
          <div class="tab-item active" data-tab="basic">基本信息</div>
          <div class="tab-item" data-tab="installs">安装情况</div>
        </div>
        <div class="tab-panel active" data-panel="basic">
          <div class="panel"><div class="panel-body">
            <table class="kv-table" style="margin-bottom:16px"><tbody>
              <tr><th>应用图标</th><td>${U.appIconHtml(app, { size: 40, className: 'app-icon app-icon-sm' })}</td></tr>
              <tr><th>应用名称</th><td>${esc(app.app_name || '—')}</td></tr>
              <tr><th>应用编码</th><td><code>${esc(app.app_code || '—')}</code></td></tr>
              <tr><th>App ID</th><td><code>${esc(app.app_id || '—')}</code></td></tr>
              <tr><th>Bundle Name</th><td><code>${esc(app.bundle_name || '—')}</code></td></tr>
              <tr><th>状态</th><td>${Number(app.status) === 1 ? U.badgeStatus('published') : '<span class="badge badge-off">已下架</span>'}</td></tr>
              <tr><th>描述</th><td style="white-space:pre-wrap">${esc(app.description || '—')}</td></tr>
              ${app.update_time ? `<tr><th>更新时间</th><td>${esc(app.update_time)}</td></tr>` : ''}
            </tbody></table>
            ${versionsBlockHtml()}
          </div></div>
        </div>
        <div class="tab-panel" data-panel="installs">
          <div id="installs-wrap">${installsPanelHtml()}</div>
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

      document.querySelectorAll('.btn-toggle-ver-status').forEach(btn => {
        btn.addEventListener('click', () => {
          if (btn.disabled) return;
          const cur = Number(btn.dataset.status);
          const next = cur === 2 ? 3 : 2;
          const action = next === 2 ? '发布' : '下架';
          U.confirm(`确认${action}该版本？`, async () => {
            try {
              await MDMApi.updateAppVersion(app.id, btn.dataset.id, { status: next });
              U.toast(`已${action}`);
              location.reload();
            } catch (e) {
              U.toast(e.message || '操作失败', 'error');
            }
          });
        });
      });

      document.querySelectorAll('.btn-del-ver').forEach(btn => {
        btn.addEventListener('click', () => {
          U.confirm('确认删除该版本？', async () => {
            try {
              await MDMApi.deleteAppVersion(app.id, btn.dataset.id);
              U.toast('已删除');
              location.reload();
            } catch (e) {
              U.toast(e.message || '删除失败', 'error');
            }
          });
        });
      });

      const installsWrap = document.getElementById('installs-wrap');
      let searchTimer = null;

      async function refreshInstalls() {
        await loadInstalls();
        if (installsWrap) installsWrap.innerHTML = installsPanelHtml();
        bindInstalls();
      }

      let groupsCache = null;
      async function loadGroups() {
        if (groupsCache) return groupsCache;
        const data = await MDMApi.listAppTargetGroups();
        groupsCache = Array.isArray(data) ? data : (data.items || []);
        return groupsCache;
      }

      function buildGroupTree(groups) {
        const byParent = {};
        groups.forEach(g => {
          const pid = g.parent_id || '';
          if (!byParent[pid]) byParent[pid] = [];
          byParent[pid].push(g);
        });
        function walk(pid, depth) {
          return (byParent[pid] || []).map(g => ({
            ...g,
            depth,
            children: walk(g.id, depth + 1)
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

      function versionHasPackage(v) {
        return !!(v && (v.has_package || v.download_url || v.file_name || v.file_path));
      }

      function publishedVersions() {
        return (versions || []).filter(v => Number(v.status) === 2);
      }

      /** 与后端 _version_key 一致：拆成数字元组便于比较 */
      function versionKey(value) {
        const text = String(value || '').trim();
        if (!text) return [0];
        if (/^\d+$/.test(text)) return [Number(text)];
        const parts = [];
        let buf = '';
        for (const ch of text) {
          if (/\d/.test(ch)) buf += ch;
          else if (buf) {
            parts.push(Number(buf));
            buf = '';
          }
        }
        if (buf) parts.push(Number(buf));
        return parts.length ? parts : [0, text];
      }

      function cmpVersionKey(a, b) {
        const n = Math.max(a.length, b.length);
        for (let i = 0; i < n; i++) {
          const x = a[i] ?? 0;
          const y = b[i] ?? 0;
          if (typeof x === 'number' && typeof y === 'number') {
            if (x !== y) return x < y ? -1 : 1;
          } else {
            const sx = String(x);
            const sy = String(y);
            if (sx !== sy) return sx < sy ? -1 : 1;
          }
        }
        return 0;
      }

      /** 已发布版本中取版本号最高者（优先 version_code，其次 version_name） */
      function pickLatestPublished() {
        const pubs = publishedVersions();
        if (!pubs.length) return null;
        return pubs.reduce((best, cur) => {
          const bc = versionKey(best.version_code);
          const cc = versionKey(cur.version_code);
          let c = cmpVersionKey(bc, cc);
          if (c !== 0) return c < 0 ? cur : best;
          const bn = versionKey(best.version_name);
          const cn = versionKey(cur.version_name);
          c = cmpVersionKey(bn, cn);
          if (c !== 0) return c < 0 ? cur : best;
          return String(cur.id) > String(best.id) ? cur : best;
        });
      }

      function escapeHtml(str) {
        return String(str || '')
          .replace(/&/g, '&amp;')
          .replace(/"/g, '&quot;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;');
      }

      function collectDescendantIds(node, acc) {
        const out = acc || [];
        (node.children || []).forEach(c => {
          out.push(String(c.id));
          collectDescendantIds(c, out);
        });
        return out;
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
            const descIds = hasChildren ? collectDescendantIds(n) : [];
            const descChecked = descIds.filter(x => selectedSet.has(x)).length;
            const indeterminate = !checked && descChecked > 0 && descChecked < descIds.length;
            const toggle = hasChildren
              ? `<button type="button" class="batch-group-toggle${expanded ? ' is-open' : ''}" data-toggle-id="${escapeHtml(id)}" aria-label="${expanded ? '收起' : '展开'}"></button>`
              : '<span class="batch-group-toggle is-leaf" aria-hidden="true"></span>';
            rows.push(`<div class="batch-group-option${checked ? ' is-checked' : ''}" style="--d:${depth}">
              ${toggle}
              <label class="batch-group-option-label">
                <input type="checkbox" class="batch-group-cb" value="${escapeHtml(id)}"${checked ? ' checked' : ''}${indeterminate ? ' data-indeterminate="1"' : ''}>
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

      function openBatchModal(mode) {
        const isInstall = mode === 'install';
        let latestPublished = null;
        if (isInstall) {
          latestPublished = pickLatestPublished();
          if (!latestPublished) {
            U.toast('没有已发布版本，请先在应用版本中发布', 'error');
            return;
          }
          if (!versionHasPackage(latestPublished)) {
            U.toast('最高已发布版本未上传安装包（.hap），请先上传后再批量安装', 'error');
            return;
          }
        }
        if (!app.app_id || !app.bundle_name) {
          U.toast('请先完善应用的 App ID 与 Bundle Name', 'error');
          return;
        }

        loadGroups().then(groups => {
          const tree = buildGroupTree(groups);
          const flat = flattenTree(tree);
          const nodeMap = Object.fromEntries(flat.map(n => [String(n.id), n]));
          let selected = new Set();
          const expandedIds = new Set(
            tree.filter(n => n.children && n.children.length).map(n => String(n.id))
          );

          U.modal({
            title: isInstall ? '批量安装' : '批量卸载',
            okText: isInstall ? '确认安装' : '确认卸载',
            size: 'sm',
            body: `
              <div class="form-item" style="margin-bottom:0">
                <div class="batch-group-picker is-open" id="batch-group-picker">
                  <div class="batch-group-head">
                    <span class="batch-group-head-label">目标分组</span>
                    <span class="batch-group-head-status is-empty" id="batch-group-summary">未选择</span>
                  </div>
                  <div class="batch-group-panel" id="batch-group-panel">
                    <div class="batch-group-tools">
                      <label class="batch-group-all">
                        <input type="checkbox" id="batch-all-groups">
                        <span>全选</span>
                      </label>
                      <button type="button" class="btn-link" id="batch-clear-groups">清空</button>
                    </div>
                    <div class="batch-group-options" id="batch-group-list"></div>
                  </div>
                </div>
              </div>`,
            onOk: async () => {
              const groupIds = Array.from(selected);
              if (!groupIds.length) {
                U.toast('请至少选择一个成员分组', 'error');
                return false;
              }
              const payload = {
                all_groups: false,
                group_ids: groupIds
              };
              if (isInstall) {
                if (!latestPublished || !versionHasPackage(latestPublished)) {
                  U.toast('没有可安装的已发布版本', 'error');
                  return false;
                }
                payload.version_id = String(latestPublished.id);
                payload.public_base_url = location.origin;
              }
              try {
                const result = isInstall
                  ? await MDMApi.batchInstallApp(app.id, payload)
                  : await MDMApi.batchUninstallApp(app.id, payload);
                U.toast(
                  (result && result.message) ||
                    `${isInstall ? '批量安装' : '批量卸载'}任务已创建，正在后台下发，请稍后查看执行结果`,
                  'success'
                );
                return true;
              } catch (e) {
                U.toast(e.message || '操作失败', 'error');
                return false;
              }
            }
          });

          const listEl = document.getElementById('batch-group-list');
          const summaryEl = document.getElementById('batch-group-summary');
          const allCb = document.getElementById('batch-all-groups');
          const clearBtn = document.getElementById('batch-clear-groups');

          function subtreeIds(id) {
            const node = nodeMap[id];
            if (!node) return [id];
            return [id, ...collectDescendantIds(node)];
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

          function syncSummary() {
            if (!summaryEl) return;
            const n = selected.size;
            if (!n) {
              summaryEl.textContent = '未选择';
              summaryEl.classList.add('is-empty');
            } else if (n === flat.length && flat.length) {
              summaryEl.textContent = `已选全部 ${n} 个`;
              summaryEl.classList.remove('is-empty');
            } else {
              summaryEl.textContent = `已选 ${n} 个`;
              summaryEl.classList.remove('is-empty');
            }
            syncAllCheckbox();
          }

          function applyIndeterminate() {
            listEl?.querySelectorAll('.batch-group-cb').forEach(cb => {
              cb.indeterminate = cb.dataset.indeterminate === '1';
            });
          }

          function rerenderList() {
            if (listEl) listEl.innerHTML = renderGroupTreeRows(tree, selected, expandedIds);
            bindListEvents();
            applyIndeterminate();
            syncSummary();
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
            listEl?.querySelectorAll('.batch-group-cb').forEach(cb => {
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

          allCb?.addEventListener('change', () => {
            if (allCb.checked) {
              selected = new Set(flat.map(g => String(g.id)));
            } else {
              selected = new Set();
            }
            rerenderList();
          });

          clearBtn?.addEventListener('click', e => {
            e.preventDefault();
            selected = new Set();
            rerenderList();
          });

          rerenderList();
        }).catch(e => {
          U.toast(e.message || '加载分组失败', 'error');
        });
      }

            function bindInstalls() {
        document.getElementById('btn-batch-install')?.addEventListener('click', () => {
          openBatchModal('install');
        });
        document.getElementById('btn-batch-uninstall')?.addEventListener('click', () => {
          openBatchModal('uninstall');
        });
        const search = document.getElementById('install-search');
        search?.addEventListener('input', () => {
          clearTimeout(searchTimer);
          searchTimer = setTimeout(() => {
            installKeyword = search.value.trim();
            installPage = 1;
            refreshInstalls();
          }, 300);
        });
        installsWrap?.querySelectorAll('[data-page]').forEach(btn => {
          btn.addEventListener('click', () => {
            const p = Number(btn.dataset.page);
            if (!p || p === installPage) return;
            installPage = p;
            refreshInstalls();
          });
        });
      }

      bindInstalls();
    }
  });
})();
