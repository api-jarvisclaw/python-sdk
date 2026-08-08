# NOTES

## 2026-08-08 — NetworkClient docstring 对公开注册表的认证要求过度承诺

### 目标
生产 SDK 端到端实测的顺带修复。实测时 `NetworkClient` 无法按它自己 docstring 描述的方式构造出来。

### 症状与根因
`jarvisclaw/network.py` 的 `NetworkClient` docstring 写着公开注册表（search / servers / resources）"needs no auth at all"，但它继承的 `BaseClient` 在既无 `api_key` 也无 `private_key` 时直接 `raise ValueError`。照文档写的代码根本构造不出实例 —— e2e 时我不得不塞一个占位 key 才跑起来。

文档把**服务端不校验凭证**说成了**客户端不需要凭证**，这是两件事。

### 关键决策及理由
**改文档，不改构造器。** 我最初的判断是"构造器强制凭证"属缺陷，探测后被推翻：

- go SDK 的 `NewClient` 在无凭证时同样返错 —— 这是刻意维持的跨语言一致契约
- python 侧有三个测试用 `match="api_key or private_key"` 明确锚定了这个行为：`test_agent.py:31`、`test_imports.py:37`、`test_dual_credentials.py:76`

放宽构造器会破这三个测试并打破跨语言一致性；改文档一行即可。真正错的是那句话，不是那段代码。

新措辞明确区分了两层：公开注册表服务端不做凭证校验（任何 key 都能到、响应对所有人一致），但构造器仍然要一个凭证，与后续调用哪些端点无关。

### 被否方案
- **给 `BaseClient` 加 `allow_anonymous` 开关 / 引入 `NoAuth` 策略**：否。为一句错误的文档新增公开 API 面，代价与收益完全不成比例，还得同步 go SDK 才能保持一致。

### 验证
- 契约测试 190 passed
- `ruff check jarvisclaw/network.py` → All checks passed
- `inspect.getdoc(jarvisclaw.NetworkClient)` 确认新文案已生效
- 全文 `no auth` / `needs no` 残留检查 → 0 处；共统一 4 处措辞（class docstring、注册表节标题、`health` 与 `list_apis` 的方法 docstring），避免只改一处留下自相矛盾

### 已知既有失败（与本次改动无关）
- `tests/test_targeted.py` 9 failed：这些用例需要 `JARVISCLAW_API_KEY` 环境变量，未设置。用 `git stash` 取基线对比，改动前后**逐条一致**，非本次引入。
- `ruff` E721（类型用 `==` 比较）全在 `agent.py`，既有问题，不在本次改动面内。

### 坑
`subprocess` 里不要用 `sys.executable` 跑 pytest/ruff：本机它指向 `pythonw.exe`（无控制台），会吞掉 stderr，表现为 ruff 明明 exit 1 却一行输出都没有。替换成 `python.exe` 才拿得到真实报错。

### 未验证项
- 没有实测"公开注册表用任意有效 key 都返回相同响应"这一说法的后半句，只验证了占位 key 能到达端点。新 docstring 中"响应对所有人一致"是基于服务端白标脱敏逻辑的推断。
