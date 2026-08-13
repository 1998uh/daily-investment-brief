# 抖音采集器使用指南

## 功能说明

抖音采集器通过 Playwright 浏览器自动化技术采集抖音用户的视频列表。浏览器自动处理所有反爬签名参数（`a_bogus`、`msToken`、`verifyFp` 等），无需手动破解算法。

## 前置依赖

```bash
# 安装 Playwright（如果尚未安装）
pip install playwright

# 下载 Chromium 浏览器
playwright install chromium
```

## 配置账号

在 `config/accounts.json` 中添加抖音账号：

```json
{
  "douyin": [
    {
      "name": "超级辉",
      "url": "https://www.douyin.com/user/MS4wLjABAAAAslofpLxb1ccBf6x1QC-hBZA8v4QpNg6GQjf8HQGQMiY",
      "uid": "",
      "enabled": true
    },
    {
      "name": "其他博主",
      "uid": "MS4wLjABAAAA...",
      "enabled": true
    }
  ]
}
```

### 配置说明

- **name**: 博主名称（必填）
- **url**: 抖音用户主页链接（可选，会自动提取 `sec_user_id`）
- **uid**: 抖音 `sec_user_id`（可选，可从 URL 中提取）
- **enabled**: 是否启用该账号（默认 `true`）

### 如何获取 `sec_user_id`

1. 浏览器访问抖音用户主页，如 `https://www.douyin.com/user/MS4wLjABAAAA...`
2. URL 中 `/user/` 后面的字符串就是 `sec_user_id`
3. 可以直接填写完整 URL，程序会自动提取

## 登录（可选）

如果需要采集非公开内容或提高采集成功率，可以先登录抖音账号：

```bash
# 打开浏览器登录窗口
python -m pipeline auth-login --platform douyin

# 在弹出的浏览器中完成登录
# 登录成功后按 Enter 键，Cookie 会自动保存
```

登录信息会保存在 `.browser-profiles/douyin/` 目录下，后续采集自动使用。

## 运行采集

### 采集所有平台（包括抖音）

```bash
python -m pipeline collect --date 2026-08-13
```

### 仅采集抖音平台

```bash
python -m pipeline collect --date 2026-08-13 --platform douyin
```

### 采集单个博主

```bash
python -m pipeline collect --date 2026-08-13 --name "超级辉"
```

## 采集数据结构

每条抖音视频采集的数据包括：

- **标题**: 视频描述前 48 字
- **URL**: 视频链接 `https://www.douyin.com/video/{aweme_id}`
- **发布时间**: 视频创建时间（精确到秒）
- **内容**: 包含以下信息
  - 完整视频描述
  - 统计数据（点赞数、评论数、分享数）
  - 话题标签

### 示例输出

```markdown
## 抖音 / 超级辉

### 再次声明：任何以我名义或者以我助理名义来主动联系你们的...

**来源**: [抖音](https://www.douyin.com/video/7505641163321134387)  
**发布时间**: 2026-01-28 15:34:36  

再次声明：任何以我名义或者以我助理名义来主动联系你们的都是骗子

点赞: 12330, 评论: 523, 分享: 276

#超级辉 #骗子无处不在谨防上当受骗
```

## 性能与限流

抖音反爬较为严格，采集器采用以下策略：

- **并发数**: 最多 2 个账号同时采集
- **请求延时**: 3-6 秒随机延时
- **浏览器模拟**: 使用真实浏览器环境，自动处理所有签名参数

如遇到限流或采集失败：

1. 检查是否已登录抖音账号
2. 增加 `PLATFORM_DELAY` 延时（修改 `pipeline/collectors/runner.py`）
3. 减少并发数（修改 `PLATFORM_CONCURRENCY`）

## 故障排查

### 问题 1: Playwright 未安装

```
抖音 / {name}: Playwright 未安装，已跳过
```

**解决方案**:
```bash
pip install playwright
playwright install chromium
```

### 问题 2: 缺少 uid 或 url

```
抖音 / {name}: 缺少 uid 或 url，已跳过
```

**解决方案**: 在 `config/accounts.json` 中为该账号添加 `url` 或 `uid` 字段

### 问题 3: 浏览器启动失败

**解决方案**:
```bash
# 使用系统已安装的 Chrome/Edge
set CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
python -m pipeline collect --platform douyin

# 或者重新安装 Playwright 浏览器
playwright install chromium --force
```

### 问题 4: 采集失败或返回空数据

可能原因：
- 抖音触发了反爬验证
- 网络连接问题
- 用户主页设置了隐私保护

**解决方案**:
1. 先运行 `auth-login --platform douyin` 登录账号
2. 增加请求延时避免触发限流
3. 检查目标用户是否设置了隐私保护

## 高级配置

### 自定义浏览器路径

```bash
# 使用系统 Chrome
set CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe

# 使用自定义 Profile 目录
set DOUYIN_BROWSER_PROFILE=D:\douyin-profile
```

### 调整并发和延时

编辑 `pipeline/collectors/runner.py`:

```python
PLATFORM_CONCURRENCY = {
    "抖音": 1,  # 降低并发数
}

PLATFORM_DELAY = {
    "抖音": (5.0, 10.0),  # 增加延时到 5-10 秒
}
```

## 技术原理

### Playwright 自动化流程

1. 启动 Chromium 浏览器（持久化 Profile）
2. 访问用户主页 `https://www.douyin.com/user/{sec_user_id}`
3. 浏览器自动执行抖音的 JS，生成签名参数
4. 在浏览器环境中用 `fetch()` 调用 API
5. 返回 JSON 数据到 Python

### 为什么不直接用 requests？

抖音的 API 需要以下签名参数：
- `a_bogus`: 基于请求参数和环境指纹的动态签名
- `msToken`: 客户端会话 Token
- `verifyFp`: 设备指纹
- `webid`/`uifid`: 设备标识

这些参数的生成算法：
- 经过混淆的 JavaScript 代码
- 依赖浏览器环境（navigator、screen 等）
- 算法会定期更新

使用 Playwright 的优势：
- ✅ 浏览器自动处理所有签名
- ✅ 无需逆向破解算法
- ✅ 算法更新后无需维护
- ✅ 支持登录状态

## 参考资料

- [Playwright 官方文档](https://playwright.dev/python/)
- [抖音开放平台](https://open.douyin.com/)
- 项目中的其他采集器实现：`pipeline/collectors/xueqiu.py`、`pipeline/collectors/wechat.py`
