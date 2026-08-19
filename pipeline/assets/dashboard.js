(function () {
  "use strict";

  const data = window.__DASHBOARD_DATA__ || {};
  const app = document.getElementById("app");
  const state = { status: "all", query: "" };

  function node(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  }

  function formatNumber(value) {
    return new Intl.NumberFormat("zh-CN").format(Number(value || 0));
  }

  function formatDate(value) {
    return value ? String(value).replace(/-/g, ".") : "—";
  }

  function safeUrl(value) {
    try {
      const url = new URL(value);
      return url.protocol === "http:" || url.protocol === "https:" ? url.href : "";
    } catch (_) {
      return "";
    }
  }

  function badge(status, label) {
    return node("span", "status " + status, label || status);
  }

  function render() {
    const summary = data.summary || {};
    const readiness = (data.latest || {}).readiness || { status: "unknown", sources: [], blocking: [] };
    app.innerHTML = "";

    const shell = node("div", "shell");
    const topbar = node("header", "topbar");
    const intro = node("div");
    intro.append(node("p", "eyebrow", "INVESTMENT / LEDGER"));
    intro.append(node("h1", "", "投资复盘看板"));
    intro.append(node("p", "", "只读查看假设、证据与数据源状态。所有条目均保留原始 ID，可回到日报文件复核。"));
    topbar.append(intro);
    const stamp = node("div", "stamp");
    stamp.append(node("div", "as-of", "截至 " + formatDate(data.as_of)));
    stamp.append(node("div", "generated", "生成于 " + String(data.generated_at || "").replace("T", " ")));
    stamp.append(node("div", "state " + readiness.status, readiness.status === "ready" ? "数据源就绪" : "需要检查数据"));
    topbar.append(stamp);
    shell.append(topbar);

    const metrics = node("section", "metric-grid");
    addMetric(metrics, "focus", formatNumber(summary.due_hypotheses), "本期需要复查");
    addMetric(metrics, "", formatNumber(summary.active_hypotheses), "活跃假设");
    addMetric(metrics, "", formatNumber(summary.confirmed_hypotheses), "已确认");
    addMetric(metrics, "", formatNumber(summary.falsified_hypotheses), "已证伪");
    addMetric(metrics, "", formatNumber(summary.latest_article_count), "最新文章");
    shell.append(metrics);

    const main = node("div", "main-grid");
    const primary = node("div", "primary-stack");
    primary.append(renderAttention());
    primary.append(renderLedger());
    main.append(primary);

    const side = node("aside", "side-stack");
    side.append(renderCoverage());
    side.append(renderAuthorReliability());
    side.append(renderSentiment());
    side.append(renderTrend());
    main.append(side);
    shell.append(main);

    const footer = node("footer", "footer", "LOCAL READ-ONLY SNAPSHOT · schema " + String(data.schema_version || "—") + " · reports " + formatNumber(data.report_count));
    shell.append(footer);
    app.append(shell);
    app.append(renderDrawer());
    bindControls();
  }

  function addMetric(parent, className, value, label) {
    const metric = node("div", "metric " + className);
    metric.append(node("div", "metric-value", value));
    metric.append(node("div", "metric-label", label));
    parent.append(metric);
  }

  function renderAttention() {
    const panel = node("section", "panel attention");
    const head = panelHead("需要关注", "到复查日或已逾期的非终态假设");
    panel.append(head);
    const items = (data.hypotheses || []).filter((item) => item.due).slice(0, 6);
    if (!items.length) {
      panel.append(node("p", "empty", "当前没有到期假设。"));
      return panel;
    }
    items.forEach((item) => {
      const row = node("button", "attention-row row-button");
      row.type = "button";
      row.dataset.id = item.id;
      row.append(badge(item.status, item.status_label));
      row.append(node("span", "attention-claim", item.claim));
      row.append(node("span", "attention-meta", (item.overdue ? "逾期 " : "复查 ") + formatDate(item.due_date)));
      panel.append(row);
    });
    return panel;
  }

  function panelHead(title, caption) {
    const head = node("div", "panel-head");
    const titleNode = node("div");
    titleNode.append(node("h2", "", title));
    titleNode.append(node("p", "", caption));
    head.append(titleNode);
    return head;
  }

  function renderCoverage() {
    const panel = node("section", "panel coverage");
    panel.append(panelHead("数据源状态", "必需平台按当期文章数判断"));
    const rows = ((data.latest || {}).readiness || {}).sources || [];
    const coverage = (data.latest || {}).coverage || [];
    const counts = {};
    coverage.forEach((item) => { counts[item.source] = item; });
    if (!rows.length) {
      panel.append(node("p", "empty", "当前报告没有覆盖统计。"));
      return panel;
    }
    rows.forEach((item) => {
      const source = counts[item.source] || {};
      const expected = Number(source.expected_authors || 0);
      const authors = Number(source.authors_total || 0);
      const ratio = expected ? Math.min(100, Math.round(authors / expected * 100)) : (item.articles ? 100 : 0);
      const row = node("div", "coverage-row " + (item.status === "ok" ? "" : "missing"));
      row.append(node("span", "", item.source));
      const bar = node("div", "coverage-bar");
      const fill = node("div", "coverage-fill");
      fill.style.width = ratio + "%";
      bar.append(fill);
      row.append(bar);
      row.append(node("span", "coverage-count", formatNumber(item.articles)));
      panel.append(row);
    });
    const optional = coverage.filter((item) => !rows.some((row) => row.source === item.source));
    optional.forEach((item) => {
      const row = node("div", "coverage-row");
      row.append(node("span", "", item.source + " · 可选"));
      row.append(node("div", "coverage-bar"));
      row.append(node("span", "coverage-count", formatNumber(item.articles_total)));
      panel.append(row);
    });
    const blocking = ((data.latest || {}).readiness || {}).blocking || [];
    if (blocking.length) {
      const list = node("ul", "warning-list");
      blocking.slice(0, 4).forEach((item) => list.append(node("li", "", item)));
      panel.append(list);
    }
    return panel;
  }

  function renderTrend() {
    const panel = node("section", "panel trend");
    panel.append(panelHead("日报节奏", "文章量与报告日期"));
    const reports = (data.reports || []).slice(-7);
    const max = Math.max(1, ...reports.map((item) => Number(item.article_count || 0)));
    reports.forEach((item) => {
      const row = node("div", "trend-row");
      row.append(node("span", "mono", formatDate(item.date)));
      const bar = node("div", "trend-bar");
      const fill = node("div", "trend-fill");
      fill.style.width = Math.round(Number(item.article_count || 0) / max * 100) + "%";
      bar.append(fill);
      row.append(bar);
      row.append(node("span", "coverage-count", formatNumber(item.article_count)));
      panel.append(row);
    });
    return panel;
  }

  function renderSentiment() {
    const panel = node("section", "panel sentiment");
    const sentiment = data.sentiment || {};
    panel.append(panelHead("每日情绪温度计", "最近 7 个报告日 · 看好 / 回避净情绪"));
    const items = sentiment.top_directions || [];
    if (!items.length) {
      panel.append(node("p", "empty", "暂无可解析的作者方向信号。"));
      return panel;
    }
    items.forEach((item) => {
      const row = node("div", "sentiment-row");
      const current = item.series && item.series.length ? item.series[item.series.length - 1] : {};
      const score = Number(current.net_score || 0);
      const scoreClass = score > 0 ? "bullish" : (score < 0 ? "bearish" : "neutral");
      row.append(node("div", "sentiment-label", item.name));
      const track = node("div", "sentiment-track " + scoreClass);
      const fill = node("div", "sentiment-fill");
      fill.style.width = Math.round(Math.abs(score) * 50) + "%";
      fill.style.left = score >= 0 ? "50%" : (50 - Math.round(Math.abs(score) * 50)) + "%";
      track.append(node("span", "sentiment-midline"), fill);
      row.append(track);
      row.append(node("div", "sentiment-score", (score > 0 ? "+" : "") + Math.round(score * 100) + "%"));
      row.title = "近 7 日：看好 " + formatNumber(item.bullish) + " / 回避 " + formatNumber(item.bearish);
      panel.append(row);
    });
    const note = node("p", "sentiment-note", "净分数 = (看好 - 回避) / (看好 + 回避)；按作者-日-方向去重");
    panel.append(note);
    return panel;
  }

  function renderAuthorReliability() {
    const panel = node("section", "panel reliability");
    panel.append(panelHead("作者可信度", "仅统计最终已确认 / 已证伪假设；联合署名分别归因"));
    const items = data.author_reliability || [];
    if (!items.length) {
      panel.append(node("p", "empty", "尚无已确认或已证伪的作者假设。"));
      return panel;
    }
    const table = document.createElement("table");
    table.className = "reliability-table";
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    ["排名", "作者", "胜率", "确认 / 证伪"].forEach((label) => headRow.append(node("th", "", label)));
    head.append(headRow);
    table.append(head);
    const body = document.createElement("tbody");
    items.forEach((item) => {
      const row = document.createElement("tr");
      row.append(
        node("td", "mono", "#" + formatNumber(item.rank)),
        node("td", "reliability-author", item.author),
        node("td", "mono", Math.round(Number(item.win_rate || 0) * 100) + "%"),
        node("td", "mono reliability-outcomes", formatNumber(item.confirmed) + " / " + formatNumber(item.falsified))
      );
      body.append(row);
    });
    table.append(body);
    panel.append(table);
    return panel;
  }

  function renderLedger() {
    const panel = node("section", "panel ledger");
    panel.append(panelHead("假设账本", "按最新状态排序；点击一行查看来源与验证历史"));
    const toolbar = node("div", "toolbar");
    const search = document.createElement("input");
    search.type = "search";
    search.placeholder = "搜索主题、主张或假设 ID";
    search.id = "ledger-search";
    const select = document.createElement("select");
    select.id = "ledger-status";
    [["all", "全部状态"], ["pending", "待验证"], ["partially_confirmed", "部分确认"], ["confirmed", "已确认"], ["falsified", "已证伪"], ["inconclusive", "无结论"], ["unavailable", "数据不可用"]].forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      select.append(option);
    });
    toolbar.append(search, select);
    panel.append(toolbar);
    const table = document.createElement("table");
    table.className = "ledger-table";
    const thead = document.createElement("thead");
    const tr = document.createElement("tr");
    ["状态", "主张", "验证", "截止 / 复查"].forEach((label) => tr.append(node("th", "", label)));
    thead.append(tr);
    table.append(thead);
    const tbody = document.createElement("tbody");
    tbody.id = "ledger-body";
    table.append(tbody);
    panel.append(table);
    return panel;
  }

  function renderRows() {
    const body = document.getElementById("ledger-body");
    if (!body) return;
    body.innerHTML = "";
    const query = state.query.trim().toLowerCase();
    const items = (data.hypotheses || []).filter((item) => {
      const matchesStatus = state.status === "all" || item.status === state.status;
      const haystack = [item.id, item.claim, item.subject && item.subject.name, item.subject && item.subject.thscode].join(" ").toLowerCase();
      return matchesStatus && (!query || haystack.includes(query));
    });
    if (!items.length) {
      const row = node("tr");
      const cell = node("td", "empty", "没有匹配的假设。");
      cell.colSpan = 4;
      row.append(cell);
      body.append(row);
      return;
    }
    items.forEach((item) => {
      const row = node("tr", "ledger-row");
      row.dataset.id = item.id;
      const statusCell = node("td");
      statusCell.append(badge(item.status, item.status_label));
      const claimCell = node("td");
      const button = node("button", "row-button");
      button.type = "button";
      button.dataset.id = item.id;
      button.append(node("span", "claim", item.claim));
      button.append(node("span", "subject", (item.subject && item.subject.name ? item.subject.name : "未命名主题") + " · " + item.id));
      claimCell.append(button);
      const modeCell = node("td", "mono", item.verification_mode_label || item.verification_mode);
      const dateCell = node("td", "mono", formatDate(item.deadline));
      if (item.next_review_date) dateCell.append(node("div", "subject", "复查 " + formatDate(item.next_review_date)));
      row.append(statusCell, claimCell, modeCell, dateCell);
      body.append(row);
    });
  }

  function renderDrawer() {
    const backdrop = node("div", "drawer-backdrop");
    backdrop.id = "drawer-backdrop";
    const drawer = node("aside", "drawer");
    drawer.id = "drawer";
    const close = node("button", "drawer-close", "关闭");
    close.type = "button";
    close.id = "drawer-close";
    drawer.append(close, node("div", "drawer-content"));
    backdrop.append(drawer);
    return backdrop;
  }

  function openDetail(id) {
    const item = (data.hypotheses || []).find((candidate) => candidate.id === id);
    if (!item) return;
    const content = document.querySelector(".drawer-content");
    content.innerHTML = "";
    content.append(badge(item.status, item.status_label));
    content.append(node("h2", "", item.claim));
    const meta = node("p", "stamp");
    meta.style.textAlign = "left";
    meta.append(node("span", "mono", item.id + " · " + (item.subject && item.subject.name ? item.subject.name : "未命名主题")));
    content.append(meta);
    const details = node("dl", "detail-block");
    detail(details, "验证方式", item.verification_mode_label || item.verification_mode);
    detail(details, "截止日期", formatDate(item.deadline));
    detail(details, "复查日期", formatDate(item.next_review_date || item.deadline));
    detail(details, "主题代码", item.subject && item.subject.thscode ? item.subject.thscode : "未配置");
    content.append(details);
    const sourceBlock = node("div", "detail-block");
    sourceBlock.append(node("h3", "", "原始来源"));
    (item.sources || []).forEach((source) => {
      if (source.quote) sourceBlock.append(node("p", "quote", source.quote));
      const link = safeUrl(source.url);
      const line = node("p", "subject", source.author + (source.article_id ? " · " + source.article_id : ""));
      if (link) {
        const anchor = node("a", "source-link", "打开来源");
        anchor.href = link;
        anchor.target = "_blank";
        anchor.rel = "noreferrer";
        line.append(" · ", anchor);
      }
      sourceBlock.append(line);
    });
    content.append(sourceBlock);
    const history = node("div", "detail-block");
    history.append(node("h3", "", "验证历史"));
    if (!(item.history || []).length) history.append(node("p", "empty", "尚无验证记录。"));
    (item.history || []).forEach((event) => {
      const row = node("div", "history-item");
      row.append(node("span", "mono", formatDate(event.date)));
      row.append(badge(event.status, event.status_label));
      row.append(node("span", "history-reason", event.reason || "未提供说明"));
      history.append(row);
    });
    content.append(history);
    const backdrop = document.getElementById("drawer-backdrop");
    document.getElementById("drawer").classList.add("open");
    backdrop.classList.add("open");
  }

  function detail(parent, label, value) {
    parent.append(node("dt", "", label), node("dd", "", value));
  }

  function bindControls() {
    renderRows();
    document.getElementById("ledger-search").addEventListener("input", (event) => {
      state.query = event.target.value;
      renderRows();
    });
    document.getElementById("ledger-status").addEventListener("change", (event) => {
      state.status = event.target.value;
      renderRows();
    });
    document.addEventListener("click", (event) => {
      const trigger = event.target.closest("[data-id]");
      if (trigger) openDetail(trigger.dataset.id);
      if (event.target.id === "drawer-close" || event.target.id === "drawer-backdrop") closeDetail();
    });
  }

  function closeDetail() {
    const backdrop = document.getElementById("drawer-backdrop");
    if (!backdrop) return;
    document.getElementById("drawer").classList.remove("open");
    backdrop.classList.remove("open");
  }

  render();
})();
