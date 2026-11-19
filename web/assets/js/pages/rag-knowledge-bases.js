(async function () {
  const U = MDMUtils;

  let items = [];
  let loadError = '';
  let keyword = '';

  async function loadList() {
    try {
      items = (await MDMApi.listRagKnowledgeBases({ keyword })) || [];
      loadError = '';
    } catch (e) {
      items = [];
      loadError = e.message || '加载失败';
    }
  }

  function esc(s) {
    return U.escapeHtml ? U.escapeHtml(s) : String(s || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  }

  const KB_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/><path d="M8 7h8M8 11h6"/></svg>';

  function listHtml() {
    if (loadError) {
      return `<div class="panel"><div class="panel-body text-muted">${esc(loadError)}</div></div>`;
    }
    if (!items.length) {
      return `<div class="panel"><div class="panel-body text-muted">暂无知识库。可按制度类别新建分组（如人事制度、安全规范）；问答时可跨全部分组检索。</div></div>`;
    }
    return `<div class="kb-grid">
      ${items.map(kb => `
        <div class="kb-card">
          <div class="kb-card-head">
            <div class="kb-card-icon" aria-hidden="true">${KB_ICON}</div>
            <div style="min-width:0">
              <div class="kb-card-title">${esc(kb.name)}</div>
              <div class="kb-card-desc">${esc(kb.description || '暂无说明')}</div>
            </div>
          </div>
          <div class="kb-card-meta">
            <span class="kb-count">${kb.file_count || 0} 个文件</span>
          </div>
          <div class="kb-card-actions">
            <a class="btn btn-sm btn-primary" href="${U.href('ragKnowledgeBaseDetail', { id: kb.id })}">管理文件</a>
            <button type="button" class="btn btn-sm btn-edit-kb" data-id="${esc(kb.id)}">编辑</button>
            <button type="button" class="btn btn-sm btn-link btn-text-danger btn-del-kb" data-id="${esc(kb.id)}" data-name="${esc(kb.name)}">删除</button>
          </div>
        </div>`).join('')}
    </div>`;
  }

  function openKbModal(existing) {
    const isEdit = !!(existing && existing.id);
    U.modal({
      title: isEdit ? '编辑知识库' : '新建知识库',
      size: 'md',
      okText: isEdit ? '保存' : '创建',
      body: `
        <div class="form-item" style="margin-bottom:16px">
          <label class="form-label" for="kb-name">名称 <span style="color:var(--error)">*</span></label>
          <input id="kb-name" class="form-input" maxlength="128" value="${esc(existing && existing.name || '')}" placeholder="如：人事制度" autocomplete="off">
        </div>
        <div class="form-item" style="margin-bottom:0">
          <label class="form-label" for="kb-desc">说明</label>
          <textarea id="kb-desc" class="form-textarea" rows="4" maxlength="2000" placeholder="可选，简要说明本库用途" style="font-family:inherit;font-size:13px;line-height:1.5">${esc(existing && existing.description || '')}</textarea>
        </div>
        <p id="kb-err" style="display:none;margin:12px 0 0;font-size:12px;line-height:1.5;color:var(--error)"></p>`,
      onOk: async () => {
        const nameEl = document.getElementById('kb-name');
        const descEl = document.getElementById('kb-desc');
        const err = document.getElementById('kb-err');
        const name = (nameEl && nameEl.value || '').trim();
        const description = (descEl && descEl.value || '').trim();
        if (err) {
          err.style.display = 'none';
          err.textContent = '';
        }
        if (!name) {
          if (err) {
            err.textContent = '请填写名称';
            err.style.display = 'block';
          }
          if (nameEl) nameEl.focus();
          return false;
        }
        try {
          if (isEdit) {
            await MDMApi.updateRagKnowledgeBase(existing.id, { name, description });
            U.toast('已保存');
          } else {
            await MDMApi.createRagKnowledgeBase({ name, description });
            U.toast('已创建');
          }
          await refresh();
          return true;
        } catch (e) {
          if (err) {
            err.textContent = e.message || '保存失败';
            err.style.display = 'block';
          }
          return false;
        }
      }
    });
    setTimeout(() => {
      const nameEl = document.getElementById('kb-name');
      if (nameEl) {
        nameEl.focus();
        nameEl.select();
      }
    }, 0);
  }

  async function refresh() {
    await loadList();
    const el = document.getElementById('kb-list');
    if (el) el.innerHTML = listHtml();
    bind();
  }

  function bind() {
    document.querySelectorAll('.btn-edit-kb').forEach(btn => {
      btn.onclick = () => {
        const kb = items.find(x => String(x.id) === String(btn.dataset.id));
        if (kb) openKbModal(kb);
      };
    });
    document.querySelectorAll('.btn-del-kb').forEach(btn => {
      btn.onclick = () => {
        U.confirm(`确认删除知识库「${btn.dataset.name}」？将同时删除库内文件与向量。`, async () => {
          U.showBusy('正在删除知识库及向量数据，请稍候…');
          try {
            await MDMApi.deleteRagKnowledgeBase(btn.dataset.id);
            U.toast('已删除');
            await refresh();
          } catch (e) {
            U.toast(e.message || '删除失败', 'error');
          } finally {
            U.hideBusy();
          }
        });
      };
    });
  }

  await loadList();

  MDMLayout.mount({
    pageId: 'knowledge-bases',
    moduleId: 'rag',
    title: '知识库问答',
    content: `
      <div class="panel kb-toolbar" style="margin-bottom:14px">
        <div class="toolbar">
          <div class="toolbar-left">
            <div class="search-box"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/></svg>
              <input id="kb-search" placeholder="搜索知识库名称、说明..."></div>
          </div>
          <div class="toolbar-right">
            <a class="btn" href="${U.href('ragAsk')}">制度问答</a>
            <button type="button" class="btn btn-primary" id="btn-new-kb">+ 新建知识库</button>
          </div>
        </div>
      </div>
      <div id="kb-list">${listHtml()}</div>`,
    onMount() {
      bind();
      document.getElementById('btn-new-kb').onclick = () => openKbModal(null);
      const input = document.getElementById('kb-search');
      let timer = null;
      input.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => {
          keyword = input.value.trim();
          refresh();
        }, 250);
      });
    }
  });
})();
