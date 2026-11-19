(async function () {
  const U = MDMUtils;
  const kbId = U.query('id');
  if (!kbId) {
    location.href = U.href('ragKnowledgeBases');
    return;
  }

  let kb = null;
  let files = [];
  let total = 0;
  let page = 1;
  const pageSize = 20;
  let loadError = '';
  let pollTimer = null;
  /** 轮询时用于发现「解析中 → 失败」并 toast 原因 */
  let knownFailedIds = new Set();
  let failWatchReady = false;
  /** 来自提问页 sources：?file_id=&open_chunks=1 */
  const focusFileId = U.query('file_id') || '';
  const autoOpenChunks = U.query('open_chunks') === '1';
  let didAutoOpenChunks = false;

  function esc(s) {
    return String(s || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  }

  function statusBadge(st) {
    if (st === 'completed') return U.badgeStatus('completed');
    if (st === 'failed') return U.badgeStatus('failed');
    if (st === 'parsing') return '<span class="tag tag-blue">解析中</span>';
    return `<span class="badge badge-off">${esc(st)}</span>`;
  }

  function failReasonShort(msg, maxLen) {
    const t = String(msg || '').trim().replace(/\s+/g, ' ');
    const n = maxLen || 72;
    if (!t) return '解析失败，暂无详细原因';
    return t.length > n ? `${t.slice(0, n)}…` : t;
  }

  function openFailReason(fileName, message) {
    const mask = document.createElement('div');
    mask.className = 'modal-mask show';
    mask.innerHTML = `
      <div class="modal" style="max-width:560px">
        <div class="modal-header">入库失败原因</div>
        <div class="modal-body">
          <p style="margin:0 0 10px"><strong>${esc(fileName || '文件')}</strong></p>
          <div style="white-space:pre-wrap;line-height:1.6;color:var(--error);font-size:13px">${esc(message || '解析失败，暂无详细原因')}</div>
          <p class="text-muted" style="margin:14px 0 0;font-size:12px">可删除后按提示修正文件再上传；若仍失败请联系管理员查看服务日志。</p>
        </div>
        <div class="modal-footer"><button type="button" class="btn btn-primary" id="fail-close">知道了</button></div>
      </div>`;
    document.body.appendChild(mask);
    const close = () => mask.remove();
    mask.querySelector('#fail-close').onclick = close;
    mask.addEventListener('click', e => { if (e.target === mask) close(); });
  }

  async function loadAll() {
    try {
      kb = await MDMApi.getRagKnowledgeBase(kbId);
      const data = await MDMApi.listRagFiles(kbId, { page, page_size: pageSize });
      files = (data && data.items) || [];
      total = (data && data.total) || 0;
      loadError = '';
    } catch (e) {
      kb = null;
      files = [];
      total = 0;
      loadError = e.message || '加载失败';
    }
  }

  function filesHtml() {
    if (loadError) {
      return `<div class="panel"><div class="panel-body text-muted">${esc(loadError)}</div></div>`;
    }
    if (!files.length) {
      return `<div class="panel"><div class="panel-body text-muted">暂无文件，请上传 PDF / Word / PPT（规章制度原稿）</div></div>`;
    }
    const failedCount = files.filter(f => f.status === 'failed').length;
    const failBanner = failedCount
      ? `<div class="panel" style="margin-bottom:12px;border-color:color-mix(in srgb, var(--error) 35%, var(--border));background:color-mix(in srgb, var(--error) 6%, var(--paper))">
          <div class="panel-body" style="padding:12px 16px;color:var(--error);font-size:13px;line-height:1.5">
            当前页有 <strong>${failedCount}</strong> 个文件入库失败。请查看状态列中的失败原因；可按提示修正后删除并重新上传。
          </div>
        </div>`
      : '';
    return `${failBanner}<div class="panel"><div class="panel-body" style="padding:0">
      <table class="data-table">
        <thead><tr>
          <th>文件名</th><th>大小</th><th style="min-width:220px">状态 / 失败原因</th><th>切片数</th><th>上传时间</th><th style="width:220px">操作</th>
        </tr></thead>
        <tbody>
          ${files.map(f => {
            const focused = focusFileId && String(f.id) === String(focusFileId);
            const failed = f.status === 'failed';
            const reason = failed ? failReasonShort(f.error_message, 80) : '';
            const rowBg = failed
              ? 'background:color-mix(in srgb, var(--error) 4%, transparent)'
              : (focused ? 'background:rgba(0,0,0,0.03)' : '');
            return `
            <tr${rowBg ? ` style="${rowBg}"` : ''} id="${focused ? 'rag-focus-file' : ''}">
              <td>${esc(f.name)}${focused ? ' <span class="tag tag-blue" style="margin-left:6px">来自问答</span>' : ''}</td>
              <td>${U.fmtFileSize(f.file_size)}</td>
              <td>
                ${statusBadge(f.status)}
                ${failed ? `<div style="margin-top:6px;font-size:12px;line-height:1.45;color:var(--error)">${esc(reason)}</div>` : ''}
              </td>
              <td>${f.chunk_count || 0}</td>
              <td>${esc(f.create_time || '—')}</td>
              <td>
                <div class="table-row-actions">
                  ${failed ? `<button type="button" class="btn btn-sm btn-fail-reason" data-id="${esc(f.id)}" data-name="${esc(f.name)}">查看原因</button>` : ''}
                  <button type="button" class="btn btn-sm btn-chunks" data-id="${esc(f.id)}" ${f.status !== 'completed' ? 'disabled' : ''}>查看切片</button>
                  <button type="button" class="btn btn-sm btn-link btn-text-danger btn-del-file" data-id="${esc(f.id)}" data-name="${esc(f.name)}">删除</button>
                </div>
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
      <div id="file-pagination" style="padding:12px 16px">${U.pagination(total, page, pageSize, { unit: '个', pageItems: files.length })}</div>
    </div></div>`;
  }

  function openEditChunkModal(fileId, chunk, onSaved) {
    const orderLabel = (chunk.order != null ? Number(chunk.order) : 0) + 1;
    const mask = document.createElement('div');
    mask.className = 'modal-mask show';
    mask.style.zIndex = '1100';
    mask.innerHTML = `
      <div class="modal" style="max-width:640px;max-height:90vh;display:flex;flex-direction:column">
        <div class="modal-header">编辑切片 #${orderLabel}</div>
        <div class="modal-body" style="overflow:auto;flex:1">
          ${Array.isArray(chunk.title_path) && chunk.title_path.length
            ? `<div class="text-muted" style="font-size:12px;margin-bottom:8px">${esc(chunk.title_path.join(' / '))}</div>` : ''}
          <textarea id="chunk-edit-text" class="form-textarea rag-chunk-edit-text" rows="14">${esc(chunk.text || '')}</textarea>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn" id="chunk-edit-cancel">取消</button>
          <button type="button" class="btn btn-primary" id="chunk-edit-save">保存并重向量</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    const close = () => mask.remove();
    mask.querySelector('#chunk-edit-cancel').onclick = close;
    mask.addEventListener('click', e => { if (e.target === mask) close(); });
    const saveBtn = mask.querySelector('#chunk-edit-save');
    saveBtn.onclick = async () => {
      const text = (mask.querySelector('#chunk-edit-text').value || '').trim();
      if (!text) {
        U.toast('切片正文不能为空', 'error');
        return;
      }
      saveBtn.disabled = true;
      U.showBusy('正在保存并重新向量化…');
      try {
        const updated = await MDMApi.updateRagFileChunk(
          kbId, fileId, chunk.chunk_id, text
        );
        U.toast('切片已更新并重新向量化');
        close();
        if (typeof onSaved === 'function') onSaved(updated || { ...chunk, text, length: text.length, manually_edited: true });
      } catch (e) {
        U.toast(e.message || '保存失败', 'error');
      } finally {
        U.hideBusy();
        saveBtn.disabled = false;
      }
    };
  }

  function renderChunkList(body, items, fileId) {
    let localItems = items.slice();
    const paint = () => {
      body.innerHTML = localItems.map((c, i) => {
        const orderLabel = (c.order != null ? c.order : i) + 1;
        const edited = c.manually_edited
          ? '<span class="tag" style="margin-left:4px">已手工修改</span>'
          : '';
        return `
        <div class="rag-chunk-card" data-chunk-id="${esc(c.chunk_id)}" style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:10px">
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:space-between;margin-bottom:6px">
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:12px;color:var(--muted)">
              <strong style="color:var(--text)">#${orderLabel}</strong>
              <span>${esc(c.type || 'text')}</span>
              ${c.page != null ? `<span>第 ${esc(c.page)} 页</span>` : ''}
              <span class="chunk-len">${esc(c.length)} 字</span>
              ${edited}
            </div>
            <button type="button" class="btn btn-sm btn-edit-chunk" data-chunk-id="${esc(c.chunk_id)}">修改</button>
          </div>
          ${Array.isArray(c.title_path) && c.title_path.length
            ? `<div class="text-muted" style="font-size:12px;margin-bottom:6px">${esc(c.title_path.join(' / '))}</div>` : ''}
          <div class="chunk-text-view" style="white-space:pre-wrap;line-height:1.55;font-size:13px">${esc(c.text || '')}</div>
        </div>`;
      }).join('');

      body.querySelectorAll('.btn-edit-chunk').forEach(btn => {
        btn.onclick = () => {
          const chunk = localItems.find(x => String(x.chunk_id) === String(btn.dataset.chunkId));
          if (!chunk) return;
          openEditChunkModal(fileId, chunk, (updated) => {
            localItems = localItems.map(x =>
              String(x.chunk_id) === String(updated.chunk_id) ? { ...x, ...updated } : x
            );
            paint();
          });
        };
      });
    };
    paint();
  }

  function openChunks(fileId, fileName) {
    const existing = document.querySelector('.rag-chunk-drawer-mask');
    if (existing) existing.remove();

    const mask = document.createElement('div');
    mask.className = 'drawer-mask rag-chunk-drawer-mask show';
    mask.innerHTML = `
      <div class="drawer-panel" role="dialog" aria-label="切片列表">
        <div class="drawer-header">
          <div style="min-width:0">
            <div>切片</div>
            <div class="text-muted" style="font-size:12px;font-weight:400;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(fileName)}</div>
          </div>
          <button type="button" class="btn btn-sm" id="chunk-close">关闭</button>
        </div>
        <div class="drawer-body" id="chunk-body">加载中…</div>
      </div>`;
    document.body.appendChild(mask);
    const close = () => mask.remove();
    mask.querySelector('#chunk-close').onclick = close;
    mask.addEventListener('click', e => { if (e.target === mask) close(); });

    MDMApi.listRagFileChunks(kbId, fileId).then(data => {
      const items = (data && data.items) || [];
      const body = mask.querySelector('#chunk-body');
      if (!items.length) {
        body.innerHTML = '<p class="text-muted">暂无切片</p>';
        return;
      }
      renderChunkList(body, items, fileId);
    }).catch(e => {
      mask.querySelector('#chunk-body').innerHTML =
        `<p style="color:var(--error)">${esc(e.message || '加载失败')}</p>`;
    });
  }

  function tryOpenFocusedChunks() {
    if (!focusFileId || !autoOpenChunks || didAutoOpenChunks) return;
    const f = files.find(x => String(x.id) === String(focusFileId));
    if (!f) return;
    const el = document.getElementById('rag-focus-file');
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
    if (f.status !== 'completed') {
      U.toast('该文件尚未入库完成，无法打开切片', 'error');
      didAutoOpenChunks = true;
      return;
    }
    didAutoOpenChunks = true;
    openChunks(f.id, f.name || f.id);
  }

  async function refresh() {
    await loadAll();
    notifyNewFailures();
    const titleEl = document.getElementById('kb-title');
    if (titleEl && kb) titleEl.textContent = kb.name || '知识库详情';
    const descEl = document.getElementById('kb-desc');
    if (descEl) {
      const desc = (kb && kb.description) || '';
      descEl.textContent = desc;
      descEl.style.display = desc ? '' : 'none';
    }
    const listEl = document.getElementById('file-list');
    if (listEl) listEl.innerHTML = filesHtml();
    bind();
    maybePoll();
    tryOpenFocusedChunks();
  }

  function maybePoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    const busy = files.some(f => f.status === 'parsing');
    if (busy) {
      pollTimer = setInterval(() => refresh(), 3000);
    }
  }

  function notifyNewFailures() {
    const failed = files.filter(f => f.status === 'failed');
    const currentIds = new Set(failed.map(f => String(f.id)));
    if (!failWatchReady) {
      knownFailedIds = currentIds;
      failWatchReady = true;
      return;
    }
    failed.forEach(f => {
      const id = String(f.id);
      if (knownFailedIds.has(id)) return;
      const tip = failReasonShort(f.error_message || `${f.name || '文件'} 入库失败`, 100);
      U.toast(`「${f.name || id}」入库失败：${tip}`, 'error');
    });
    knownFailedIds = currentIds;
  }

  function bind() {
    document.querySelectorAll('.btn-fail-reason').forEach(btn => {
      btn.onclick = () => {
        const f = files.find(x => String(x.id) === String(btn.dataset.id));
        openFailReason(
          (f && f.name) || btn.dataset.name,
          (f && f.error_message) || '解析失败，暂无详细原因'
        );
      };
    });
    document.querySelectorAll('.btn-del-file').forEach(btn => {
      btn.onclick = () => {
        U.confirm(`确认删除文件「${btn.dataset.name}」？`, async () => {
          U.showBusy('正在删除文件及向量数据，请稍候…');
          try {
            await MDMApi.deleteRagFile(kbId, btn.dataset.id);
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
    document.querySelectorAll('.btn-chunks').forEach(btn => {
      btn.onclick = () => {
        const f = files.find(x => String(x.id) === String(btn.dataset.id));
        openChunks(btn.dataset.id, f ? f.name : btn.dataset.id);
      };
    });
    const pag = document.getElementById('file-pagination');
    if (pag) {
      pag.querySelectorAll('[data-page]').forEach(btn => {
        btn.onclick = () => {
          page = Number(btn.dataset.page) || 1;
          refresh();
        };
      });
    }
  }

  await loadAll();

  MDMLayout.mount({
    pageId: 'knowledge-base-detail',
    moduleId: 'rag',
    title: '知识库详情',
    content: `
      <div class="panel kb-toolbar" style="margin-bottom:14px">
        <div class="toolbar">
          <div class="toolbar-left" style="flex-direction:column;align-items:flex-start;gap:6px;min-width:0">
            <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;min-width:0">
              <strong id="kb-title" style="font-size:16px;font-weight:700;line-height:1.3;color:var(--ink)">${esc(kb && kb.name || '…')}</strong>
              <a class="btn btn-sm" href="${U.href('ragKnowledgeBases')}">← 返回列表</a>
              <a class="btn btn-sm" href="${U.href('ragAsk', { kb_id: kbId })}">制度问答</a>
            </div>
            <div class="text-muted" id="kb-desc" style="font-size:12.5px;line-height:1.5${(kb && kb.description) ? '' : ';display:none'}">${esc((kb && kb.description) || '')}</div>
          </div>
          <div class="toolbar-right">
            <label class="btn btn-primary" style="cursor:pointer;margin:0">
              批量上传
              <input type="file" id="rag-upload" multiple accept=".pdf,.doc,.docx,.ppt,.pptx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation" hidden>
            </label>
          </div>
        </div>
      </div>
      <div id="file-list">${filesHtml()}</div>`,
    onMount() {
      bind();
      maybePoll();
      tryOpenFocusedChunks();
      const input = document.getElementById('rag-upload');
      input.addEventListener('change', async () => {
        const selected = input.files ? Array.from(input.files) : [];
        input.value = '';
        if (!selected.length) return;
        try {
          U.toast(`正在上传 ${selected.length} 个文件…`);
          await MDMApi.uploadRagFiles(kbId, selected);
          U.toast(
            selected.length > 1
              ? `已上传 ${selected.length} 个文件，将按队列依次解析向量化`
              : '已上传，正在解析向量化'
          );
          page = 1;
          refresh();
        } catch (e) {
          U.toast(e.message || '上传失败', 'error');
        }
      });
    }
  });
})();
