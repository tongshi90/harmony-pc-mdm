/**
 * 统一 API 客户端：Token、RSA 密码加密、业务请求封装
 * 响应约定：{ code:0, message:"", data:{} }；HTTP 401 → 跳转登录
 * 云侧管理台接口前缀：/platform；对外设备侧白名单预留 /api/
 */
(function () {
  const TOKEN_KEY = 'mdm_access_token';
  const USER_KEY = 'mdm_user';
  const PLATFORM = '/platform/platform';

  let publicKeyPemPromise = null;
  let cachedPublicKeyPem = null;
  let cachedSubtleKey = null;
  let forgeLoadPromise = null;

  function getToken() {
    return localStorage.getItem(TOKEN_KEY) || '';
  }

  function setSession(token, user) {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  function getCachedUser() {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || 'null');
    } catch {
      return null;
    }
  }

  /** HTTPS / localhost 才有 crypto.subtle；内网 HTTP 访问时需走 forge 兜底 */
  function canUseSubtle() {
    try {
      return !!(window.crypto && window.crypto.subtle && typeof window.crypto.subtle.importKey === 'function');
    } catch (_) {
      return false;
    }
  }

  function pemToArrayBuffer(pem) {
    const b64 = pem
      .replace(/-----BEGIN PUBLIC KEY-----/, '')
      .replace(/-----END PUBLIC KEY-----/, '')
      .replace(/\s+/g, '');
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes.buffer;
  }

  async function loadPublicKeyPem() {
    if (cachedPublicKeyPem) return cachedPublicKeyPem;
    if (!publicKeyPemPromise) {
      publicKeyPemPromise = fetch('/platform/auth/public-key')
        .then(r => r.json())
        .then(res => {
          if (res.code !== 0) throw new Error(res.message || '获取公钥失败');
          const pem = (res.data && res.data.public_key) || '';
          if (!pem) throw new Error('公钥为空');
          cachedPublicKeyPem = pem;
          return pem;
        })
        .catch(err => {
          publicKeyPemPromise = null;
          throw err;
        });
    }
    return publicKeyPemPromise;
  }

  async function loadSubtleKey(pem) {
    if (cachedSubtleKey) return cachedSubtleKey;
    cachedSubtleKey = await crypto.subtle.importKey(
      'spki',
      pemToArrayBuffer(pem),
      { name: 'RSA-OAEP', hash: 'SHA-256' },
      false,
      ['encrypt']
    );
    return cachedSubtleKey;
  }

  function ensureForge() {
    if (window.forge && window.forge.pki) return Promise.resolve(window.forge);
    if (forgeLoadPromise) return forgeLoadPromise;
    forgeLoadPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = '/assets/js/vendor/forge.min.js';
      s.async = true;
      s.onload = () => {
        if (window.forge && window.forge.pki) resolve(window.forge);
        else reject(new Error('RSA 库加载异常'));
      };
      s.onerror = () => {
        forgeLoadPromise = null;
        reject(new Error('无法加载 RSA 加密库，请检查网络或静态资源'));
      };
      document.head.appendChild(s);
    });
    return forgeLoadPromise;
  }

  async function encryptPasswordWithForge(pem, plain) {
    const forge = await ensureForge();
    const publicKey = forge.pki.publicKeyFromPem(pem);
    const encrypted = publicKey.encrypt(forge.util.encodeUtf8(String(plain || '')), 'RSA-OAEP', {
      md: forge.md.sha256.create(),
      mgf1: { md: forge.md.sha256.create() }
    });
    return forge.util.encode64(encrypted);
  }

  async function encryptPassword(plain) {
    const pem = await loadPublicKeyPem();
    if (canUseSubtle()) {
      const key = await loadSubtleKey(pem);
      const encoded = new TextEncoder().encode(String(plain || ''));
      const cipher = await crypto.subtle.encrypt({ name: 'RSA-OAEP' }, key, encoded);
      const bytes = new Uint8Array(cipher);
      let binary = '';
      for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
      return btoa(binary);
    }
    // 非安全上下文（如 http://服务器IP:端口）：用 forge 做同等 RSA-OAEP-SHA256
    return encryptPasswordWithForge(pem, plain);
  }

  async function request(path, options = {}) {
    const headers = Object.assign(
      { 'Content-Type': 'application/json' },
      options.headers || {}
    );
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    const resp = await fetch(path, {
      method: options.method || 'GET',
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined
    });

    let data;
    try {
      data = await resp.json();
    } catch {
      throw new Error('服务器响应异常');
    }

    // 授权失败统一 401 → 清会话并跳转登录
    if (resp.status === 401 || data.code === 401) {
      clearSession();
      if (!location.pathname.endsWith('/login.html')) {
        location.href = '/login.html';
      }
      throw new Error(data.message || '未登录');
    }

    if (data.code !== 0) {
      throw new Error(data.message || '请求失败');
    }
    return data.data;
  }

  window.MDMApi = {
    getToken,
    setSession,
    clearSession,
    getCachedUser,
    encryptPassword,
    request,
    login(username, password) {
      return encryptPassword(password).then(cipher =>
        request('/platform/auth/login', {
          method: 'POST',
          body: { username, password: cipher }
        }).then(data => {
          setSession(data.access_token, data.user);
          return data;
        })
      );
    },
    logout() {
      return request('/platform/auth/logout', { method: 'POST' })
        .catch(() => null)
        .finally(() => clearSession());
    },
    me() {
      return request('/platform/auth/me').then(user => {
        setSession(getToken(), user);
        return user;
      });
    },
    changePassword(oldPassword, newPassword) {
      return Promise.all([encryptPassword(oldPassword), encryptPassword(newPassword)]).then(
        ([oldCipher, newCipher]) =>
          request('/platform/auth/password', {
            method: 'PUT',
            body: { old_password: oldCipher, new_password: newCipher }
          })
      );
    },

    listMenus() {
      return request(`${PLATFORM}/menus`);
    },
    getMqttConfig() {
      return request(`${PLATFORM}/mqtt`);
    },
    testMqttConfig(payload) {
      return request(`${PLATFORM}/mqtt/test`, { method: 'POST', body: payload });
    },
    saveMqttConfig(payload) {
      return request(`${PLATFORM}/mqtt`, { method: 'PUT', body: payload });
    },
    getLogConfig() {
      return request(`${PLATFORM}/log-config`);
    },
    saveLogConfig(payload) {
      return request(`${PLATFORM}/log-config`, { method: 'PUT', body: payload });
    },

    listMdmVersions() {
      return request(`${PLATFORM}/mdm-app/versions`);
    },
    createMdmVersion(payload) {
      return request(`${PLATFORM}/mdm-app/versions`, { method: 'POST', body: payload });
    },
    updateMdmVersion(id, payload) {
      return request(`${PLATFORM}/mdm-app/versions/${id}`, { method: 'PUT', body: payload });
    },
    deleteMdmVersion(id) {
      return request(`${PLATFORM}/mdm-app/versions/${id}`, { method: 'DELETE' });
    },
    listMdmTargetGroups(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      const qs = q.toString();
      return request(`${PLATFORM}/mdm-app/target-groups${qs ? `?${qs}` : ''}`);
    },
    batchUpgradeMdm(versionId, payload) {
      return request(`${PLATFORM}/mdm-app/versions/${versionId}/batch-upgrade`, {
        method: 'POST',
        body: payload
      });
    },
    async uploadMdmPackage(versionId, file) {
      const headers = {};
      const token = getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
      const fd = new FormData();
      fd.append('file', file);
      const resp = await fetch(`${PLATFORM}/mdm-app/versions/${versionId}/package`, {
        method: 'POST',
        headers,
        body: fd
      });
      let data;
      try { data = await resp.json(); } catch { throw new Error('服务器响应异常'); }
      if (resp.status === 401 || data.code === 401) {
        clearSession();
        if (!location.pathname.endsWith('/login.html')) location.href = '/login.html';
        throw new Error(data.message || '未登录');
      }
      if (data.code !== 0) throw new Error(data.message || '上传失败');
      return data.data;
    },

    listAdmins(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      q.set('page', String(params.page || 1));
      q.set('page_size', String(params.page_size || 12));
      return request(`${PLATFORM}/admins?${q.toString()}`);
    },
    getAdmin(id) {
      return request(`${PLATFORM}/admins/${id}`);
    },
    createAdmin(payload) {
      return encryptPassword(payload.password).then(cipher =>
        request(`${PLATFORM}/admins`, {
          method: 'POST',
          body: Object.assign({}, payload, { password: cipher })
        })
      );
    },
    updateAdmin(id, payload) {
      // 编辑不允许改密码
      const body = Object.assign({}, payload);
      delete body.password;
      delete body.username;
      return request(`${PLATFORM}/admins/${id}`, { method: 'PUT', body });
    },
    deleteAdmin(id) {
      return request(`${PLATFORM}/admins/${id}`, { method: 'DELETE' });
    },
    setAdminStatus(id, status) {
      return request(`${PLATFORM}/admins/${id}/status`, {
        method: 'PUT',
        body: { status }
      });
    },
    resetAdminPassword(id, password) {
      return encryptPassword(password).then(cipher =>
        request(`${PLATFORM}/admins/${id}/reset-password`, {
          method: 'POST',
          body: { password: cipher }
        })
      );
    },

    listRoles(keyword) {
      const q = keyword ? `?keyword=${encodeURIComponent(keyword)}` : '';
      return request(`${PLATFORM}/roles${q}`);
    },
    getRole(id) {
      return request(`${PLATFORM}/roles/${id}`);
    },
    createRole(payload) {
      return request(`${PLATFORM}/roles`, { method: 'POST', body: payload });
    },
    updateRole(id, payload) {
      return request(`${PLATFORM}/roles/${id}`, { method: 'PUT', body: payload });
    },
    deleteRole(id) {
      return request(`${PLATFORM}/roles/${id}`, { method: 'DELETE' });
    },
    setRoleStatus(id, status) {
      return request(`${PLATFORM}/roles/${id}/status`, {
        method: 'PUT',
        body: { status }
      });
    },

    listOpLogs(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      if (params.success === 0 || params.success === 1) q.set('success', String(params.success));
      q.set('page', String(params.page || 1));
      q.set('page_size', String(params.page_size || 10));
      return request(`${PLATFORM}/op-logs?${q.toString()}`);
    },
    getOpLog(id) {
      return request(`${PLATFORM}/op-logs/${id}`);
    },
    // ---------- 应用管理 ----------
    listApps(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      q.set('page', String(params.page || 1));
      q.set('page_size', String(params.page_size || 12));
      return request(`/platform/app?${q.toString()}`);
    },
    getApp(id) {
      return request(`/platform/app/${id}`);
    },
    createApp(payload) {
      return request('/platform/app', { method: 'POST', body: payload });
    },
    updateApp(id, payload) {
      return request(`/platform/app/${id}`, { method: 'PUT', body: payload });
    },
    deleteApp(id) {
      return request(`/platform/app/${id}`, { method: 'DELETE' });
    },
    listAppInstalls(appId, params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      q.set('page', String(params.page || 1));
      q.set('page_size', String(params.page_size || 20));
      return request(`/platform/app/${appId}/installs?${q.toString()}`);
    },
    listAppTargetGroups(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      const qs = q.toString();
      return request(`/platform/app/target-groups${qs ? `?${qs}` : ''}`);
    },
    batchInstallApp(appId, payload) {
      return request(`/platform/app/${appId}/batch-install`, { method: 'POST', body: payload });
    },
    batchUninstallApp(appId, payload) {
      return request(`/platform/app/${appId}/batch-uninstall`, { method: 'POST', body: payload });
    },
    createAppVersion(appId, payload) {
      return request(`/platform/app/${appId}/versions`, { method: 'POST', body: payload });
    },
    getAppVersion(appId, versionId) {
      return request(`/platform/app/${appId}/versions/${versionId}`);
    },
    updateAppVersion(appId, versionId, payload) {
      return request(`/platform/app/${appId}/versions/${versionId}`, { method: 'PUT', body: payload });
    },
    deleteAppVersion(appId, versionId) {
      return request(`/platform/app/${appId}/versions/${versionId}`, { method: 'DELETE' });
    },
    async uploadAppPackage(appId, versionId, file, opts = {}) {
      const headers = {};
      const token = getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
      const fd = new FormData();
      fd.append('file', file);
      const q = opts.resign ? '?resign=true' : '';
      const resp = await fetch(`/platform/app/${appId}/versions/${versionId}/package${q}`, {
        method: 'POST',
        headers,
        body: fd
      });
      let data;
      try { data = await resp.json(); } catch { throw new Error('服务器响应异常'); }
      if (resp.status === 401 || data.code === 401) {
        clearSession();
        if (!location.pathname.endsWith('/login.html')) location.href = '/login.html';
        throw new Error(data.message || '未登录');
      }
      if (data.code !== 0) throw new Error(data.message || '上传失败');
      return data.data;
    },
    resignAppPackage(appId, versionId) {
      return request(`/platform/app/${appId}/versions/${versionId}/resign`, {
        method: 'POST'
      });
    },
    async uploadAppIcon(appId, file) {
      const headers = {};
      const token = getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
      const fd = new FormData();
      fd.append('file', file);
      const resp = await fetch(`/platform/app/${appId}/icon`, {
        method: 'POST',
        headers,
        body: fd
      });
      let data;
      try { data = await resp.json(); } catch { throw new Error('服务器响应异常'); }
      if (resp.status === 401 || data.code === 401) {
        clearSession();
        if (!location.pathname.endsWith('/login.html')) location.href = '/login.html';
        throw new Error(data.message || '未登录');
      }
      if (data.code !== 0) throw new Error(data.message || '图标上传失败');
      return data.data;
    },
    clearAppIcon(appId) {
      return request(`/platform/app/${appId}/icon`, { method: 'DELETE' });
    },

    async exportOpLogs(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      if (params.success === 0 || params.success === 1) q.set('success', String(params.success));
      const headers = {};
      const token = getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
      const resp = await fetch(`${PLATFORM}/op-logs/export?${q.toString()}`, { headers });
      if (resp.status === 401) {
        clearSession();
        if (!location.pathname.endsWith('/login.html')) location.href = '/login.html';
        throw new Error('未登录');
      }
      if (!resp.ok) {
        let msg = '导出失败';
        try {
          const data = await resp.json();
          msg = data.message || msg;
        } catch { /* ignore */ }
        throw new Error(msg);
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'op-logs.csv';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    },

    // ---------- 成员分组 ----------
    listMemberGroups(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      return request(`/platform/member-group/groups?${q.toString()}`);
    },
    getMemberGroup(id) {
      return request(`/platform/member-group/groups/${id}`);
    },
    createMemberGroup(payload) {
      return request('/platform/member-group/groups', { method: 'POST', body: payload });
    },
    updateMemberGroup(id, payload) {
      return request(`/platform/member-group/groups/${id}`, { method: 'PUT', body: payload });
    },
    deleteMemberGroup(id) {
      return request(`/platform/member-group/groups/${id}`, { method: 'DELETE' });
    },

    // ---------- 人员管理 ----------
    listMembers(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      if (params.department_id) q.set('department_id', String(params.department_id));
      if (params.bind) q.set('bind', String(params.bind));
      q.set('page', String(params.page || 1));
      q.set('page_size', String(params.page_size || 20));
      return request(`/platform/member?${q.toString()}`);
    },
    /** 人员表单用分组树（人员菜单权限即可） */
    listMemberGroupOptions(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      return request(`/platform/member/groups?${q.toString()}`);
    },
    getMember(id) {
      return request(`/platform/member/${id}`);
    },
    createMember(payload) {
      return encryptPassword(payload.password).then(cipher =>
        request('/platform/member', {
          method: 'POST',
          body: Object.assign({}, payload, { password: cipher })
        })
      );
    },
    updateMember(id, payload) {
      return request(`/platform/member/${id}`, { method: 'PUT', body: payload });
    },
    deleteMember(id) {
      return request(`/platform/member/${id}`, { method: 'DELETE' });
    },
    async downloadMemberImportTemplate() {
      const headers = {};
      const token = getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
      const resp = await fetch('/platform/member/import/template', { headers });
      if (resp.status === 401) {
        clearSession();
        if (!location.pathname.endsWith('/login.html')) location.href = '/login.html';
        throw new Error('未登录');
      }
      if (!resp.ok) {
        let msg = '模板下载失败';
        try {
          const data = await resp.json();
          msg = data.message || msg;
        } catch { /* ignore */ }
        throw new Error(msg);
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'member-import-template.xlsx';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    },
    async importMembers(file) {
      const headers = {};
      const token = getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
      const fd = new FormData();
      fd.append('file', file);
      const resp = await fetch('/platform/member/import', {
        method: 'POST',
        headers,
        body: fd
      });
      let data;
      try { data = await resp.json(); } catch { throw new Error('服务器响应异常'); }
      if (resp.status === 401 || data.code === 401) {
        clearSession();
        if (!location.pathname.endsWith('/login.html')) location.href = '/login.html';
        throw new Error(data.message || '未登录');
      }
      if (data.code !== 0) throw new Error(data.message || '导入失败');
      return data.data;
    },

    // ---------- 设备管理 ----------
    listDevices(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      if (params.status) q.set('status', params.status);
      if (params.bind) q.set('bind', params.bind);
      if (params.compliance) q.set('compliance', params.compliance);
      q.set('page', String(params.page || 1));
      q.set('page_size', String(params.page_size || 20));
      return request(`/platform/device?${q.toString()}`);
    },
    getDevice(sn) {
      return request(`/platform/device/${encodeURIComponent(sn)}`);
    },
    /** 预登记单台设备（仅 SN） */
    createDevice(sn) {
      return request('/platform/device', {
        method: 'POST',
        body: { sn: String(sn || '').trim() }
      });
    },
    /** 批量预登记；部分失败不回滚，返回 created / failed */
    batchCreateDevices(sns) {
      return request('/platform/device/batch', {
        method: 'POST',
        body: { sns: Array.isArray(sns) ? sns : [] }
      });
    },
    /** 删除未绑定设备 */
    deleteDevice(sn) {
      return request(`/platform/device/${encodeURIComponent(sn)}`, { method: 'DELETE' });
    },
    /** 不合规设备补发 STRATEGY_PULL */
    notifyDeviceStrategyPull(sn) {
      return request(`/platform/device/${encodeURIComponent(sn)}/strategy-pull`, {
        method: 'POST'
      });
    },
    /** 催设备完整上报 SNAPSHOT_REPORT（基本信息 / 已装应用 / 策略快照） */
    notifyDeviceSnapshotReport(sn) {
      return request(`/platform/device/${encodeURIComponent(sn)}/snapshot-report`, {
        method: 'POST'
      });
    },
    /** 管理员解绑（需登录；设备侧不再提供解绑接口） */
    unbindDevice(sn) {
      return request(`/platform/device/${encodeURIComponent(sn)}/unbind`, {
        method: 'POST'
      });
    },
    getDeviceSnapshot(sn) {
      return request(`/platform/device/${encodeURIComponent(sn)}/snapshot`);
    },
    listDeviceApps(sn) {
      return request(`/platform/device/${encodeURIComponent(sn)}/apps`);
    },
    listDeviceLocations(sn, params = {}) {
      const q = new URLSearchParams();
      q.set('page', String(params.page || 1));
      q.set('page_size', String(params.page_size || 20));
      return request(
        `/platform/device/${encodeURIComponent(sn)}/locations?${q.toString()}`
      );
    },
    /** 设备绑定成员业务卡片：kind=mine|todo */
    listDeviceBizCards(sn, params = {}) {
      const q = new URLSearchParams();
      q.set('kind', String(params.kind || 'mine'));
      q.set('page', String(params.page || 1));
      q.set('page_size', String(params.page_size || 20));
      return request(
        `/platform/device/${encodeURIComponent(sn)}/biz-cards?${q.toString()}`
      );
    },
    /** 业务卡片详情（完整步骤） */
    getDeviceBizCard(sn, bizId) {
      return request(
        `/platform/device/${encodeURIComponent(sn)}/biz-cards/${encodeURIComponent(bizId)}`
      );
    },
    /** 设备远程控制：reboot | shutDown | lockScreen | DISK_ERASURE */
    controlDevice(sn, controlType) {
      return request(`/platform/device/${encodeURIComponent(sn)}/control`, {
        method: 'POST',
        body: { control_type: String(controlType || '') }
      });
    },

    // ---------- 初始策略模板 ----------
    listInitialPolicies(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      q.set('page', String(params.page || 1));
      q.set('page_size', String(params.page_size || 50));
      return request(`/platform/member-group/initial-policies?${q.toString()}`);
    },
    getInitialPolicy(id) {
      return request(`/platform/member-group/initial-policies/${id}`);
    },
    createInitialPolicy(payload) {
      return request('/platform/member-group/initial-policies', { method: 'POST', body: payload });
    },
    updateInitialPolicy(id, payload) {
      return request(`/platform/member-group/initial-policies/${id}`, { method: 'PUT', body: payload });
    },
    deleteInitialPolicy(id) {
      return request(`/platform/member-group/initial-policies/${id}`, { method: 'DELETE' });
    },

    // ---------- 策略下发 ----------
    listPolicyTasks(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      if (params.op_type) q.set('op_type', params.op_type);
      if (params.start_date) q.set('start_date', params.start_date);
      if (params.end_date) q.set('end_date', params.end_date);
      q.set('page', String(params.page || 1));
      q.set('page_size', String(params.page_size || 20));
      return request(`/platform/policy/tasks?${q.toString()}`);
    },
    getPolicyTask(id) {
      return request(`/platform/policy/tasks/${id}`);
    },
    listPolicyTaskDevices(id, params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      if (params.status) q.set('status', params.status);
      q.set('page', String(params.page || 1));
      q.set('page_size', String(params.page_size || 20));
      return request(`/platform/policy/tasks/${id}/devices?${q.toString()}`);
    },
    listDeviceStrategySync(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      if (params.match) q.set('match', params.match);
      q.set('page', String(params.page || 1));
      q.set('page_size', String(params.page_size || 20));
      return request(`/platform/policy/device-sync?${q.toString()}`);
    },
    createPolicyTask(payload) {
      return request('/platform/policy/tasks', { method: 'POST', body: payload });
    },
    /** 手动选人：仅已绑定设备的成员 */
    listPolicyTargetMembers(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      q.set('page', String(params.page || 1));
      q.set('page_size', String(params.page_size || 50));
      return request(`/platform/policy/targets/members?${q.toString()}`);
    },

    /** 数据看板总览 */
    getDashboardOverview() {
      return request('/platform/dashboard/overview');
    },

    // ---------- 知识库问答（RAG）----------
    listRagKnowledgeBases(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      return request(`/platform/rag/knowledge-bases?${q.toString()}`);
    },
    getRagKnowledgeBase(id) {
      return request(`/platform/rag/knowledge-bases/${id}`);
    },
    createRagKnowledgeBase(payload) {
      return request('/platform/rag/knowledge-bases', { method: 'POST', body: payload });
    },
    updateRagKnowledgeBase(id, payload) {
      return request(`/platform/rag/knowledge-bases/${id}`, { method: 'PUT', body: payload });
    },
    deleteRagKnowledgeBase(id) {
      return request(`/platform/rag/knowledge-bases/${id}`, { method: 'DELETE' });
    },
    listRagFiles(kbId, params = {}) {
      const q = new URLSearchParams();
      q.set('page', String(params.page || 1));
      q.set('page_size', String(params.page_size || 20));
      return request(`/platform/rag/knowledge-bases/${kbId}/files?${q.toString()}`);
    },
    async uploadRagFile(kbId, file) {
      const items = await this.uploadRagFiles(kbId, [file]);
      return Array.isArray(items) ? items[0] : items;
    },
    /** 批量上传知识库文件（同库服务端串行解析排队） */
    async uploadRagFiles(kbId, fileList) {
      const token = getToken();
      const files = Array.from(fileList || []).filter(Boolean);
      if (!files.length) throw new Error('请选择要上传的文件');
      const fd = new FormData();
      files.forEach(f => fd.append('files', f));
      const resp = await fetch(`/platform/rag/knowledge-bases/${kbId}/files/upload`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd
      });
      let data;
      try {
        data = await resp.json();
      } catch {
        throw new Error('服务器响应异常');
      }
      if (resp.status === 401 || data.code === 401) {
        clearSession();
        if (!location.pathname.endsWith('/login.html')) location.href = '/login.html';
        throw new Error(data.message || '未登录');
      }
      if (data.code !== 0) throw new Error(data.message || '上传失败');
      return data.data;
    },
    deleteRagFile(kbId, fileId) {
      return request(`/platform/rag/knowledge-bases/${kbId}/files/${fileId}`, { method: 'DELETE' });
    },
    listRagFileChunks(kbId, fileId) {
      return request(`/platform/rag/knowledge-bases/${kbId}/files/${fileId}/chunks`);
    },
    updateRagFileChunk(kbId, fileId, chunkId, text) {
      return request(
        `/platform/rag/knowledge-bases/${kbId}/files/${fileId}/chunks/${encodeURIComponent(chunkId)}`,
        { method: 'PUT', body: { text } }
      );
    },
    ragAsk(payload) {
      return request('/platform/rag/ask', { method: 'POST', body: payload });
    },
    /**
     * 管理台流式提问（SSE）。
     * handlers: onStatus / onMeta / onDelta / onFinal / onError
     * 返回最终 final 载荷（与 ragAsk data 同构）；失败抛错。
     */
    async ragAskStream(payload, handlers = {}) {
      const token = getToken();
      const headers = {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream'
      };
      if (token) headers.Authorization = `Bearer ${token}`;

      const resp = await fetch('/platform/rag/ask/stream', {
        method: 'POST',
        headers,
        body: JSON.stringify(payload || {})
      });

      if (resp.status === 401) {
        clearSession();
        if (!location.pathname.endsWith('/login.html')) {
          location.href = '/login.html';
        }
        throw new Error('未登录');
      }
      if (!resp.ok) {
        let msg = `提问失败 (${resp.status})`;
        try {
          const errBody = await resp.json();
          if (errBody && errBody.message) msg = errBody.message;
        } catch (_) { /* ignore */ }
        throw new Error(msg);
      }
      if (!resp.body) throw new Error('浏览器不支持流式响应');

      const reader = resp.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let finalData = null;
      let streamError = null;

      const dispatch = (eventName, data) => {
        if (eventName === 'status' && handlers.onStatus) handlers.onStatus(data);
        else if (eventName === 'meta' && handlers.onMeta) handlers.onMeta(data);
        else if (eventName === 'answer_delta' && handlers.onDelta) {
          handlers.onDelta(data && data.text != null ? String(data.text) : '');
        } else if (eventName === 'final') {
          finalData = data;
          if (handlers.onFinal) handlers.onFinal(data);
        } else if (eventName === 'error') {
          streamError = (data && data.message) || '提问失败';
          if (handlers.onError) handlers.onError(streamError);
        }
      };

      const flushBlock = (block) => {
        const lines = block.split(/\r?\n/);
        let eventName = 'message';
        const dataLines = [];
        lines.forEach(line => {
          if (line.startsWith('event:')) {
            eventName = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            dataLines.push(line.slice(5).trim());
          }
        });
        if (!dataLines.length) return;
        let parsed = {};
        try {
          parsed = JSON.parse(dataLines.join('\n'));
        } catch (_) {
          parsed = { raw: dataLines.join('\n') };
        }
        dispatch(eventName, parsed);
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let sep;
        while ((sep = buffer.search(/\r?\n\r?\n/)) >= 0) {
          const block = buffer.slice(0, sep);
          buffer = buffer.slice(sep).replace(/^\r?\n\r?\n/, '');
          if (block.trim()) flushBlock(block);
        }
      }
      if (buffer.trim()) flushBlock(buffer);

      if (streamError) throw new Error(streamError);
      if (!finalData) throw new Error('流式回答未完整结束');
      return finalData;
    },

    /* ---- 应用管理 · 证书（接口仍挂 /platform/store） ---- */
    listStoreCerts() {
      return request('/platform/store/certs');
    },
    getStoreSignStatus() {
      return request('/platform/store/sign-status');
    },
    listAppCertOptions() {
      return request('/platform/app/cert-options');
    },
    listAppProfiles(appId) {
      return request(`/platform/app/${appId}/profiles`);
    },
    createAppProfile(appId, payload) {
      return request(`/platform/app/${appId}/profiles`, {
        method: 'POST',
        body: payload
      });
    },
    deleteAppProfile(appId, profileId) {
      return request(`/platform/app/${appId}/profiles/${profileId}`, {
        method: 'DELETE'
      });
    },
    /* ---- 应用商店调试遗留（侧栏已隐藏） ---- */
    async addStoreCert(certName, file) {
      const headers = {};
      const token = getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
      const fd = new FormData();
      fd.append('cert_name', certName);
      fd.append('file', file);
      const resp = await fetch('/platform/store/certs', {
        method: 'POST',
        headers,
        body: fd
      });
      let data;
      try { data = await resp.json(); } catch { throw new Error('服务器响应异常'); }
      if (resp.status === 401 || data.code === 401) {
        clearSession();
        if (!location.pathname.endsWith('/login.html')) location.href = '/login.html';
        throw new Error(data.message || '未登录');
      }
      if (data.code !== 0) throw new Error(data.message || '上传失败');
      return data.data;
    },
    deleteStoreCert(id) {
      return request(`/platform/store/certs/${id}`, { method: 'DELETE' });
    },
    listStoreApps(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      q.set('page', String(params.page || 1));
      q.set('page_size', String(params.page_size || 12));
      return request(`/platform/store/apps?${q.toString()}`);
    },
    getStoreApp(id) {
      return request(`/platform/store/apps/${id}`);
    },
    createStoreApp(payload) {
      return request('/platform/store/apps', { method: 'POST', body: payload });
    },
    updateStoreApp(id, payload) {
      return request(`/platform/store/apps/${id}`, { method: 'PUT', body: payload });
    },
    deleteStoreApp(id) {
      return request(`/platform/store/apps/${id}`, { method: 'DELETE' });
    },
    async uploadStoreAppIcon(appId, file) {
      const headers = {};
      const token = getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
      const fd = new FormData();
      fd.append('file', file);
      const resp = await fetch(`/platform/store/apps/${appId}/icon`, {
        method: 'POST',
        headers,
        body: fd
      });
      let data;
      try { data = await resp.json(); } catch { throw new Error('服务器响应异常'); }
      if (resp.status === 401 || data.code === 401) {
        clearSession();
        if (!location.pathname.endsWith('/login.html')) location.href = '/login.html';
        throw new Error(data.message || '未登录');
      }
      if (data.code !== 0) throw new Error(data.message || '上传失败');
      return data.data;
    },
    listStoreVersions(appId) {
      return request(`/platform/store/apps/${appId}/versions`);
    },
    async createStoreVersion(appId, { versionName, versionCode, file }) {
      const headers = {};
      const token = getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
      const fd = new FormData();
      fd.append('version_name', versionName);
      fd.append('version_code', versionCode);
      fd.append('file', file);
      const resp = await fetch(`/platform/store/apps/${appId}/versions`, {
        method: 'POST',
        headers,
        body: fd
      });
      let data;
      try { data = await resp.json(); } catch { throw new Error('服务器响应异常'); }
      if (resp.status === 401 || data.code === 401) {
        clearSession();
        if (!location.pathname.endsWith('/login.html')) location.href = '/login.html';
        throw new Error(data.message || '未登录');
      }
      if (data.code !== 0) throw new Error(data.message || '上传失败');
      return data.data;
    },
    deleteStoreVersion(appId, versionId) {
      return request(`/platform/store/apps/${appId}/versions/${versionId}`, {
        method: 'DELETE'
      });
    },
    listStoreProfiles(appId) {
      return request(`/platform/store/apps/${appId}/profiles`);
    },
    createStoreProfile(appId, payload) {
      return request(`/platform/store/apps/${appId}/profiles`, {
        method: 'POST',
        body: payload
      });
    },
    deleteStoreProfile(appId, profileId) {
      return request(`/platform/store/apps/${appId}/profiles/${profileId}`, {
        method: 'DELETE'
      });
    },
    async downloadStoreFile(url, filename) {
      const headers = {};
      const token = getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
      const resp = await fetch(url, { headers });
      if (resp.status === 401) {
        clearSession();
        if (!location.pathname.endsWith('/login.html')) location.href = '/login.html';
        throw new Error('未登录');
      }
      if (!resp.ok) {
        let msg = '下载失败';
        try {
          const j = await resp.json();
          if (j && j.message) msg = j.message;
        } catch { /* binary or empty */ }
        throw new Error(msg);
      }
      const blob = await resp.blob();
      const a = document.createElement('a');
      const obj = URL.createObjectURL(blob);
      a.href = obj;
      a.download = filename || 'download';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(obj), 2000);
    }
  };
})();
