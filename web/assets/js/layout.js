(function () {
  const PC_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M8 20h8M12 16v4"/></svg>';
  const USER_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';

  const MENU_ICONS = {
    dashboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>',
    device: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>',
    member: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2"/><circle cx="9.5" cy="7" r="3.5"/><path d="M20 8v6M17 11h6"/></svg>',
    member_group: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    app: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="6" height="6" rx="1.2"/><rect x="14" y="4" width="6" height="6" rx="1.2"/><rect x="4" y="14" width="6" height="6" rx="1.2"/><rect x="14" y="14" width="6" height="6" rx="1.2"/></svg>',
    app_cert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/><circle cx="12" cy="16" r="1.5"/></svg>',
    policy_dispatch: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 12h6M9 16h4"/></svg>',
    rag: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/><path d="M8 7h8M8 11h6"/></svg>',
    platform: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>'
  };

  // 页面 pageId → 菜单 code（与后端 MenuCode 对齐）
  const PAGE_MENU = {
    dashboard: 'dashboard',
    users: 'platform', 'user-form': 'platform', 'role-permission': 'platform',
    apps: 'app', 'app-detail': 'app', 'app-form': 'app', 'app-version-form': 'app',
    certs: 'app_cert',
    devices: 'device', 'device-detail': 'device',
    members: 'member',
    'device-groups': 'member_group',
    'initial-policy': 'member_group',
    'initial-policy-form': 'member_group',
    'scene-dispatch': 'policy_dispatch',
    'scene-dispatch-create': 'policy_dispatch',
    'scene-dispatch-detail': 'policy_dispatch',
    'knowledge-bases': 'rag',
    'knowledge-base-detail': 'rag',
    'rag-ask': 'rag',
    store: 'app_cert'
  };

  const PAGE_LABEL = {
    dashboard: '数据看板',
    device: '设备管理',
    member: '人员管理',
    member_group: '成员分组',
    app: '我的应用',
    app_cert: '证书',
    policy_dispatch: '策略记录',
    rag: '知识库问答',
    platform: '平台基础管理'
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

  function firstAllowedHref(menuCodes) {
    if (typeof MDM.resolveHomeHref === 'function') {
      return MDM.resolveHomeHref(menuCodes);
    }
    const items = flattenNav(menuCodes);
    return items[0] ? items[0].href : '/index.html';
  }

  function findNavMeta(activeId) {
    for (const g of MDM.nav || []) {
      for (const item of g.items || []) {
        if ((item.code || item.id) === activeId) {
          return { group: g.group || '', label: item.label || PAGE_LABEL[activeId] || activeId };
        }
      }
    }
    return { group: '', label: PAGE_LABEL[activeId] || activeId || '' };
  }

  function renderSidebarNav(activeId, menuCodes) {
    const set = new Set(menuCodes || []);
    const parts = [];
    (MDM.nav || []).forEach(g => {
      const items = (g.items || []).filter(item => set.has(item.code || item.id));
      if (!items.length) return;
      parts.push(`<div class="sidebar-group">`);
      if (g.group) parts.push(`<span class="sidebar-group-label">${g.group}</span>`);
      items.forEach(item => {
        const code = item.code || item.id;
        const icon = MENU_ICONS[code] || MENU_ICONS.dashboard;
        parts.push(
          `<a class="sidebar-link${code === activeId ? ' active' : ''}" href="${item.href}">` +
          `<span class="sidebar-link-icon" aria-hidden="true">${icon}</span>` +
          `<span>${item.label}</span></a>`
        );
      });
      parts.push(`</div>`);
    });
    if (!parts.length) {
      return '<div class="sidebar-group"><span class="sidebar-group-label">暂无菜单</span></div>';
    }
    return parts.join('');
  }

  function renderUserChip(u) {
    return `
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
      </div>`;
  }

  function renderShell({ home, brandName, activeNav, menuCodes, crumbHtml, userHtml, mainHtml }) {
    return `
      <aside class="sidebar" aria-label="主导航">
        <a class="sidebar-brand" href="${home}" title="${brandName}">
          <div class="brand-mark" aria-hidden="true">${PC_ICON}</div>
          <div class="brand-text">
            <strong>${brandName}</strong>
          </div>
        </a>
        <nav class="sidebar-nav">${renderSidebarNav(activeNav, menuCodes)}</nav>
      </aside>
      <div class="app-shell">
        <header class="top">
          <div class="top-crumb">${crumbHtml}</div>
          ${userHtml}
        </header>
        <main class="main">${mainHtml}</main>
      </div>`;
  }

  function renderNoMenuAccess(root, user) {
    const D = MDM;
    const u = D.user || user || { name: '未登录', role: '-' };
    const brandName = (D.platform && (D.platform.brand || D.platform.fullName)) || '企业终端管控平台';
    root.innerHTML = renderShell({
      home: '/index.html',
      brandName,
      activeNav: '',
      menuCodes: [],
      crumbHtml: '<strong>暂无可用菜单</strong>',
      userHtml: renderUserChip(u),
      mainHtml: `
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
        </div>`
    });
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
        pageId, moduleId, title, actions, breadcrumb, content, onMount
      } = config;
      const root = document.getElementById('app');
      const D = MDM;
      const activeNav = menuCodeOf(pageId, moduleId);
      const requiredMenu = activeNav;

      document.body.dataset.tone = 'light';
      document.title = (D.platform && D.platform.name) || '企业终端管控平台';

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
        const brandName = (D.platform && (D.platform.brand || D.platform.fullName)) || '企业终端管控平台';
        // 页面大标题统一去掉；顶栏面包屑仍展示当前页名称。若有 actions，落到内容区上方工具条。
        const actionsBarHtml = actions
          ? `<div class="page-actions-bar">${actions}</div>`
          : '';
        const meta = findNavMeta(activeNav);
        const crumbHtml = meta.group
          ? `<span>${meta.group}</span><span class="top-crumb-sep">/</span><strong>${title || meta.label}</strong>`
          : `<strong>${title || meta.label || brandName}</strong>`;

        root.innerHTML = renderShell({
          home,
          brandName,
          activeNav,
          menuCodes,
          crumbHtml,
          userHtml: renderUserChip(u),
          mainHtml: `
            ${breadcrumb ? `<div class="breadcrumb">${breadcrumb}</div>` : ''}
            ${actionsBarHtml}
            <div class="content">
              <div id="page-content">${content || ''}</div>
            </div>`
        });

        bindUserMenu();
        requestAnimationFrame(() => {
          document.body.classList.add('ui-ready');
          root.classList.add('ui-ready');
        });
        if (typeof onMount === 'function') onMount();
      };

      ensureAuth().then(render).catch(() => {});
    }
  };
})();
