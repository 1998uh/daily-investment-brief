# WeRead 公众号 Book ID 配置设计

## 目标

根据 WeRead 公众号详情链接中的 `v` 参数，解析出采集器需要的完整 `MP_WXS_...` 标识，并写入 `config/accounts.json` 的微信账号配置。

## 当前约束

- `pipeline/collectors/wechat.py` 只会把 `uid` 中以 `MP_WXS_` 开头的值作为 WeRead `bookId`。
- 现有四个微信账号已经存在，保留其名称、`urls`、`rss_url` 和 `enabled` 字段。
- 用户提供了第五个公众号“热点投研”，需要新增同结构账号。
- 本次不修改采集器代码，不把原始详情链接写入 `urls`，也不新增采集器不会读取的自定义字段。
- 工作区已有 `README.md` 和 `reports/archive/2026-08/04-week-08-17-to-08-22.md` 未提交改动，必须保持不变。

## 配置结果

| 公众号 | `uid` |
| --- | --- |
| 柯中投研笔记 | `MP_WXS_3083440260` |
| 三岁小怪兽 | `MP_WXS_3572504738` |
| 猫笔刀 | `MP_WXS_3198966508` |
| ETF领航员 | `MP_WXS_3911694450` |
| 热点投研 | `MP_WXS_3077802861` |

## 实施与验证

1. 修改 `config/accounts.json`：给现有四项补充 `uid`，新增“热点投研”项。
2. 使用 Python JSON 解析确认文件格式有效。
3. 使用账号加载器确认五个名称和五个 `uid` 均被正确读取，并且每个值都以 `MP_WXS_` 开头。
4. 检查 git diff，确保只新增配置变更；已有未提交文件不被修改。
