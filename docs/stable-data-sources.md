# 稳定数据源方案

本项目的采集流程已改为“实时采集 + 本地缓存 + 降级导出”：

```text
平台采集器 / WeWe RSS / 手工 URL
  -> data/articles.sqlite
  -> sources/<date>/*.md
  -> daily-brief generate
```

## 日常命令

采集并写入缓存，随后从缓存导出当天窗口内 Markdown：

```powershell
daily-brief collect --date 2026-07-16
```

只导出本次实时抓到的内容，不使用缓存兜底：

```powershell
daily-brief collect --date 2026-07-16 --no-cache-fallback
```

查看最近一次各账号采集状态：

```powershell
daily-brief source-health
```

## 浏览器持久登录

微博和雪球可以用持久浏览器 profile 保存登录态，减少手工维护 Cookie：

```powershell
daily-brief auth-login --platform weibo
daily-brief auth-login --platform xueqiu
```

登录窗口打开后，手动完成登录，再回到终端按 Enter。默认 profile 路径：

```text
.browser-profiles/weibo
.browser-profiles/xueqiu
```

可用环境变量覆盖：

```text
WEIBO_BROWSER_PROFILE
XUEQIU_BROWSER_PROFILE
```

## 公众号手工 URL 池

当 WeWe RSS 或第三方 RSS 不稳定时，可以把当天公众号文章 URL 放到：

```text
config/wechat_urls/YYYY-MM-DD.txt
```

支持三种格式：

```text
# 注释会被忽略
https://mp.weixin.qq.com/s/article-id
猫笔刀|https://mp.weixin.qq.com/s/article-id
ETF领航员 https://mp.weixin.qq.com/s/article-id
```

采集时会自动读取对应日期文件，抓取正文并写入 SQLite 缓存。

## WeWe RSS 接入建议

WeWe RSS 单独部署后，把每个公众号的 RSS URL 配进 `config/accounts.json`：

```json
{
  "wechat": [
    {
      "name": "猫笔刀",
      "rss_url": "http://localhost:4000/feeds/xxx.rss",
      "enabled": true
    }
  ]
}
```

建议每个公众号单独配置 feed，方便日报统计覆盖率。手工 URL 池仍保留为兜底。
