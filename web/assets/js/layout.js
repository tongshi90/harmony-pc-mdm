(function () {
  const PC_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M8 20h8M12 16v4"/></svg>';
  const USER_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';

  // 页面 pageId → 菜单 code（与后端 MenuCode 对齐）
  const PAGE_MENU = {
    dashboard: 'dashboard',
    users: 'platform', 'user-form': 'platform', 'role-permission': 'platform',
    apps: 'app', 'app-detail': 'app', 'app-form': 'app', 'app-version-form': 'app',
    devices: 'device', 'device-detail': 'device',
    members: 'member',
    'device-groups': 'member_group',
    'initial-policy': 'member_group',
    'initial-policy-form': 'member_group',
    'scene-dispatch': 'policy_dispatch',
    'scene-dispatch-create': 'policy_dispatch',
    'scene-dispatch-detail': 'policy_dispatch'
  };

  function menuCodeOf(pageId, moduleId) {
    return moduleId || PAGE_MENU[pageId] || pageId;
  }

  function ensureAuth() {
    if (typeof MDMApi === 'undefined') return Promise.resolve(null);
    if (!MDMApi.getToken()) {
      location.href = '/login.html';
      return Promise.reject(new Error('unauthorized'));
    }
    const cached = MDMApi.getCachedUser();
    if (cached) applyUser(cached);
    return MDMApi.me()
      .then(user => {
        applyUser(user);
        return user;
      })
      .catch(() => {
        MDMApi.clearSession();
        location.href = '/login.html';
        return null;
      });
  }

  function applyUser(user) {
    if (!window.MDM) window.MDM = {};
    const codes = user.menu_codes || (user.menus || []).map(m => m.code || m);
    MDM.user = {
      id: user.id,
      name: user.name,
      username: user.username,
      role: user.role_label || (user.is_admin ? '系统管理员' : '管理员'),
      dept: user.role && user.role.role_code ? user.role.role_code : '',
      is_admin: user.is_admin,
      role_id: user.role_id,
      role_code: user.role && user.role.role_code ? user.role.role_code : '',
      menu_codes: codes,
      menus: user.menus || []
    };
  }

  function flattenNav(menuCodes) {
    const set = new Set(menuCodes || []);
    const items = [];
    (MDM.nav || []).forEach(g => {
      (g.items || []).forEach(item => {
        if (set.has(item.code || item.id)) items.push(item);
      });
    });
    return items;
  }

  function renderTopNav(activeId, menuCodes) {
    const items = flattenNav(menuCodes);
    if (!items.length) {
      return '<span class="top-nav-item" style="opacity:.5;cursor:default">暂无菜单</span>';
    }
    return items.map(item =>
      `<a class="top-nav-item${item.id === activeId ? ' active' : ''}" href="${item.href}">${item.label}</a>`
    ).join('');
  }

  function firstAllowedHref(menuCodes) {
    if (typeof MDM.resolveHomeHref === 'function') {
      return MDM.resolveHomeHref(menuCodes);
    }
    const items = flattenNav(menuCodes);
    return items[0] ? items[0].href : '/index.html';
  }

  function renderNoMenuAccess(root, user) {
    const D = MDM;
    const u = D.user || user || { name: '未登录', role: '-' };
    const brandName = (D.platform && D.platform.brand) || 'Harmony PC MDM';
    const brandSub = (D.platform && D.platform.brandSub) || '企业终端管控平台';
    root.innerHTML = `
      <header class="top">
        <a class="brand" href="/index.html">
          <div class="brand-mark" aria-hidden="true">${PC_ICON}</div>
          <div class="brand-text">
            <strong>${brandName}</strong>
            <em>${brandSub}</em>
          </div>
        </a>
        <nav class="top-nav" aria-label="菜单">${renderTopNav('', [])}</nav>
        <div class="top-user" id="user-menu">
          <div class="user-avatar" aria-hidden="true">${USER_ICON}</div>
          <div>
            <div class="user-name">${u.name || ''}</div>
            <small class="user-role">${u.role || ''}</small>
          </div>
          <svg class="user-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
          <div class="user-dropdown">
            <button type="button" data-action="password">修改密码</button>
            <button type="button" data-action="logout">退出登录</button>
          </div>
        </div>
      </header>
      <main class="main">
        <div class="content">
          <div class="panel">
            <div class="panel-body" style="padding:56px 24px;text-align:center">
              <p style="margin:0 0 8px;font-size:16px;font-weight:600">暂无可用菜单</p>
              <p class="text-muted" style="margin:0;font-size:13px;line-height:1.6">
                当前账号未分配角色，或角色尚未配置菜单权限。<br>
                请联系管理员开通后再使用。
              </p>
            </div>
          </div>
        </div>
      </main>`;
    bindUserMenu();
  }

  function ensurePwdModal() {
    let mask = document.getElementById('pwd-modal-mask');
    if (mask) return mask;
    mask = document.createElement('div');
    mask.id = 'pwd-modal-mask';
    mask.className = 'modal-mask';
    const U = window.MDMUtils;
    mask.innerHTML = `
      <div class="modal">
        <div class="modal-header">修改密码</div>
        <div class="modal-body">
          <div class="form-item"><label class="form-label">旧密码</label>${U.passwordInputHtml({ id: 'pwd-old', placeholder: '请输入当前登录密码', autocomplete: 'current-password' })}</div>
          <div class="form-item" style="margin-top:12px"><label class="form-label">新密码</label>${U.passwordInputHtml({ id: 'pwd-new', placeholder: U.PLATFORM_PASSWORD_HINT, autocomplete: 'new-password' })}</div>
          <div class="form-item" style="margin-top:12px"><label class="form-label">确认新密码</label>${U.passwordInputHtml({ id: 'pwd-confirm', placeholder: '再次输入新密码', autocomplete: 'new-password' })}</div>
          <p class="text-muted" id="pwd-error" style="color:var(--error);margin-top:10px;display:none"></p>
        </div>
        <div class="modal-footer">
          <button class="btn" id="pwd-cancel" type="button">取消</button>
          <button class="btn btn-primary" id="pwd-ok" type="button">确定</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    U.bindPasswordToggles(mask);
    return mask;
  }

  function openChangePassword() {
    const U = MDMUtils;
    const mask = ensurePwdModal();
    mask.querySelector('#pwd-old').value = '';
    mask.querySelector('#pwd-new').value = '';
    mask.querySelector('#pwd-confirm').value = '';
    mask.querySelectorAll('.password-field input').forEach(input => { input.type = 'password'; });
    mask.querySelectorAll('[data-pwd-toggle]').forEach(btn => {
      btn.innerHTML = U._eyeOpen;
      btn.dataset.bound = '1';
    });
    const err = mask.querySelector('#pwd-error');
    err.style.display = 'none';
    mask.classList.add('show');

    const close = () => mask.classList.remove('show');
    mask.querySelector('#pwd-cancel').onclick = close;
    mask.querySelector('#pwd-ok').onclick = async () => {
      const oldPwd = mask.querySelector('#pwd-old').value;
      const newPwd = mask.querySelector('#pwd-new').value;
      const confirm = mask.querySelector('#pwd-confirm').value;
      if (!oldPwd || !newPwd) {
        err.textContent = '请填写完整';
        err.style.display = 'block';
        return;
      }
      const pwdErr = U.validatePlatformPassword(newPwd);
      if (pwdErr) {
        err.textContent = pwdErr;
        err.style.display = 'block';
        return;
      }
      if (newPwd !== confirm) {
        err.textContent = '两次输入的新密码不一致';
        err.style.display = 'block';
        return;
      }
      try {
        await MDMApi.changePassword(oldPwd, newPwd);
        close();
        U.toast('密码已修改，请重新登录');
        MDMApi.clearSession();
        setTimeout(() => { location.href = '/login.html'; }, 600);
      } catch (e) {
        err.textContent = e.message || '修改失败';
        err.style.display = 'block';
      }
    };
  }

  function bindUserMenu() {
    const chip = document.getElementById('user-menu');
    if (!chip) return;
    const dropdown = chip.querySelector('.user-dropdown');
    chip.addEventListener('click', e => {
      e.stopPropagation();
      dropdown.classList.toggle('show');
    });
    document.addEventListener('click', () => dropdown.classList.remove('show'));
    chip.querySelector('[data-action="password"]')?.addEventListener('click', e => {
      e.stopPropagation();
      dropdown.classList.remove('show');
      openChangePassword();
    });
    chip.querySelector('[data-action="logout"]')?.addEventListener('click', async e => {
      e.stopPropagation();
      dropdown.classList.remove('show');
      try { await MDMApi.logout(); } catch (_) { /* ignore */ }
      location.href = '/login.html';
    });
  }

  window.MDMLayout = {
    mount(config) {
      const {
        pageId, moduleId, title, subtitle, actions, breadcrumb, content, onMount, hidePageHead
      } = config;
      const root = document.getElementById('app');
      const D = MDM;
      const activeNav = menuCodeOf(pageId, moduleId);
      const requiredMenu = activeNav;

      document.body.dataset.tone = 'light';
      document.title = (D.platform && D.platform.name) || 'Harmony PC MDM';

      const render = (user) => {
        const menuCodes = (user && user.menu_codes) || [];
        if (!menuCodes.length) {
          renderNoMenuAccess(root, user);
          return;
        }
        if (requiredMenu && !menuCodes.includes(requiredMenu)) {
          location.href = firstAllowedHref(menuCodes);
          return;
        }
        const u = D.user || { name: '未登录', role: '-', dept: '' };
        const home = firstAllowedHref(menuCodes);
        const brandName = (D.platform && D.platform.brand) || 'Harmony PC MDM';
        const brandSub = (D.platform && D.platform.brandSub) || '企业终端管控平台';
        const showHead = !hidePageHead && title;
        const pageHeadHtml = showHead ? `
          <header class="page-head">
            <div>
              <h1>${title}</h1>
              ${subtitle ? `<p>${subtitle}</p>` : ''}
            </div>
            ${actions ? `<div class="head-actions">${actions}</div>` : ''}
          </header>` : '';

        root.innerHTML = `
          <header class="top">
            <a class="brand" href="${home}">
              <div class="brand-mark" aria-hidden="true">${PC_ICON}</div>
              <div class="brand-text">
                <strong>${brandName}</strong>
                <em>${brandSub}</em>
              </div>
            </a>
            <nav class="top-nav" aria-label="菜单">${renderTopNav(activeNav, menuCodes)}</nav>
            <div class="top-user" id="user-menu">
              <div class="user-avatar" aria-hidden="true">${USER_ICON}</div>
              <div>
                <div class="user-name">${u.name || ''}</div>
                <small class="user-role">${u.role || ''}</small>
              </div>
              <svg class="user-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
              <div class="user-dropdown">
                <button type="button" data-action="password">修改密码</button>
                <button type="button" data-action="logout">退出登录</button>
              </div>
            </div>
          </header>
          <main class="main">
            ${pageHeadHtml}
            ${breadcrumb ? `<div class="breadcrumb">${breadcrumb}</div>` : ''}
            <div class="content">
              <div id="page-content">${content || ''}</div>
            </div>
          </main>`;

        bindUserMenu();
        if (typeof onMount === 'function') onMount();
      };

      ensureAuth().then(render).catch(() => {});
    }
  };
})();
