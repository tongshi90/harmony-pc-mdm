(async function () {
  const U = MDMUtils;
  const appId = U.query('appId') || U.query('app');
  const versionId = U.query('versionId') || U.query('version');
  if (!appId) {
    location.href = U.href('apps');
    return;
  }

  let app, version = null;
  try {
    app = await MDMApi.getApp(appId);
    if (versionId) version = await MDMApi.getAppVersion(appId, versionId);
  } catch (e) {
    U.toast(e.message || '加载失败', 'error');
    location.href = U.href('apps');
    return;
  }

  const isEdit = !!version;
  let pkgField = null;

  MDMLayout.mount({
    pageId: 'app-version-form',
    title: isEdit ? '编辑版本' : '新建版本',
    actions: `
      <a class="btn" href="${U.href('appDetail', { id: appId, tab: 'versions' })}">返回</a>
      <button type="button" class="btn btn-primary btn-save">保存</button>`,
    content: `
      <div class="panel">
        <div class="panel-body">
          <div class="form-grid">
            <div class="form-item"><label class="form-label">版本名称 <span style="color:var(--error)">*</span></label>
              <input class="form-input" id="f-name" value="${version?.version_name || ''}"></div>
            <div class="form-item"><label class="form-label">版本号 <span style="color:var(--error)">*</span></label>
              <input class="form-input" id="f-code" value="${version?.version_code || ''}"></div>
            <div class="form-item full">
              <label class="form-label">安装包处理方式 <span style="color:var(--error)">*</span></label>
              <div style="display:flex;flex-direction:column;gap:10px;margin-top:6px">
                <label style="display:flex;align-items:flex-start;gap:8px;font-weight:normal;cursor:pointer;line-height:1.5">
                  <input type="radio" name="pkg-mode" id="f-mode-direct" value="direct" checked style="width:auto;margin-top:3px">
                  <span>
                    <strong>直接上传</strong>
                    <span class="text-muted" style="display:block;font-size:12px">包已在本机签好，平台仅存档，不做解包/重签</span>
                  </span>
                </label>
                <label style="display:flex;align-items:flex-start;gap:8px;font-weight:normal;cursor:pointer;line-height:1.5">
                  <input type="radio" name="pkg-mode" id="f-mode-resign" value="resign" style="width:auto;margin-top:3px">
                  <span>
                    <strong>平台重签</strong>
                    <span class="text-muted" style="display:block;font-size:12px">上传后解包并用平台证书重新封包</span>
                  </span>
                </label>
              </div>
            </div>
            <div class="form-item full"><label class="form-label">安装包（.hap / .app） <span style="color:var(--error)">*</span></label>
              ${U.hapPackageFieldHtml({
                fileName: version?.file_name || '',
                fileSize: version?.file_size
              })}
            </div>
          </div>
        </div>
      </div>`,
    onMount() {
      pkgField = U.bindHapPackageField({
        fileName: version?.file_name || '',
        fileSize: version?.file_size,
        acceptExt: ['.hap', '.app', '.sap'],
        emptyTitle: '点击选择 .hap / .app 安装包'
      });

      function selectedMode() {
        const el = document.querySelector('input[name="pkg-mode"]:checked');
        return el ? el.value : 'direct';
      }

      document.querySelector('.btn-save')?.addEventListener('click', async () => {
        const version_name = document.getElementById('f-name').value.trim();
        const version_code = document.getElementById('f-code').value.trim();
        const doResign = selectedMode() === 'resign';
        if (!version_name || !version_code) {
          U.toast('请填写版本名称与版本号', 'error');
          return;
        }
        if (!pkgField || !pkgField.hasPackage()) {
          U.toast('请上传安装包', 'error');
          return;
        }
        const selectedFile = pkgField.getFile();
        if (!selectedFile && doResign) {
          U.toast('平台重签需重新选择安装包', 'error');
          return;
        }
        const payload = {
          version_name,
          version_code
        };
        try {
          let vid = versionId;
          if (isEdit) {
            await MDMApi.updateAppVersion(appId, versionId, payload);
          } else {
            const created = await MDMApi.createAppVersion(appId, payload);
            vid = created.id;
          }
          if (selectedFile) {
            await MDMApi.uploadAppPackage(appId, vid, selectedFile, { resign: doResign });
          }
          U.toast(doResign ? '已上传并完成平台重签' : '已保存');
          location.href = U.href('appDetail', { id: appId, tab: 'versions' });
        } catch (e) {
          U.toast(e.message || '保存失败', 'error');
        }
      });
    }
  });
})();
