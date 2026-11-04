(async function () {
  const U = MDMUtils;
  const editId = U.query('id');
  let admin = null;
  let roles = [];
  let loadError = '';

  try {
    roles = ((await MDMApi.listRoles()) || []).filter(r => Number(r.status) === 1);
    if (editId) admin = await MDMApi.getAdmin(editId);
  } catch (e) {
    loadError = e.message || '加载失败';
  }

  const roleOptions = roles.map(r =>
    `<option value="${r.id}"${admin && String(admin.role_id) === String(r.id) ? ' selected' : ''}>${r.role_name}（${r.role_code}）</option>`
  ).join('');

  const securitySection = admin
    ? ''
    : `
          <div class="form-section-title">安全</div>
          <div class="form-grid">
            <div class="form-item">
              <label class="form-label">初始密码 <span style="color:var(--error)">*</span></label>
              ${U.passwordInputHtml({ id: 'f-password', placeholder: U.PLATFORM_PASSWORD_HINT, autocomplete: 'new-password' })}
            </div>
          </div>`;

  MDMLayout.mount({
    pageId: 'user-form',
    title: admin ? '编辑管理员' : '新建管理员',
    actions: `<a class="btn" href="${U.href('users')}">返回</a>`,
    content: loadError
      ? `<div class="panel"><div class="panel-body text-muted">${loadError}</div></div>`
      : `
      <div class="panel">
        <div class="panel-body">
          <div class="form-section-title">账号信息</div>
          <div class="form-grid">
            <div class="form-item">
              <label class="form-label">登录账号 <span style="color:var(--error)">*</span></label>
              <input class="form-input" id="f-username" value="${admin ? admin.username : ''}" placeholder="如 zhangsan" ${admin ? 'readonly' : ''}>
            </div>
            <div class="form-item">
              <label class="form-label">姓名 <span style="color:var(--error)">*</span></label>
              <input class="form-input" id="f-name" value="${admin ? admin.name : ''}">
            </div>
            <div class="form-item">
              <label class="form-label">手机号</label>
              <input class="form-input" id="f-phone" value="${admin ? (admin.phone || '') : ''}" placeholder="11 位手机号，如 13800138000">
            </div>
            <div class="form-item">
              <label class="form-label">邮箱</label>
              <input class="form-input" id="f-email" value="${admin ? (admin.email || '') : ''}" placeholder="name@example.com">
            </div>
          </div>
          <div class="form-section-title">权限</div>
          <div class="form-grid">
            <div class="form-item">
              <label class="form-label">角色 <span style="color:var(--error)">*</span></label>
              <select class="form-select" id="f-role">
                <option value="">请选择角色</option>
                ${roleOptions}
              </select>
            </div>
          </div>
          ${securitySection}
          <div style="margin-top:20px;display:flex;gap:8px">
            <button class="btn btn-primary btn-save" type="button">保存</button>
            <a class="btn" href="${U.href('users')}">取消</a>
          </div>
        </div>
      </div>`,
    onMount() {
      if (loadError) return;
      U.bindPasswordToggles(document.getElementById('page-content'));
      document.querySelector('.btn-save')?.addEventListener('click', async () => {
        const username = document.getElementById('f-username').value.trim();
        const name = document.getElementById('f-name').value.trim();
        const phone = document.getElementById('f-phone').value.trim();
        const email = document.getElementById('f-email').value.trim();
        const role_id = document.getElementById('f-role').value;
        const passwordEl = document.getElementById('f-password');
        const password = passwordEl ? passwordEl.value : '';

        if (!name) {
          U.toast('请填写姓名', 'error');
          return;
        }
        if (!admin) {
          if (!username) {
            U.toast('请填写登录账号', 'error');
            return;
          }
          if (username === 'admin') {
            U.toast('admin 为系统保留账号', 'error');
            return;
          }
          if (!password) {
            U.toast('请设置初始密码', 'error');
            return;
          }
          const pwdErr = U.validatePlatformPassword(password);
          if (pwdErr) {
            U.toast(pwdErr, 'error');
            return;
          }
        }
        if (!role_id) {
          U.toast('请选择角色', 'error');
          return;
        }
        if (!U.isPhone(phone)) {
          U.toast('手机号格式不正确', 'error');
          return;
        }
        if (!U.isEmail(email)) {
          U.toast('邮箱格式不正确', 'error');
          return;
        }

        try {
          if (admin) {
            await MDMApi.updateAdmin(admin.id, { name, phone, email, role_id });
            U.toast('管理员已更新');
          } else {
            await MDMApi.createAdmin({
              username, name, phone, email, role_id, password
            });
            U.toast('管理员已创建');
          }
          setTimeout(() => { location.href = U.href('users'); }, 400);
        } catch (e) {
          U.toast(e.message || '保存失败', 'error');
        }
      });
    }
  });
})();
