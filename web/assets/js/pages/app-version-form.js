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
      <a class="btn" href="${U.href('appDetail', { id: appId })}">返回</a>
      <button type="button" class="btn btn-primary btn-save">保存</button>`,
    content: `
      <div class="panel">
        <div class="panel-body">
          <div class="form-grid">
            <div class="form-item"><label class="form-label">所属应用</label>
              <input class="form-input" value="${app.app_name}" readonly></div>
            <div class="form-item"><label class="form-label">版本名称 <span style="color:var(--error)">*</span></label>
              <input class="form-input" id="f-name" value="${version?.version_name || ''}"></div>
            <div class="form-item"><label class="form-label">版本号 <span style="color:var(--error)">*</span></label>
              <input class="form-input" id="f-code" value="${version?.version_code || ''}"></div>
            <div class="form-item full"><label class="form-label">安装包（.hap） <span style="color:var(--error)">*</span></label>
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
        fileSize: version?.file_size
      });

      document.querySelector('.btn-save')?.addEventListener('click', async () => {
        const version_name = document.getElementById('f-name').value.trim();
        const version_code = document.getElementById('f-code').value.trim();
        if (!version_name || !version_code) {
          U.toast('请填写版本名称与版本号', 'error');
          return;
        }
        if (!pkgField || !pkgField.hasPackage()) {
          U.toast('请上传 .hap 安装包', 'error');
          return;
        }
        const selectedFile = pkgField.getFile();
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
            await MDMApi.uploadAppPackage(appId, vid, selectedFile);
          }
          U.toast('已保存');
          location.href = U.href('appDetail', { id: appId });
        } catch (e) {
          U.toast(e.message || '保存失败', 'error');
        }
      });
    }
  });
})();
