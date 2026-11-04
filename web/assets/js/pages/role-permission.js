(async function () {
  const U = MDMUtils;
  const roleId = U.query('id') || U.query('role');
  let role = null;
  let menus = [];
  let error = '';

  try {
    if (!roleId) throw new Error('缺少角色 ID');
    // 兼容旧链接 ?role=admin
    if (/^\d+$/.test(roleId)) {
      role = await MDMApi.getRole(roleId);
    } else {
      const list = await MDMApi.listRoles();
      role = (list || []).find(r => r.role_code === roleId);
      if (!role) throw new Error('角色不存在');
      role = await MDMApi.getRole(role.id);
    }
    menus = await MDMApi.listMenus() || [];
  } catch (e) {
    error = e.message || '加载失败';
  }

  const selected = new Set((role && role.menu_codes) || []);
  const isSystem = !!(role && Number(role.is_system) === 1);

  MDMLayout.mount({
    pageId: 'role-permission',
    title: '平台基础管理',
    breadcrumb: `<a href="${U.href('users', { tab: 'roles' })}">平台基础管理</a> / 角色权限配置${role ? ' / ' + role.role_name : ''}`,
    content: error
      ? `<div class="panel"><div class="panel-body text-muted">${error}</div></div>`
      : `
      <div class="panel">
        <div class="panel-header">
          <h3>${role.role_name}${isSystem ? ' <span class="tag tag-orange">系统</span>' : ''}</h3>
          <span class="extra">${role.role_code}</span>
        </div>
        <div class="panel-body">
          <p class="text-muted mb-16">${role.description || '—'}</p>
          <table class="data-table">
            <thead><tr><th style="width:72px;white-space:nowrap">授权</th><th>菜单</th><th>Code</th><th>接口前缀</th></tr></thead>
            <tbody>
              ${menus.map(m => `<tr>
                <td><input type="checkbox" class="perm-menu" data-code="${m.code}" ${selected.has(m.code) ? 'checked' : ''}${isSystem ? ' disabled' : ''}></td>
                <td><strong>${m.name}</strong></td>
                <td><code>${m.code}</code></td>
                <td><code>${m.api_prefix}</code></td>
              </tr>`).join('')}
            </tbody>
          </table>
          <div style="margin-top:16px">
            ${isSystem ? '' : '<button class="btn btn-primary btn-save" type="button">保存权限</button>'}
            <a class="btn" href="${U.href('users', { tab: 'roles' })}">返回</a>
          </div>
        </div>
      </div>`,
    onMount() {
      if (error || isSystem) return;
      document.querySelector('.btn-save')?.addEventListener('click', async () => {
        const menu_codes = [...document.querySelectorAll('.perm-menu:checked')].map(el => el.dataset.code);
        try {
          await MDMApi.updateRole(role.id, { menu_codes });
          U.toast('角色权限已保存');
          setTimeout(() => { location.href = U.href('users', { tab: 'roles' }); }, 400);
        } catch (e) {
          U.toast(e.message || '保存失败', 'error');
        }
      });
    }
  });
})();
