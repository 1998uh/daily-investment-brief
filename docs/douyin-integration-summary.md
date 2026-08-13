# 抖音采集器集成完成

## 功能概述

成功为项目添加了抖音平台数据采集功能，使用 **Playwright 浏览器自动化** 技术绕过抖音的反爬机制。

## 已完成的工作

### 1. 核心采集器实现
- ✅ 创建 `pipeline/collectors/douyin.py`
- ✅ 实现 `collect_douyin()` 主采集函数
- ✅ 实现 `_fetch_user_posts()` 浏览器自动化数据获取
- ✅ 实现 `_parse_aweme()` 视频数据解析
- ✅ 实现 `extract_sec_user_id()` UID 提取工具

### 2. 系统集成
- ✅ 注册到 `pipeline/collectors/runner.py`
  - 添加导入语句
  - 配置并发数和延时策略
  - 集成到 `collect_account()` 路由
  - 添加账号验证规则
- ✅ 更新 `pipeline/collectors/accounts.py`
  - 添加抖音平台标识符规范化
- ✅ 更新 `pipeline/collectors/browser.py`
  - 添加抖音登录 URL 配置

### 3. 文档和测试
- ✅ 创建 `docs/douyin-collector-guide.md` 详细使用指南
- ✅ 创建 `scripts/test_douyin.py` 测试脚本

## 技术架构

### Playwright 自动化方案

```
用户请求 → Python 启动浏览器 → 访问抖音主页 → 浏览器自动生成签名
          ↓
返回 JSON ← Python 接收 ← 浏览器内 fetch() ← API 调用（带签名）
```

**核心优势:**
- 浏览器自动处理 `a_bogus`、`msToken` 等签名参数
- 无需逆向破解算法
- 算法更新后无需维护
- 支持登录状态持久化

### 数据流程

```python
collect_douyin()
  ↓
_fetch_user_posts()  # Playwright 浏览器获取 JSON
  ↓
_parse_aweme()  # 解析单条视频数据
  ↓
CollectedItem  # 标准化数据结构
```

## 配置示例

### 账号配置 (`config/accounts.json`)

```json
{
  "douyin": [
    {
      "name": "超级辉",
      "url": "https://www.douyin.com/user/MS4wLjABAAAAslofpLxb1ccBf6x1QC-hBZA8v4QpNg6GQjf8HQGQMiY",
      "enabled": true
    }
  ]
}
```

### 登录（可选）

```bash
python -m pipeline auth-login --platform douyin
```

### 运行采集

```bash
# 采集所有平台（包括抖音）
python -m pipeline collect --date 2026-08-13

# 仅采集抖音
python -m pipeline collect --date 2026-08-13 --platform douyin
```

## 采集数据结构

每条视频包含:
- **标题**: 视频描述（前 48 字）
- **URL**: `https://www.douyin.com/video/{aweme_id}`
- **发布时间**: 精确到秒的时间戳
- **内容**:
  - 完整视频描述
  - 统计信息（点赞/评论/分享数）
  - 话题标签

## 性能参数

```python
# pipeline/collectors/runner.py

PLATFORM_CONCURRENCY = {
    "抖音": 2,  # 最多 2 个账号并发
}

PLATFORM_DELAY = {
    "抖音": (3.0, 6.0),  # 请求间隔 3-6 秒
}
```

## 测试方法

```bash
# 运行测试脚本
python scripts/test_douyin.py

# 测试内容:
# 1. sec_user_id 提取测试
# 2. 实际采集测试（采集超级辉的最新 5 条视频）
```

## 与现有采集器的对比

| 平台 | 技术方案 | 签名处理 | 登录支持 |
|------|---------|---------|---------|
| 雪球 | Playwright (专用线程) | 浏览器自动 | ✅ |
| 微博 | HTTP + Cookie | 手动维护 | ✅ |
| 微信读书 | HTTP + 动态 Referer | 手动构造 | ✅ |
| **抖音** | **Playwright (按需启动)** | **浏览器自动** | **✅** |

## 故障排查

### 常见问题

1. **Playwright 未安装**
   ```bash
   pip install playwright
   playwright install chromium
   ```

2. **浏览器启动失败**
   ```bash
   set CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
   ```

3. **采集失败**
   - 先运行登录: `auth-login --platform douyin`
   - 增加延时避免限流
   - 检查用户隐私设置

## 文件清单

```
pipeline/collectors/
├── douyin.py              # 抖音采集器核心实现 (319 行)
├── runner.py              # 已更新：集成抖音采集
├── accounts.py            # 已更新：添加平台标识符
└── browser.py             # 已更新：添加登录 URL

docs/
└── douyin-collector-guide.md  # 详细使用指南

scripts/
└── test_douyin.py         # 测试脚本
```

## 下一步建议

### 可选优化

1. **高频采集场景**: 参考 `xueqiu.py` 实现专用后台线程，避免每次请求都启动浏览器
2. **重试机制**: 添加请求失败自动重试（当前失败直接跳过）
3. **代理支持**: 在 `browser_launch_kwargs()` 中添加代理配置
4. **视频下载**: 扩展功能，支持下载视频文件到本地

### 监控指标

建议监控:
- 采集成功率（通过 `source_health` 表）
- 平均响应时间
- 限流触发频率

## 参考项目

实现参考了以下开源项目:
- [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)
- [JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader)

## 贡献者

- 实现: Claude Code (Kiro)
- 集成日期: 2026-08-13
- 项目: daily-investment-brief

---

**状态**: ✅ 已完成并通过测试
**版本**: 1.0.0
