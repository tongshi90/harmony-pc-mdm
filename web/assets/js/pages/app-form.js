(async function () {
  const U = MDMUtils;
  const editId = U.query('id');
  const isEdit = !!editId;

  let app = null;
  let selectedIcon = null;
  let clearIcon = false;

  if (isEdit) {
    try {
      app = await MDMApi.getApp(editId);
    } catch (e) {
      U.toast(e.message || '加载失败', 'error');
      location.href = U.href('apps');
      return;
    }
  }

  function escAttr(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;');
  }

  function escText(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  const ICON_ACCEPT = '.png,.jpg,.jpeg,.webp,.gif,.svg,image/png,image/jpeg,image/webp,image/gif,image/svg+xml';

  function previewSrc() {
    if (selectedIcon) return URL.createObjectURL(selectedIcon);
    if (clearIcon) return U.DEFAULT_APP_ICON;
    if (isEdit && app && app.has_icon && app.app_icon) return app.app_icon;
    return U.DEFAULT_APP_ICON;
  }

  const iconBlock = `
            <div class="form-item full">
              <label class="form-label">应用图标</label>
              <div class="app-icon-upload">
                <img class="preview" id="icon-preview" src="${previewSrc()}" alt="应用图标预览">
                <div>
                  <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
                    <button type="button" class="btn" id="icon-pick">选择图标</button>
                    <button type="button" class="btn" id="icon-clear"${(isEdit && app && app.has_icon) ? '' : ' style="display:none"'}>恢复默认</button>
                  </div>
                  <input type="file" id="icon-file" accept="${ICON_ACCEPT}" style="display:none">
                  <div class="hint" id="icon-info" style="margin-top:8px">未上传时使用统一默认图标；支持 png / jpg / webp / gif / svg，不超过 2MB</div>
                </div>
              </div>
            </div>`;

  const createContent = `
      <div class="panel">
        <div class="panel-body">
          <div class="form-section-title">应用信息</div>
          <p class="param-hint" style="margin:0 0 12px">先创建应用实体；<strong>App ID</strong> 由云平台自动生成。创建成功后请在应用详情中<strong>新建版本并上传安装包</strong>。</p>
          <div class="form-grid">
            ${iconBlock}
            <div class="form-item"><label class="form-label">应用名称 <span style="color:var(--error)">*</span></label>
              <input class="form-input" id="f-name" placeholder="如 企业微信"></div>
            <div class="form-item"><label class="form-label">Bundle Name <span style="color:var(--error)">*</span></label>
              <input class="form-input" id="f-bundle" placeholder="端侧包名，如 com.company.app"></div>
            <div class="form-item full"><label class="form-label">应用描述</label>
              <textarea class="form-textarea" id="f-desc" placeholder="应用说明、用途"></textarea></div>
          </div>
        </div>
      </div>`;

  const editContent = isEdit ? `
      <div class="panel">
        <div class="panel-body">
          <div class="form-section-title">应用基本信息</div>
          <div class="form-grid">
            ${iconBlock}
            <div class="form-item"><label class="form-label">应用名称 <span style="color:var(--error)">*</span></label>
              <input class="form-input" id="f-name" value="${escAttr(app.app_name)}"></div>
            <div class="form-item"><label class="form-label">应用编码</label>
              <input class="form-input" id="f-code" value="${escAttr(app.app_code)}" readonly></div>
            <div class="form-item"><label class="form-label">App ID</label>
              <input class="form-input" id="f-app-id" value="${escAttr(app.app_id)}" readonly></div>
            <div class="form-item"><label class="form-label">Bundle Name</label>
              <input class="form-input" id="f-bundle" value="${escAttr(app.bundle_name)}" readonly></div>
            <div class="form-item"><label class="form-label">状态</label>
              <select class="form-select" id="f-status">
                <option value="1"${Number(app.status) === 1 ? ' selected' : ''}>上架</option>
                <option value="0"${Number(app.status) === 0 ? ' selected' : ''}>下架</option>
              </select></div>
            <div class="form-item full"><label class="form-label">应用描述</label>
              <textarea class="form-textarea" id="f-desc">${escText(app.description)}</textarea></div>
          </div>
          <p class="param-hint" style="margin-top:8px">App ID、Bundle Name、应用编码创建后不可修改；版本与安装包请在应用详情中管理。</p>
        </div>
      </div>` : '';

  MDMLayout.mount({
    pageId: 'app-form',
    title: isEdit ? '编辑应用' : '新建应用',
    actions: `
      <a class="btn" href="${U.href('apps')}">返回</a>
      <button type="button" class="btn btn-primary btn-save">${isEdit ? '保存' : '创建应用'}</button>`,
    content: isEdit ? editContent : createContent,
    onMount() {
      const iconInput = document.getElementById('icon-file');
      const iconPreview = document.getElementById('icon-preview');
      const iconInfo = document.getElementById('icon-info');
      const iconClearBtn = document.getElementById('icon-clear');

      function refreshIconUi() {
        if (iconPreview) iconPreview.src = previewSrc();
        const showClear = !!(selectedIcon || (!clearIcon && isEdit && app && app.has_icon));
        if (iconClearBtn) iconClearBtn.style.display = showClear ? '' : 'none';
        if (!iconInfo) return;
        if (selectedIcon) {
          iconInfo.textContent = `${selectedIcon.name} · ${(selectedIcon.size / 1024).toFixed(1)} KB`;
        } else if (clearIcon) {
          iconInfo.textContent = '将使用统一默认图标';
        } else if (isEdit && app && app.has_icon) {
          iconInfo.textContent = '已上传自定义图标；可重新选择或恢复默认';
        } else {
          iconInfo.textContent = '未上传时使用统一默认图标；支持 png / jpg / webp / gif / svg，不超过 2MB';
        }
      }

      document.getElementById('icon-pick')?.addEventListener('click', () => iconInput?.click());
      iconInput?.addEventListener('change', () => {
        const f = iconInput.files && iconInput.files[0];
        if (!f) return;
        const name = (f.name || '').toLowerCase();
        if (!/\.(png|jpe?g|webp|gif|svg)$/.test(name)) {
          U.toast('仅支持 png / jpg / webp / gif / svg', 'error');
          iconInput.value = '';
          return;
        }
        if (f.size > 2 * 1024 * 1024) {
          U.toast('图标不能超过 2MB', 'error');
          iconInput.value = '';
          return;
        }
        selectedIcon = f;
        clearIcon = false;
        refreshIconUi();
      });
      iconClearBtn?.addEventListener('click', () => {
        selectedIcon = null;
        clearIcon = true;
        if (iconInput) iconInput.value = '';
        refreshIconUi();
      });
      refreshIconUi();

      async function syncIcon(appId) {
        if (selectedIcon) {
          await MDMApi.uploadAppIcon(appId, selectedIcon);
        } else if (isEdit && clearIcon && app && app.has_icon) {
          await MDMApi.clearAppIcon(appId);
        }
      }

      document.querySelector('.btn-save')?.addEventListener('click', async () => {
        if (isEdit) {
          const app_name = document.getElementById('f-name').value.trim();
          if (!app_name) {
            U.toast('请填写应用名称', 'error');
            return;
          }
          try {
            await MDMApi.updateApp(app.id, {
              app_name,
              description: document.getElementById('f-desc').value.trim(),
              status: Number(document.getElementById('f-status').value)
            });
            await syncIcon(app.id);
            U.toast('已保存');
            location.href = U.href('appDetail', { id: app.id });
          } catch (e) {
            U.toast(e.message || '保存失败', 'error');
          }
          return;
        }

        const app_name = document.getElementById('f-name').value.trim();
        const bundle_name = document.getElementById('f-bundle').value.trim();
        if (!app_name) {
          U.toast('请填写应用名称', 'error');
          return;
        }
        if (!bundle_name) {
          U.toast('请填写 Bundle Name', 'error');
          return;
        }
        try {
          const created = await MDMApi.createApp({
            app_name,
            bundle_name,
            description: document.getElementById('f-desc').value.trim()
          });
          await syncIcon(created.id);
          U.toast('应用已创建，请继续上传版本安装包');
          location.href = U.href('appDetail', { id: created.id });
        } catch (e) {
          U.toast(e.message || '创建失败', 'error');
        }
      });
    }
  });
})();
