/**
 * 端云协议《指令详情》预制策略/指令目录
 * 来源：E:\Desktop\端云协议.docx · 指令详情章节
 * 用途：策略下发 / 初始策略参数表单
 *
 * 约定：
 * - code：平台侧唯一标识（卡片路由用）
 * - protocolKey / protocolCode：下发 JSON 中的键与值（commandCode 或 sceneCode）
 * - params[].type：string | long | enum | array_string | array_object | file
 * - enum 用 options: [{ value, label }]，label 为协议字段说明中的中文释义
 */
(function () {
  const E = (value, label) => ({ value, label });

  const POLICY_COMMANDS = [
    {
      code: 'WIFI_SET',
      name: 'Wifi配置',
      protocolKey: 'commandCode',
      protocolCode: 'WIFI_SET',
      category: '网络',
      pending: false,
      desc: '根据配置执行 WIFI 连接',
      sceneDesc: '根据配置进行执行WIFI的连接',
      businessLogic: '如果已经连接这个WIFI直接返回成功，没有连接则调用MDM Kit接口进行配置',
      verifyMethod: '检查电脑是否正常连接指定WIFI',
      params: [
        {
          key: 'ssid', type: 'string', label: 'ssid', required: true,
          desc: 'Wi-Fi热点名称'
        },
        {
          key: 'bssid', type: 'string', label: 'bssid', required: false,
          alwaysShow: true,
          desc: 'Wi-Fi热点的MAC地址，长度6个字节，例如：00:11:22:33:44:55',
          placeholder: '00:11:22:33:44:55'
        },
        {
          key: 'preSharedKey', type: 'string', label: 'preSharedKey', required: false,
          alwaysShow: true,
          desc: '热点的密钥，用于Wi-Fi连接认证。安全类型为 WIFI_SEC_TYPE_OPEN 时允许为空'
        },
        {
          key: 'securityType', type: 'enum', label: 'securityType', required: true,
          desc: '安全类型',
          default: 'WIFI_SEC_TYPE_SAE',
          options: [
            E('WIFI_SEC_TYPE_INVALID', '无效加密类型。例如机场公共Wi-Fi'),
            E('WIFI_SEC_TYPE_OPEN', '开放加密类型'),
            E('WIFI_SEC_TYPE_WEP', 'Wired Equivalent Privacy (WEP)加密类型'),
            E('WIFI_SEC_TYPE_PSK', 'Pre-shared key (PSK)加密类型。例如家庭、小型办公室Wi-Fi'),
            E('WIFI_SEC_TYPE_SAE', 'SAE加密类型。例如智能家居、中小型企业网络'),
            E('WIFI_SEC_TYPE_EAP', 'EAP加密类型。例如大型企业认证、大学校园网络等'),
            E('WIFI_SEC_TYPE_EAP_SUITE_B', 'Suite-B 192位加密类型。适用于政府和高安全机构'),
            E('WIFI_SEC_TYPE_OWE', '机会性无线加密类型。例如咖啡馆公共Wi-Fi'),
            E('WIFI_SEC_TYPE_WAPI_CERT', 'WAPI-Cert加密类型。中国自主的无线安全标准'),
            E('WIFI_SEC_TYPE_WAPI_PSK', 'WAPI-PSK加密类型')
          ]
        },
        // 以下仅 securityType = WIFI_SEC_TYPE_EAP 时显示
        {
          key: 'eapMethod', type: 'enum', label: 'eapMethod', required: false,
          desc: '企业 Wi-Fi 的 EAP 认证方式',
          default: 'EAP_NONE',
          visibleWhen: { securityType: 'WIFI_SEC_TYPE_EAP' },
          options: [
            E('EAP_NONE', '不指定'),
            E('EAP_PEAP', 'PEAP类型，受保护的可扩展认证协议。先建立安全的TLS隧道、然后进行简单认证'),
            E('EAP_TLS', 'TLS类型，传输层安全协议。双向证书认证'),
            E('EAP_TTLS', 'TTLS类型，隧道传输层安全协议。与PEAP类似，但后续隧道内部认证方法更加丰富'),
            E('EAP_PWD', 'PWD类型，密码认证。无需服务器证书'),
            E('EAP_SIM', 'SIM类型，使用手机SIM卡中的密钥和算法进行认证'),
            E('EAP_AKA', 'AKA类型，使用USIM卡（3G/4G/5G SIM卡）中的增强密钥和算法进行认证'),
            E('EAP_AKA_PRIME', 'AKA Prime类型，EAP-AKA增强版，在密钥派生中绑定网络名称'),
            E('EAP_UNAUTH_TLS', 'UNAUTH TLS类型，单向认证（仅认证客户端）和加密通道')
          ]
        },
        {
          key: 'identity', type: 'string', label: 'identity', required: false,
          desc: '登录身份。当认证方式为 TLS 时不能为空',
          visibleWhen: { securityType: 'WIFI_SEC_TYPE_EAP' }
        },
        {
          key: 'phase2Method', type: 'enum', label: 'phase2Method', required: false,
          desc: '第二阶段认证方式',
          default: 'PHASE2_NONE',
          visibleWhen: { securityType: 'WIFI_SEC_TYPE_EAP' },
          options: [
            E('PHASE2_NONE', '不指定'),
            E('PHASE2_PAP', 'PAP类型'),
            E('PHASE2_MSCHA', 'MSCHAP类型'),
            E('PHASE2_MSCHAPV2', 'MSCHAPV2类型'),
            E('PHASE2_GTC', 'GTC类型'),
            E('PHASE2_SIM', 'SIM类型'),
            E('PHASE2_AKA', 'AKA类型'),
            E('PHASE2_AKA_PRIME', 'AKA Prime类型')
          ]
        },
        {
          key: 'password', type: 'string', label: 'password', required: false,
          desc: '认证密码。当认证方式为 PEAP 或 PWD 时不能为空，最长 128 字节',
          visibleWhen: { securityType: 'WIFI_SEC_TYPE_EAP' }
        },
        {
          key: 'certEntry', type: 'file', label: 'certEntry', required: false,
          accept: '.cer,.crt,.pem,.p12,.pfx,.cert,application/x-x509-ca-cert,application/x-pkcs12',
          desc: '上传客户端证书。当认证方式为 TLS 时一般需要提供',
          visibleWhen: { securityType: 'WIFI_SEC_TYPE_EAP' }
        },
        {
          key: 'certPassword', type: 'string', label: 'certPassword', required: false,
          desc: '证书密码（如有）',
          visibleWhen: { securityType: 'WIFI_SEC_TYPE_EAP' }
        }
      ],
      example: {
        commandCode: 'WIFI_SET',
        param: {
          ssid: 'TALKWEB',
          bssid: '00:11:22:33:44:55',
          preSharedKey: '123456',
          securityType: 'WIFI_SEC_TYPE_SAE',
          eapMethod: 'EAP_TTLS',
          identity: 'zhangsan@company.com',
          phase2Method: 'PHASE2_PAP',
          password: 'passwd',
          certEntry: '',
          certPassword: ''
        }
      }
    },
    {
      code: 'REMOTE_CONTROL',
      name: '远程操控设备',
      protocolKey: 'sceneCode',
      protocolCode: 'REMOTE_CONTROL',
      category: '远程管理',
      pending: true,
      desc: '对设备进行远程操控（锁屏、挂失、数据擦除等）',
      sceneDesc: '对设备进行远程操控',
      businessLogic: '直接进行指令操控，对设备进行远程操控，包含锁屏、挂失（解锁前无法操作）、数据擦除',
      verifyMethod: '指令执行后，检查设备是否会自动进入锁屏、挂失、数据擦除操作',
      note: '数据擦除之后，设备会回到初始状态（HEM 平台下发策略和 MDM 应用前）。此状态下设备必须重新连一次外网，才能被 HEM 平台检测到，再次下发初始策略以及 MDM 应用的安装。',
      params: [
        {
          key: 'operationType', type: 'enum', label: 'operationType', required: true,
          desc: '选择要对设备执行的远程操作',
          default: 'lockDevice',
          options: [
            E('lockDevice', '设备锁定'),
            E('unlockDevice', '设备解除锁定')
          ]
        }
      ],
      example: {
        sceneCode: 'REMOTE_CONTROL',
        param: { operationType: 'lockDevice' }
      }
    },
    {
      code: 'LOCATION_POLICY',
      name: '是否允许定位',
      protocolKey: 'sceneCode',
      protocolCode: 'LOCATION_POLICY',
      category: '定位',
      pending: false,
      desc: '限制设备是否允许定位',
      sceneDesc: '对设备进行设置，限制是否允许定位',
      businessLogic: '直接进行指令操控，对设备是否允许定位进行调整。如果配置已经是指定策略，则不需要做任何处理',
      verifyMethod: '设置之后，检查设备是否能够进行定位。禁止位置服务后无法手动打开；强制开启后无法手动关闭；默认策略可自行开关。并检查开启/关闭后是否与预期一样可以/无法获取当前位置。',
      params: [
        {
          key: 'policyType', type: 'enum', label: 'policyType', required: true,
          desc: '选择设备位置服务策略',
          default: 'DEFAULT',
          options: [
            E('DEFAULT', '默认策略，用户可自行打开/关闭位置服务'),
            E('DISALLOW', '禁用位置服务'),
            E('FORCE_OPEN', '强制开启位置服务')
          ]
        }
      ],
      example: {
        sceneCode: 'LOCATION_POLICY',
        param: { policyType: 'DEFAULT' }
      }
    },
    {
      code: 'APP_MANAGEMENT',
      name: '应用安装管理',
      protocolKey: 'sceneCode',
      protocolCode: 'APP_MANAGEMENT',
      category: '应用',
      pending: true,
      desc: '按列表安装/更新应用，并卸载指定应用',
      sceneDesc: '根据证书列表进行应用的管理',
      businessLogic: '获取当前设备安装的应用及版本，并参考应用列表，对缺少的应用进行安装；uninstallApps 中的应用执行卸载；已安装的应用如果版本比指定版本低的也进行更新（版本更高的不做处理）',
      verifyMethod: '设置之后，检查设备是否按照预期进行了应用的安装、更新或卸载',
      note: '可能会导致手动安装的应用被卸载。',
      params: [
        {
          key: 'currentApps', type: 'app_install_select', label: 'currentApps', required: false,
          desc: '选择需要安装或更新的应用及版本；包名与下载地址由应用管理自动带出。不选则表示暂不安装'
        },
        {
          key: 'uninstallApps', type: 'app_multi_select', valueField: 'bundleName', label: 'uninstallApps', required: false,
          desc: '从应用管理中多选需要卸载的应用（按下发 bundleName）；不选则传空列表'
        }
      ],
      example: {
        sceneCode: 'APP_MANAGEMENT',
        param: {
          currentApps: [],
          uninstallApps: []
        }
      }
    },
    {
      code: 'APP_CONFIG_MANAGEMENT',
      name: '应用配置管理',
      protocolKey: 'sceneCode',
      protocolCode: 'APP_CONFIG_MANAGEMENT',
      category: '应用',
      pending: false,
      desc: '应用安装白/黑名单与禁止卸载名单',
      sceneDesc: '根据配置对应用的安装、卸载进行限制',
      businessLogic: '直接进行指令操控，将通过 MDM Kit 对应用的黑名单、白名单、禁止卸载名单进行更新（以前的配置信息被替换）',
      verifyMethod: '设置之后，检查设备进行应用的安装/卸载时候是否会被限制',
      params: [
        {
          key: 'allowAppIds', type: 'app_multi_select', valueField: 'appId', valueShape: 'appRef',
          label: 'allowAppIds', required: false,
          desc: '从应用管理中多选允许安装的应用；下发为 {appId, appName}，便于设备侧展示'
        },
        {
          key: 'disallowAppIds', type: 'app_multi_select', valueField: 'appId', valueShape: 'appRef',
          label: 'disallowAppIds', required: false,
          desc: '从应用管理中多选禁止安装的应用；下发为 {appId, appName}'
        },
        {
          key: 'disallowedUninstallAppIds', type: 'app_multi_select', valueField: 'appId', valueShape: 'appRef',
          label: 'disallowedUninstallAppIds', required: false,
          desc: '从应用管理中多选禁止卸载的应用；下发为 {appId, appName}'
        }
      ],
      example: {
        sceneCode: 'APP_CONFIG_MANAGEMENT',
        param: {
          allowAppIds: [{ appId: '0001', appName: '企业邮箱' }],
          disallowAppIds: [],
          disallowedUninstallAppIds: []
        }
      }
    },
    {
      code: 'DOMAIN_MANAGEMENT',
      name: '禁止访问网站域名',
      protocolKey: 'sceneCode',
      protocolCode: 'DOMAIN_MANAGEMENT',
      category: '网络',
      pending: false,
      desc: '限制设备访问指定网站域名',
      sceneDesc: '对设备访问网站域名进行限制',
      businessLogic: '直接进行指令操控，将通过 MDM Kit 对设备的域名访问进行限制（以前的配置信息被替换）',
      verifyMethod: '设置之后，检查设备是否还能访问指定域名的网页',
      params: [
        {
          key: 'domainNames', type: 'array_string', label: 'domainNames', required: false,
          desc: '禁止访问的域名数组，为空时传递空数组 []',
          placeholder: '每行一个域名，例如：\nwww.baidu.com'
        }
      ],
      example: {
        sceneCode: 'DOMAIN_MANAGEMENT',
        param: { domainNames: ['www.baidu.com'] }
      }
    },
    {
      code: 'FIREWALL_MANAGEMENT',
      name: '防火墙配置',
      protocolKey: 'sceneCode',
      protocolCode: 'FIREWALL_MANAGEMENT',
      category: '安全合规',
      pending: false,
      desc: '配置设备防火墙规则',
      sceneDesc: '对设备防火墙配置限制',
      businessLogic: '直接进行指令操控，将通过 MDM Kit 对设备防火墙配置进行更新（以前的配置信息被替换）',
      verifyMethod: '设置之后，检查是否还能与指定 IP/端口进行连接/被连接',
      params: [
        {
          key: 'firewalls', type: 'firewall_rules', label: 'firewalls', required: false,
          desc: '逐条添加拦截规则；不添加则下发空列表。地址支持单 IP（如 10.1.1.1）或 IP 段（如 192.168.1.1-192.168.22.66）'
        }
      ],
      example: {
        sceneCode: 'FIREWALL_MANAGEMENT',
        param: {
          firewalls: [{
            srcAddr: '192.168.1.1-192.168.22.66',
            destAddr: '10.1.1.1',
            srcPort: '8080',
            destPort: '8089'
          }]
        }
      }
    },
    {
      code: 'PSW_MANAGEMENT',
      name: '密码策略',
      protocolKey: 'sceneCode',
      protocolCode: 'PSW_MANAGEMENT',
      category: '安全合规',
      pending: false,
      desc: '约束设备开机密码规则',
      sceneDesc: '根据配置对设备的开机密码规则进行约束',
      businessLogic: '直接进行指令操控，将通过 MDM Kit 对设备开机密码规则进行限制（以前的配置信息被替换）',
      verifyMethod: '设置之后，检查设备设置开机密码的时候，是否被限制以及提示文案是否与预期一致',
      params: [
        {
          key: 'complexityRegex', type: 'string', label: 'complexityRegex', required: false,
          desc: '口令复杂程度的正则表达式',
          placeholder: '^[A-Za-z0-9]{6,18}$'
        },
        {
          key: 'validityPeriod', type: 'days_ms', label: 'validityPeriod', required: false,
          desc: '按天填写；写入设备预期快照时后端换算为毫秒',
          placeholder: '30',
          default: 30
        },
        {
          key: 'additionalDescription', type: 'string', label: 'additionalDescription', required: false,
          desc: '口令复杂度描述文案。例如：密码中必须包含字母、数字、特殊字符，至少8个字符，最多30个字符'
        }
      ],
      example: {
        sceneCode: 'PSW_MANAGEMENT',
        param: {
          complexityRegex: '^[A-Za-z0-9]{6,18}$',
          validityPeriod: 2592000000,
          additionalDescription: '密码中必须包含字母、数字、特殊字符，8-30个字符'
        }
      }
    },
    {
      code: 'USB_MANAGEMENT',
      name: 'U盘策略',
      protocolKey: 'sceneCode',
      protocolCode: 'USB_MANAGEMENT',
      category: '外设管控',
      pending: false,
      desc: '配置 U 盘使用策略',
      sceneDesc: '根据配置对U盘的使用策略进行配置',
      businessLogic: '直接进行指令操控，将通过 MDM Kit 对设备U盘策略进行更新（以前的配置信息被替换）',
      verifyMethod: '设置之后，连接外接U盘的时候，检查是否与预期效果一致',
      params: [
        {
          key: 'usbPolicy', type: 'enum', label: 'usbPolicy', required: true,
          desc: 'USB使用策略',
          default: 'READ_WRITE',
          options: [
            E('READ_WRITE', '可读可写'),
            E('READ_ONLY', '只读'),
            E('DISABLED', '禁用')
          ]
        }
      ],
      example: {
        sceneCode: 'USB_MANAGEMENT',
        param: { usbPolicy: 'READ_WRITE' }
      }
    }
  ];

  /** 面向使用用户的短标题（界面不展示协议字段名） */
  const TITLES = {
    ssid: 'Wi-Fi 热点名称',
    bssid: '热点 MAC 地址',
    preSharedKey: 'Wi-Fi 密码',
    securityType: '安全类型',
    eapMethod: '企业认证方式',
    identity: '登录身份',
    phase2Method: '第二阶段认证',
    password: '认证密码',
    certEntry: '客户端证书',
    certPassword: '证书密码',
    operationType: '操作类型',
    policyType: '定位策略',
    currentApps: '需要安装的应用',
    uninstallApps: '需要卸载的应用',
    allowAppIds: '允许安装的应用',
    disallowAppIds: '禁止安装的应用',
    disallowedUninstallAppIds: '禁止卸载的应用',
    domainNames: '禁止访问的域名',
    firewalls: '防火墙规则',
    complexityRegex: '密码复杂度规则',
    validityPeriod: '密码有效期（天）',
    additionalDescription: '密码要求说明',
    usbPolicy: 'U 盘使用策略'
  };

  POLICY_COMMANDS.forEach(cmd => {
    (cmd.params || []).forEach(p => {
      if (!p.title && TITLES[p.key]) p.title = TITLES[p.key];
    });
  });

  if (!window.MDM) window.MDM = {};
  MDM.policyCommands = POLICY_COMMANDS;
  /** 覆盖旧演示指令目录，供策略下发 / 初始策略统一引用 */
  MDM.commands = POLICY_COMMANDS;
})();
