(async function () {
  const U = MDMUtils;
  const presetKb = U.query('kb_id') || '';

  let kbs = [];
  let asking = false;
  /** 本页会话（正序旧→新）；发送时上送近几轮 history */
  let turns = [];
  const MAX_HISTORY_TURNS = 2;

  function esc(s) {
    return String(s || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  }

  /** 轻量 Markdown → HTML（先转义再排版，覆盖列表/加粗/标题等常见回答格式） */
  function renderMarkdown(src) {
    const raw = String(src || '').replace(/\r\n/g, '\n').trim();
    if (!raw) return '（暂无回答）';

    function inlineFmt(text) {
      let t = esc(text);
      t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
      t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
      t = t.replace(/__([^_]+)__/g, '<strong>$1</strong>');
      t = t.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
      return t;
    }

    const lines = raw.split('\n');
    const html = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();
      if (!trimmed) {
        i += 1;
        continue;
      }

      const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
      if (heading) {
        const level = heading[1].length;
        html.push(`<h${level + 2}>${inlineFmt(heading[2])}</h${level + 2}>`);
        i += 1;
        continue;
      }

      if (/^[-*]\s+/.test(trimmed)) {
        const items = [];
        while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
          items.push(`<li>${inlineFmt(lines[i].trim().replace(/^[-*]\s+/, ''))}</li>`);
          i += 1;
        }
        html.push(`<ul>${items.join('')}</ul>`);
        continue;
      }

      if (/^\d+\.\s+/.test(trimmed)) {
        const items = [];
        while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
          items.push(`<li>${inlineFmt(lines[i].trim().replace(/^\d+\.\s+/, ''))}</li>`);
          i += 1;
        }
        html.push(`<ol>${items.join('')}</ol>`);
        continue;
      }

      const paras = [trimmed];
      i += 1;
      while (i < lines.length) {
        const next = lines[i].trim();
        if (!next || /^#{1,3}\s+/.test(next) || /^[-*]\s+/.test(next) || /^\d+\.\s+/.test(next)) break;
        paras.push(next);
        i += 1;
      }
      html.push(`<p>${paras.map(inlineFmt).join('<br>')}</p>`);
    }
    return html.join('') || esc(raw);
  }

  async function loadKbs() {
    try {
      kbs = (await MDMApi.listRagKnowledgeBases({})) || [];
    } catch (e) {
      kbs = [];
      U.toast(e.message || '加载知识库失败', 'error');
    }
  }

  function kbOptions() {
    return [`<option value="">全部制度</option>`]
      .concat(kbs.map(kb => {
        const sel = String(presetKb) === String(kb.id) ? ' selected' : '';
        return `<option value="${esc(kb.id)}"${sel}>${esc(kb.name)}</option>`;
      }))
      .join('');
  }

  function sourceDocLabel(doc) {
    const name = doc.file_name || doc.file_path || '制度原文';
    const kb = doc.kb_name ? `${doc.kb_name} · ` : '';
    const n = (doc.chunks && doc.chunks.length) || 0;
    if (n > 1) return `${kb}${name}（${n} 处摘录）`;
    const page = doc.chunks && doc.chunks[0] && doc.chunks[0].page != null && doc.chunks[0].page !== ''
      ? `，第 ${doc.chunks[0].page} 页`
      : '';
    return `${kb}${name}${page}`;
  }

  /** 按文件合并切片：列表只显示文档一次 */
  function groupSourcesByFile(sources) {
    if (!Array.isArray(sources) || !sources.length) return [];
    const map = new Map();
    sources.forEach(s => {
      const key = String(
        s.file_id
        || `${s.kb_id || ''}|${s.file_name || s.file_path || ''}`
      );
      if (!map.has(key)) {
        map.set(key, {
          key,
          kb_id: s.kb_id,
          kb_name: s.kb_name,
          file_id: s.file_id,
          file_name: s.file_name,
          file_path: s.file_path,
          chunks: []
        });
      }
      const g = map.get(key);
      if (!g.file_name && s.file_name) g.file_name = s.file_name;
      if (!g.kb_name && s.kb_name) g.kb_name = s.kb_name;
      g.chunks.push({
        text: s.text || '',
        page: s.page,
        chunk_id: s.chunk_id
      });
    });
    return Array.from(map.values());
  }

  /** 清洗正文：去掉文末来源段、行内出处脚注（参考依据另区展示） */
  function sanitizeAnswerBody(text) {
    let t = String(text || '').replace(/\r\n/g, '\n');
    t = t.replace(
      /\n+(?:#{1,3}\s*)?(?:\*\*|__)?来源(?:\*\*|__)?\s*[：:].*$/isu,
      ''
    );
    t = t.replace(
      /\n+(?:#{1,3}\s*)?(?:\*\*|__)?(?:参考依据|参考文献|参考资料)(?:\*\*|__)?\s*[：:].*$/isu,
      ''
    );
    // 行内/段末出处：（来源：…）（依据：xxx.pdf）【文件：…】等
    t = t.replace(
      /[（(]\s*(?:来源|依据|参考|出处|参见|见)\s*[：:．.\s][^）)]*[）)]/gu,
      ''
    );
    t = t.replace(/【\s*(?:来源|依据|参考|文件|知识库)\s*[：:．.\s][^】]*】/gu, '');
    t = t.replace(/[ \t]*——+\s*(?:来源|依据|参考)[^\n]*/gu, '');
    // 清理因删除脚注留下的多余空白
    t = t.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n');
    return t.trim();
  }

  function buildConversationHistory() {
    const recent = turns.slice(-MAX_HISTORY_TURNS);
    const history = [];
    recent.forEach(t => {
      const q = String(t.question || '').trim();
      const a = sanitizeAnswerBody((t.data && t.data.answer) || '');
      if (q) history.push({ role: 'user', content: q });
      if (a) history.push({ role: 'assistant', content: a });
    });
    return history;
  }

  function openSourceModal(doc) {
    const chunks = (doc && doc.chunks) || [];
    const bodyHtml = chunks.length
      ? chunks.map((c, i) => {
        const metaBits = [];
        if (chunks.length > 1) metaBits.push(`摘录 ${i + 1}`);
        if (c.page != null && c.page !== '') metaBits.push(`第 ${c.page} 页`);
        return `
          <div class="ask-src-chunk">
            ${metaBits.length ? `<div class="ask-src-chunk-meta">${esc(metaBits.join(' · '))}</div>` : ''}
            <div class="ask-src-body">${esc(c.text || '（无内容）')}</div>
          </div>`;
      }).join('')
      : '<div class="ask-src-body">（无内容）</div>';

    const mask = document.createElement('div');
    mask.className = 'modal-mask show';
    mask.innerHTML = `
      <div class="modal modal-lg">
        <div class="modal-header">参考原文</div>
        <div class="modal-body ask-src-modal-body">
          <p class="ask-src-meta">${esc(sourceDocLabel(doc))}</p>
          ${bodyHtml}
        </div>
        <div class="modal-footer">
          <button type="button" class="btn" id="ask-src-close">关闭</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    const close = () => mask.remove();
    mask.querySelector('#ask-src-close').onclick = close;
    mask.addEventListener('click', e => { if (e.target === mask) close(); });
  }

  function renderRefs(docs, turnIndex) {
    if (!Array.isArray(docs) || !docs.length) return '';
    return `
      <div class="ask-refs">
        <span class="ask-refs-label">参考依据</span>
        <ul class="ask-refs-list">
          ${docs.map((d, i) => `
            <li>
              <button type="button" class="ask-ref-link" data-turn="${turnIndex}" data-doc="${i}">
                <span class="ask-ref-idx">${i + 1}.</span>
                <span class="ask-ref-name" title="${esc(sourceDocLabel(d))}">${esc(sourceDocLabel(d))}</span>
              </button>
            </li>`).join('')}
        </ul>
      </div>`;
  }

  function renderTurn(turn, index) {
    const data = turn.data || {};
    const docs = groupSourcesByFile(data.sources || []);
    turn._docs = docs;
    const noHit = data.has_evidence === false;
    const tips = [];
    if (noHit) tips.push('未在制度库中找到直接依据。');
    if (Array.isArray(data.notices) && data.notices.length) {
      const useful = data.notices.filter(n => {
        const s = String(n || '');
        return s && !/^本次将检索/.test(s) && !/^本次仅检索/.test(s);
      });
      if (useful.length) tips.push(useful.join('；'));
    }
    const answer = sanitizeAnswerBody(data.answer || '');
    const streaming = !!data.streaming;
    const bodyHtml = answer
      ? renderMarkdown(answer)
      : (streaming ? '<span class="ask-stream-placeholder">…</span>' : renderMarkdown(''));
    const streamTip = streaming && turn._streamHint ? turn._streamHint : '';
    const tipText = streamTip || (tips.length ? tips.join(' ') : '');
    return `
      <div class="ask-turn">
        <div class="ask-row ask-row-user">
          <div class="ask-msg ask-msg-user">${esc(turn.question)}</div>
        </div>
        <div class="ask-row ask-row-bot">
          <div class="ask-msg ask-msg-bot">
            <div class="ask-msg-body ask-md">${bodyHtml}</div>
            ${tipText ? `<p class="ask-turn-tip">${esc(tipText)}</p>` : ''}
            ${noHit || streaming ? '' : renderRefs(docs, index)}
          </div>
        </div>
      </div>`;
  }

  function bindRefs(root) {
    root.querySelectorAll('.ask-ref-link').forEach(btn => {
      btn.onclick = () => {
        const turn = turns[Number(btn.dataset.turn)];
        const doc = turn && turn._docs && turn._docs[Number(btn.dataset.doc)];
        if (doc) openSourceModal(doc);
      };
    });
  }

  function renderHistory() {
    const box = document.getElementById('ask-thread');
    if (!box) return;
    if (!turns.length) {
      box.innerHTML = `
        <div class="ask-empty">
          <div class="ask-empty-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
              <path d="M8 7h8M8 11h6"/>
            </svg>
          </div>
          <div>向制度知识库提问</div>
          <div class="ask-empty-hint">例如：员工请假需要履行哪些手续？回答将基于已入库制度原文。</div>
        </div>`;
      return;
    }
    box.innerHTML = turns.map((t, i) => renderTurn(t, i)).join('');
    bindRefs(box);
    box.scrollTop = box.scrollHeight;
  }

  /** 流式过程中只刷新最后一轮助手正文，避免整表重绘过频 */
  function patchStreamingAnswer(turnIndex, answerText, hint) {
    const box = document.getElementById('ask-thread');
    if (!box) return;
    const turnsEls = box.querySelectorAll('.ask-turn');
    const el = turnsEls[turnIndex];
    if (!el) {
      renderHistory();
      return;
    }
    const body = el.querySelector('.ask-msg-body');
    if (body) body.innerHTML = renderMarkdown(sanitizeAnswerBody(answerText || ''));
    let tip = el.querySelector('.ask-turn-tip');
    if (hint) {
      if (!tip) {
        tip = document.createElement('p');
        tip.className = 'ask-turn-tip';
        const msg = el.querySelector('.ask-msg-bot');
        if (msg) msg.appendChild(tip);
      }
      tip.textContent = hint;
    } else if (tip) {
      tip.remove();
    }
    box.scrollTop = box.scrollHeight;
  }

  await loadKbs();

  MDMLayout.mount({
    pageId: 'rag-ask',
    moduleId: 'rag',
    title: '制度问答',
    content: `
      <div class="ask-page">
        <div class="toolbar toolbar-standalone">
          <div class="toolbar-left">
            <a class="btn btn-sm" href="${U.href('ragKnowledgeBases')}">← 知识库</a>
            <label class="ask-kb-field">
              <span class="ask-kb-label">检索范围</span>
              <select id="ask-kb" class="form-select ask-kb-select" title="检索范围">${kbOptions()}</select>
            </label>
          </div>
          <div class="toolbar-right">
            <button type="button" class="btn btn-sm" id="ask-new">新对话</button>
          </div>
        </div>
        <div class="ask-panel">
          <div id="ask-thread" class="ask-thread"></div>
          <div class="ask-composer">
            <textarea id="ask-q" class="form-textarea ask-q-input" rows="2" placeholder="请输入制度相关问题" maxlength="4000"></textarea>
            <div class="ask-composer-bar">
              <span class="ask-hint" id="ask-hint">Enter 发送，Shift+Enter 换行</span>
              <button type="button" class="btn btn-primary" id="ask-send">发送</button>
            </div>
          </div>
        </div>
      </div>`,
    onMount() {
      document.body.classList.add('page-ask');
      renderHistory();
      const hintIdle = 'Enter 发送，Shift+Enter 换行';
      const setHintIdle = () => {
        document.getElementById('ask-hint').textContent = hintIdle;
      };
      document.getElementById('ask-new').onclick = () => {
        if (asking) return;
        turns = [];
        renderHistory();
        setHintIdle();
        document.getElementById('ask-q').focus();
      };
      const send = async () => {
        if (asking) return;
        const qEl = document.getElementById('ask-q');
        const question = qEl.value.trim();
        if (!question) {
          U.toast('请输入问题', 'error');
          return;
        }
        const kbVal = document.getElementById('ask-kb').value;
        asking = true;
        document.getElementById('ask-send').disabled = true;
        const history = buildConversationHistory();
        document.getElementById('ask-hint').textContent = '正在检索…';

        const turn = {
          question,
          data: {
            answer: '',
            sources: [],
            has_evidence: true,
            notices: [],
            streaming: true
          }
        };
        turns.push(turn);
        const turnIndex = turns.length - 1;
        qEl.value = '';
        renderHistory();

        let pendingDelta = '';
        let rafId = 0;
        const flushDelta = () => {
          rafId = 0;
          if (!turn.data.streaming) return;
          turn.data.answer = (turn.data.answer || '') + pendingDelta;
          pendingDelta = '';
          patchStreamingAnswer(turnIndex, turn.data.answer, turn._streamHint || '');
        };
        const queueDelta = (text) => {
          pendingDelta += text;
          if (!rafId) rafId = requestAnimationFrame(flushDelta);
        };

        try {
          const payload = {
            question,
            kb_id: kbVal || null,
            top_k: 5,
            enable_rerank: true
          };
          if (history.length) payload.conversation_history = history;

          const data = await MDMApi.ragAskStream(payload, {
            onStatus(st) {
              const msg = (st && st.message) || '';
              const phase = st && st.phase;
              if (phase === 'generating') {
                document.getElementById('ask-hint').textContent = msg || '正在生成回答…';
                turn._streamHint = '';
              } else {
                document.getElementById('ask-hint').textContent = msg || '正在检索…';
                turn._streamHint = msg || '正在检索…';
                patchStreamingAnswer(turnIndex, turn.data.answer, turn._streamHint);
              }
            },
            onDelta(text) {
              if (!text) return;
              turn._streamHint = '';
              queueDelta(text);
            },
            onFinal(finalData) {
              if (rafId) {
                cancelAnimationFrame(rafId);
                rafId = 0;
              }
              if (pendingDelta) {
                turn.data.answer = (turn.data.answer || '') + pendingDelta;
                pendingDelta = '';
              }
              turn.data = Object.assign({}, finalData || {}, { streaming: false });
              if (!turn.data.answer && pendingDelta === '') {
                /* keep */
              }
            }
          });

          turn.data = Object.assign({}, data || turn.data, { streaming: false });
          delete turn._streamHint;
          renderHistory();
          setHintIdle();
        } catch (e) {
          if (rafId) cancelAnimationFrame(rafId);
          if (pendingDelta) {
            turn.data.answer = (turn.data.answer || '') + pendingDelta;
          }
          turn.data.streaming = false;
          if (!String(turn.data.answer || '').trim()) {
            turns.pop();
          } else {
            turn.data.notices = [e.message || '生成中断'];
            renderHistory();
          }
          U.toast(e.message || '提问失败', 'error');
          setHintIdle();
        } finally {
          asking = false;
          document.getElementById('ask-send').disabled = false;
          qEl.focus();
        }
      };
      document.getElementById('ask-send').onclick = send;
      document.getElementById('ask-q').addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          send();
        }
      });
    }
  });
})();
