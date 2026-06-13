# Frontend UI 重设计 + 个人中心

**日期:** 2026-06-13  
**范围:** 全部前端页面 UI 翻新 + Bug 修复 + 新增个人中心页

---

## 目标

1. 修复 `chat/[sessionId]/page.tsx` 中 `use(params)` 运行时错误
2. 将整体 UI 从 Bloomberg 橙色主题改为 GitHub 深蓝灰（B 风格），对齐 ChatGPT/Claude 审美
3. 新增 `/profile` 个人中心页，展示用户信息与退出登录
4. 侧边栏底部添加用户头像入口，点击跳转个人中心

---

## 色彩系统

替换 `tailwind.config.js` 中的 `bg.*`、`border.*`、`text.*`、`accent.*` tokens：

| Token | 旧值 | 新值 |
|-------|------|------|
| `bg.primary` | `#0a0a0a` | `#0d1117` |
| `bg.secondary` | `#111111` | `#161b22` |
| `bg.tertiary` | `#1a1a1a` | `#21262d` |
| `bg.elevated` | `#222222` | `#2d333b` |
| `bg.hover` | `#2a2a2a` | `#30363d` |
| `border.primary` | `#2a2a2a` | `#30363d` |
| `border.secondary` | `#333333` | `#3d444d` |
| `text.primary` | `#e8e8e8` | `#f0f6fc` |
| `text.secondary` | `#999999` | `#c9d1d9` |
| `text.muted` | `#666666` | `#8b949e` |
| `text.accent` | `#f0a500` | `#58a6ff` |
| `accent.orange` | `#f0a500` | `#58a6ff`（改名为 accent.blue）|
| `accent.green` | `#22c55e` | `#3fb950` |
| `accent.red` | `#ef4444` | `#f85149` |

`globals.css` 同步更新背景色和滚动条颜色。

---

## Bug 修复

**文件:** `frontend/app/chat/[sessionId]/page.tsx`

**问题:** 第 9 行 `const { sessionId } = use(params)` — Next.js 14.2 客户端组件不支持用 `React.use()` 解包 Promise 类型的 `params`，导致"An unsupported type was passed to use(): [object Object]"运行时错误。

**修复:** 将函数签名改为同步 params（Next.js 14 在客户端组件中 params 仍为同步对象）：

```tsx
// 修复前
export default function SessionPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);

// 修复后
export default function SessionPage({ params }: { params: { sessionId: string } }) {
  const { sessionId } = params;
```

同时移除 `use` 的 import（如果不再使用）。

---

## 后端新增接口

**文件:** `agent/routers/auth.py`

新增 `GET /api/auth/me`，返回当前登录用户信息：

```python
@router.get("/me")
async def me(request: Request):
    user = await get_current_user(request)
    cfg = _settings(request)
    full_user = await get_user_by_id(cfg.db_path, user["id"])
    return {
        "id": full_user["id"],
        "username": full_user["username"],
        "email": full_user["email"],
        "created_at": full_user["created_at"],
    }
```

**文件:** `frontend/lib/api.ts`

新增：
```ts
export const user = {
  me: () => request<{ id: string; username: string; email: string | null; created_at: string }>('/api/auth/me'),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
};
```

后端同时新增 `POST /api/auth/logout`，清除 httponly cookie。

---

## 页面改动

### `app/login/page.tsx`
- 背景色改 `bg.primary`（`#0d1117`）
- 卡片用 `bg.secondary` + `border.primary`，去掉当前粗边框感
- 强调色从橙色改蓝色（`text.accent` = `#58a6ff`）
- Tab 激活态改蓝色背景（`bg.tertiary` + 蓝色文字）
- 输入框 focus 边框改蓝色
- 提交按钮改 `#58a6ff` 背景 + 白色文字

### `app/chat/layout.tsx` — 侧边栏
- 侧边栏宽度固定 `260px`，背景 `#161b22`，右边框 `#30363d`
- 顶部：logo 图标 + "Investment Agent" 文字 + "新对话" 按钮（蓝色，右对齐）
- 会话列表：当前会话左边蓝色 2px 竖线 + `bg.tertiary` 背景高亮；其余灰色文字，hover 淡显
- **底部用户区块**：头像（灰色圆形）+ 用户名，点击跳转 `/profile`
- 移除现有 `WatchlistPanel`（右侧面板），简化为标准双栏布局（自选股功能保留在 memory 页）

> 注：`WatchlistPanel` 组件本身保留，仅从 layout 移除——自选股/交易记录通过 `/memory/*` 页面访问。

### `app/chat/[sessionId]/page.tsx`
- 修复 Bug（见上）
- 用户消息：右对齐，深色卡片背景（`#21262d`），无气泡圆角改小
- 助手消息：左对齐，无背景色，直接文字，更宽展示区
- 流式 typing 指示器：三点动画（CSS keyframes）

### `app/chat/new/page.tsx`
读取此文件后按 B 主题同步，欢迎语和建议 prompt 不变，仅改颜色。

### `app/memory/trades/page.tsx` & `app/memory/events/page.tsx`
同步 B 主题色（背景、边框、按钮颜色），功能逻辑不动。

### `app/profile/page.tsx`（新建）

路由：`/profile`

布局：复用 chat layout（左侧侧边栏），主区域展示用户信息卡片。

展示内容：
- 用户名（大字）
- 邮箱（若有）
- 注册时间（格式化为中文日期）
- 退出登录按钮（红色，调用 logout API，清 cookie，跳转 `/login`）

数据来源：`GET /api/auth/me`（客户端请求，loading 态展示骨架屏）。

---

## 文件清单

| 文件 | 操作 |
|------|------|
| `frontend/tailwind.config.js` | 修改 color tokens |
| `frontend/app/globals.css` | 同步背景色、滚动条色 |
| `frontend/app/login/page.tsx` | 修改主题色 |
| `frontend/app/chat/layout.tsx` | 重写侧边栏，移除 WatchlistPanel，加用户入口 |
| `frontend/app/chat/[sessionId]/page.tsx` | 修复 Bug + 消息样式更新 |
| `frontend/app/chat/new/page.tsx` | 同步主题色 |
| `frontend/app/memory/trades/page.tsx` | 同步主题色 |
| `frontend/app/memory/events/page.tsx` | 同步主题色 |
| `frontend/app/profile/page.tsx` | **新建** |
| `frontend/lib/api.ts` | 新增 `user.me()` 和 `user.logout()` |
| `agent/routers/auth.py` | 新增 `GET /api/auth/me` + `POST /api/auth/logout` |

---

## 不在范围内

- 自选股实时行情数据（保留现有静态列表）
- 修改聊天逻辑、SSE、会话管理
- 修改后端认证机制
- 响应式/移动端适配
