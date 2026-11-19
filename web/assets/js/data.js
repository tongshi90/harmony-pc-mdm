/** 前端公共静态配置（导航 / 品牌）；业务数据一律走 API */
window.MDM = {
  platform: {
    name: '企业终端管控平台',
    brand: '企业终端管控平台',
    fullName: '企业终端管控平台',
    version: '0.3.0-beta'
  },
  user: { name: '', role: '', dept: '' },

  // 顶栏顺序：数据看板优先，其余按常用度；与后端 MenuCode.sort 对齐，按登录用户 menu_codes 过滤
  nav: [
    { group: '运营', items: [
      { id: 'dashboard', code: 'dashboard', label: '数据看板', href: '/index.html' }
    ]},
    { group: '终端', items: [
      { id: 'device', code: 'device', label: '设备管理', href: '/pages/devices/devices.html' },
      { id: 'member', code: 'member', label: '人员管理', href: '/pages/members/members.html' },
      { id: 'member_group', code: 'member_group', label: '成员分组', href: '/pages/members/groups.html' },
      { id: 'app', code: 'app', label: '应用管理', href: '/pages/apps/apps.html' },
      { id: 'policy_dispatch', code: 'policy_dispatch', label: '策略记录', href: '/pages/scenes/scene-dispatch.html' },
      { id: 'rag', code: 'rag', label: '知识库问答', href: '/pages/rag/knowledge-bases.html' }
    ]},
    { group: '平台', items: [
      { id: 'platform', code: 'platform', label: '平台基础管理', href: '/pages/platform/users.html' }
    ]}
  ],

  /** 按顶栏顺序取第一个有权限的入口；无权限时落到看板页（由布局展示空状态） */
  resolveHomeHref(menuCodes) {
    const set = new Set(menuCodes || []);
    for (const g of this.nav || []) {
      for (const item of g.items || []) {
        if (set.has(item.code || item.id)) return item.href;
      }
    }
    return '/index.html';
  },

  /**
   * 内置指令目录：由 policy-commands.js 按协议覆盖填充。
   * 保留空数组，避免脚本加载顺序导致取不到属性。
   */
  commands: [],
  policyCommands: []
};
