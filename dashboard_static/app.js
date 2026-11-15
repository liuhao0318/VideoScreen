let data = { counts: {}, sources: [], clips: [] };
let jobs = [];
let currentLogId = "";
let sourceFilter = "all";
let clipFilter = "all";
let clipSort = "default";
let currentClipStage = "pending"; // "pending" | "published" | "all"
let currentViewMode = "grid"; // "grid" | "list"
let clipPage = 1;
const PAGE_SIZE = 24;

const selectedClips = new Set();
const selectedSources = new Set();
const unsavedEdits = new Map();
let currentDrawerClip = null;

const labels = {
  sources: "素材总数",
  waiting: "待处理",
  analyzed: "已分析",
  clips: "最终成片",
  douyin_pending: "待发布",
  douyin_published: "已发布"
};

const stages = {
  waiting: "待转写",
  transcribed: "待分析",
  analyzed: "已分析",
  ready: "待发布",
  published: "已发布",
  source_deleted: "原素材已清理",
  no_audio: "无音轨",
  failed: "失败"
};

const actionLabels = {
  transcribe_all: "转写新素材",
  analyze_all: "分析全部素材",
  retry_source: "重新处理素材",
  cut_all: "剪辑全部候选",
  sync_queue: "同步发布队列",
  upload_douyin: "自动发布",
  upload_selected: "批量自动发布",
  manual_publish: "手动发布"
};

const statusLabels = {
  running: "运行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消"
};

const $ = s => document.querySelector(s);

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function safeFetchJson(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    if (res.status === 404) {
      throw new Error("后台接口未找到 (HTTP 404)。如果您刚更新了代码，请在终端按 Ctrl+C 停止并重新运行 python3 dashboard_server.py 载入最新后台路由。");
    }
    let msg = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      if (err.error) msg = err.error;
    } catch (_) {
      try {
        const text = await res.text();
        if (text) msg = text.slice(0, 100);
      } catch (_) {}
    }
    throw new Error(msg);
  }
  return await res.json();
}

let toastTimer = null;
function toast(text, type = "info") {
  const el = $("#toast");
  el.className = "";
  el.classList.add(type);
  el.textContent = text;
  el.style.display = "block";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.style.display = "none";
  }, 2800);
}

function formatDuration(sec) {
  const s = Math.round(parseFloat(sec) || 0);
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m.toString().padStart(2, "0")}:${rem.toString().padStart(2, "0")}`;
}

function formatTrafficNum(num) {
  const n = parseInt(num) || 0;
  if (n >= 10000) return (n / 10000).toFixed(1) + "w";
  return n.toLocaleString();
}

function renderTrafficBadge(t) {
  if (!t || (!t.play_count && !t.like_count)) return "";
  const isViral = t.is_viral;
  return `
    <div class="clip-traffic-badge ${isViral ? 'is-viral' : ''}">
      ${isViral ? '<span class="viral-pill">🔥 爆款</span>' : ''}
      <span class="traffic-stat" title="播放量">👁️ ${formatTrafficNum(t.play_count)}</span>
      <span class="traffic-stat" title="点赞数">👍 ${formatTrafficNum(t.like_count)}</span>
      <span class="traffic-stat" title="评论数">💬 ${t.comment_count || 0}</span>
      ${t.velocity > 10 ? `<span class="velocity-pill" title="新增点赞/小时">⚡ +${t.velocity}/h</span>` : ''}
    </div>
  `;
}

function publishSettings() {
  return {
    ai_cover: $("#ai-cover").checked,
    declaration: $("#publish-declaration").checked,
    auto_publish: $("#auto-final-publish").checked
  };
}

async function refresh(options = {}) {
  const shouldScan = options.scan === true;
  const pill = $("#auto-scan-pill");
  if (shouldScan && pill) {
    pill.classList.add("scanning");
    const scanText = pill.querySelector(".scan-text");
    if (scanText) scanText.textContent = "正在扫描新素材...";
  }

  const url = shouldScan ? "/api/overview?scan=1" : "/api/overview";
  try {
    data = await fetch(url).then(r => r.json());
  } catch (e) {
    if (pill) pill.classList.remove("scanning");
    return;
  }

  data.sources = data.sources.filter(x => x.status !== "source_deleted");
  data.counts.sources = data.sources.length;
  data.counts.waiting = data.sources.filter(x => x.stage === "waiting" || x.stage === "transcribed").length;
  data.counts.analyzed = data.sources.filter(x => x.analyzed).length;

  if (pill) {
    pill.classList.remove("scanning");
    const scanText = pill.querySelector(".scan-text");
    if (scanText) {
      if (data.scan && data.scan.last_completed_at) {
        const t = new Date(data.scan.last_completed_at * 1000).toLocaleTimeString();
        scanText.textContent = `已扫描 · ${t}`;
      } else {
        scanText.textContent = "自动扫描就绪";
      }
    }
  }

  if (data.ai) {
    updateAiBadge(data.ai);
  }
  if (data.radar) {
    updateRadarBadge(data.radar);
  }

  renderStats();
  renderSourceFilters();
  renderSources();
  renderClipFilters();
  renderClips();
  await refreshJobs();
}

function renderStats() {
  const rawSources = data.counts.sources || 0;
  const transcribed = data.sources.filter(x => x.transcript_exists).length;
  const analyzed = data.counts.analyzed || 0;
  const clips = data.counts.clips || 0;
  const pending = data.counts.douyin_pending || 0;
  const published = data.counts.douyin_published || 0;

  if ($("#funnel-sources")) $("#funnel-sources").textContent = rawSources;
  if ($("#funnel-transcribed")) $("#funnel-transcribed").textContent = transcribed;
  if ($("#funnel-analyzed")) $("#funnel-analyzed").textContent = analyzed;
  if ($("#funnel-clips")) $("#funnel-clips").textContent = clips;
  if ($("#funnel-pending")) $("#funnel-pending").textContent = pending;
  if ($("#funnel-published")) $("#funnel-published").textContent = published;

  if ($("#tab-sources-badge")) $("#tab-sources-badge").textContent = rawSources;
  if ($("#tab-clips-badge")) $("#tab-clips-badge").textContent = clips;

  if (data.storage) {
    if ($("#disk-free-val")) $("#disk-free-val").textContent = `${data.storage.disk_free_gb || 0} GB`;
    if ($("#clips-size-val")) $("#clips-size-val").textContent = `${data.storage.clips_total_gb || 0} GB`;
    if ($("#cleanable-val")) $("#cleanable-val").textContent = `${data.storage.cleanable_gb || 0} GB`;
  }

  if (data.traffic) {
    if ($("#metric-tracked-count")) $("#metric-tracked-count").textContent = data.traffic.tracked_count || 0;
    if ($("#metric-total-plays")) $("#metric-total-plays").textContent = formatTrafficNum(data.traffic.total_plays || 0);
    if ($("#metric-total-likes")) $("#metric-total-likes").textContent = formatTrafficNum(data.traffic.total_likes || 0);
    if ($("#metric-viral-count")) $("#metric-viral-count").textContent = `${data.traffic.viral_count || 0} 条`;
    if ($("#metric-interaction-rate")) $("#metric-interaction-rate").textContent = `${data.traffic.avg_interaction_rate_pct || 0}%`;
  }

  if (data.recorder) {
    renderRecorder(data.recorder);
  }
}

/* ======================= 素材列表 ======================= */

const sourceGroups = {
  all: { label: "全部", test: () => true },
  waiting_transcript: { label: "待转写", test: x => !x.transcript_exists && x.stage !== "source_deleted" && x.stage !== "failed" && x.stage !== "no_audio" },
  transcribed: { label: "已转写", test: x => x.transcript_exists },
  waiting_analysis: { label: "待分析", test: x => x.transcript_exists && !x.analyzed },
  analyzed: { label: "已分析", test: x => x.analyzed },
  waiting_clip: { label: "待剪辑", test: x => x.analyzed && x.candidate_count > 0 && x.clip_count === 0 },
  clipped: { label: "已剪辑", test: x => x.clip_count > 0 },
  failed: { label: "失败/无音轨", test: x => x.stage === "failed" || x.stage === "no_audio" }
};

function renderSourceFilters() {
  $("#source-filters").innerHTML = Object.entries(sourceGroups).map(([key, group]) => `
    <button class="source-filter ${key === sourceFilter ? "active" : ""}" data-filter="${key}">
      ${group.label}<span>${data.sources.filter(group.test).length}</span>
    </button>
  `).join("");
}

function pipeline(x) {
  const steps = [
    { name: "转写", done: x.transcript_exists },
    { name: "分析", done: x.analyzed },
    { name: "剪辑", done: x.clip_count > 0 }
  ];
  return `
    <div class="pipeline">
      ${steps.map((step, i) => `
        <span class="pipeline-step ${step.done ? "done" : "pending"}">${step.done ? "✓" : "○"} ${step.name}</span>
        ${i < steps.length - 1 ? "<i>→</i>" : ""}
      `).join("")}
    </div>
  `;
}

function visibleSources() {
  const q = $("#source-search").value.toLowerCase().trim();
  const group = sourceGroups[sourceFilter] || sourceGroups.all;
  return data.sources.filter(group.test).filter(x => x.name.toLowerCase().includes(q));
}

function sourceCanDelete(x) {
  return x.clip_count > 0 && x.exists;
}

function renderSources() {
  const rows = visibleSources();
  const valid = new Set(data.sources.filter(sourceCanDelete).map(x => x.path));
  [...selectedSources].forEach(path => {
    if (!valid.has(path)) selectedSources.delete(path);
  });

  $("#delete-selected-sources").textContent = `删除所选原素材（${selectedSources.size}）`;

  // 更新底部悬浮操作栏
  const floatingBar = $("#source-floating-bar");
  if (floatingBar) {
    if (selectedSources.size > 0) {
      floatingBar.style.display = "flex";
      $("#floating-selected-count").textContent = selectedSources.size;
    } else {
      floatingBar.style.display = "none";
    }
  }

  $("#source-body").innerHTML = rows.map(x => `
    <tr>
      <td>
        ${sourceCanDelete(x)
          ? `<input class="source-select" type="checkbox" data-source="${encodeURIComponent(x.path)}" ${selectedSources.has(x.path) ? "checked" : ""}>`
          : '<span class="muted">—</span>'
        }
      </td>
      <td>
        <div class="name">${esc(x.name)}</div>
        <div class="path">${esc(x.path)}</div>
        ${x.error ? `<div class="error-text">${esc(x.error)}</div>` : ""}
      </td>
      <td>
        ${pipeline(x)}
        <span class="badge ${x.stage}">${stages[x.stage] || x.stage}</span>
      </td>
      <td>${x.candidate_count}</td>
      <td>${x.clip_count}</td>
      <td>${x.published_count}/${x.clip_count}</td>
      <td class="row-actions">
        ${x.stage === "failed" ? `<button onclick='startJob("retry_source",{source:decodeURIComponent("${encodeURIComponent(x.path)}")})'>再次处理</button>` : ""}
        ${x.clip_count > 0 ? (x.exists ? `<button class="danger" onclick='cleanupSource(${JSON.stringify(x.path)})'>删除原录制视频</button>` : '<button class="deleted-source" disabled>原素材已删除</button>') : ""}
      </td>
    </tr>
  `).join("") || '<tr><td colspan="7" class="empty-cell">当前分类没有素材</td></tr>';
}

/* ======================= 成片与发布 ======================= */

const clipGroups = {
  all: { label: "全部", test: () => true },
  viral: { label: "🔥 爆款切片", test: x => !!(x.traffic && x.traffic.is_viral) },
  high_score: { label: "高分精选(≥80)", test: x => (parseFloat(x.score) || 0) >= 80 },
  needs_copy: { label: "文案待生成", test: x => !x.publish_content || x.publish_content.trim() === "" },
  ready_copy: { label: "文案已就绪", test: x => !!(x.publish_content && x.publish_content.trim().length > 0) }
};

function renderClipFilters() {
  const pending = data.clips.filter(x => x.douyin_status !== "published");
  const published = data.clips.filter(x => x.douyin_status === "published");
  const all = data.clips;

  if ($("#stage-pending-count")) $("#stage-pending-count").textContent = pending.length;
  if ($("#stage-published-count")) $("#stage-published-count").textContent = published.length;
  if ($("#stage-all-count")) $("#stage-all-count").textContent = all.length;

  let baseClips = pending;
  if (currentClipStage === "published") baseClips = published;
  else if (currentClipStage === "all") baseClips = all;

  if ($("#clip-filter-all-count")) $("#clip-filter-all-count").textContent = baseClips.length;
  if ($("#clip-filter-viral-count")) $("#clip-filter-viral-count").textContent = baseClips.filter(clipGroups.viral.test).length;
  if ($("#clip-filter-score-count")) $("#clip-filter-score-count").textContent = baseClips.filter(clipGroups.high_score.test).length;
  if ($("#clip-filter-needs-copy-count")) $("#clip-filter-needs-copy-count").textContent = baseClips.filter(clipGroups.needs_copy.test).length;
  if ($("#clip-filter-ready-copy-count")) $("#clip-filter-ready-copy-count").textContent = baseClips.filter(clipGroups.ready_copy.test).length;
}

function getFilteredClips(clips) {
  const q = ($("#clip-search")?.value || "").toLowerCase().trim();
  const group = clipGroups[clipFilter] || clipGroups.all;
  let list = clips.filter(group.test);

  if (q) {
    list = list.filter(x => {
      const haystack = [
        x.title, x.name, x.publish_title, x.publish_content,
        x.ai_topics, x.ai_matched_terms, x.ai_summary
      ].filter(Boolean).join(" ").toLowerCase();
      return haystack.includes(q);
    });
  }

  if (clipSort === "play_desc") {
    list.sort((a, b) => (b.traffic?.play_count || 0) - (a.traffic?.play_count || 0));
  } else if (clipSort === "like_desc") {
    list.sort((a, b) => (b.traffic?.like_count || 0) - (a.traffic?.like_count || 0));
  } else if (clipSort === "velocity_desc") {
    list.sort((a, b) => (b.traffic?.velocity || 0) - (a.traffic?.velocity || 0));
  } else if (clipSort === "score_desc") {
    list.sort((a, b) => (parseFloat(b.score) || 0) - (parseFloat(a.score) || 0));
  } else if (clipSort === "duration_desc") {
    list.sort((a, b) => (parseFloat(b.duration) || 0) - (parseFloat(a.duration) || 0));
  } else if (clipSort === "duration_asc") {
    list.sort((a, b) => (parseFloat(a.duration) || 0) - (parseFloat(b.duration) || 0));
  }

  return list;
}

function renderClips() {
  renderClipFilters();

  const pendingAll = data.clips.filter(x => x.douyin_status !== "published");
  const publishedAll = data.clips.filter(x => x.douyin_status === "published");

  let baseClips = pendingAll;
  if (currentClipStage === "published") baseClips = publishedAll;
  else if (currentClipStage === "all") baseClips = data.clips;

  const filtered = getFilteredClips(baseClips);
  const totalCount = filtered.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  if (clipPage > totalPages) clipPage = totalPages;
  if (clipPage < 1) clipPage = 1;

  // 关键优化：客户端分页，每页仅渲染 24 条，杜绝 1000+ DOM 节点卡死
  const pagedList = filtered.slice((clipPage - 1) * PAGE_SIZE, clipPage * PAGE_SIZE);

  const displayArea = $("#clip-display-area");
  if (!displayArea) return;

  displayArea.className = currentViewMode === "grid" ? "clip-grid" : "clip-list";

  if (currentViewMode === "grid") {
    displayArea.innerHTML = renderGridCards(pagedList);
  } else {
    displayArea.innerHTML = renderListRows(pagedList);
  }

  renderPagination(totalCount, totalPages);
}

function renderGridCards(clips) {
  if (!clips.length) {
    return '<div class="empty-state">当前分类下没有符合条件的成片</div>';
  }

  return clips.map(x => {
    const published = x.douyin_status === "published";
    const failed = x.douyin_status === "failed";
    const statusText = published ? "抖音已发布" : (failed ? "自动发布失败" : "抖音待发布");
    const statusClass = published ? "published" : (failed ? "failed" : "ready");

    return `
      <article class="clip" data-output="${esc(x.output)}">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <label class="clip-select" style="margin-bottom:0;">
            <input type="checkbox" data-output="${esc(x.output)}" ${selectedClips.has(x.output) ? "checked" : ""}> ${published ? "勾选成片" : "选择发布"}
          </label>
          <div style="display:flex;align-items:center;gap:4px;">
            ${published && !x.exists ? `<span class="badge" style="background:#e0e7ff;color:#3730a3;font-size:11px;">💾 原片已释放</span>` : ""}
            <span class="badge ${statusClass}">${statusText}</span>
          </div>
        </div>

        ${x.exists ? `
          <div class="clip-thumb" onclick='playClip(decodeURIComponent("${encodeURIComponent(x.output)}"),${JSON.stringify(x.title || x.name)})' title="点击播放视频">
            <div class="thumb-poster">
              <span class="poster-icon">⚽</span>
              <span class="poster-tag">高清切片</span>
            </div>
            <div class="thumb-play">▶</div>
            <span class="thumb-duration">${formatDuration(x.duration)}</span>
            <span class="thumb-score">⭐ ${esc(x.score)}分</span>
          </div>
        ` : ""}

        <h3>${esc(x.title || x.name)}</h3>

        <div class="meta">
          ${esc(x.duration)} 秒 ·
          ${esc(x.score)} 分 ·
          ${x.exists ? "文件正常" : "文件已释放/缺失"}
        </div>

        ${renderTrafficBadge(x.traffic)}

        <div class="path">${esc(x.output)}</div>

        <div class="ai-copy-source" style="margin-top:10px;">
          <div><b>AI内容摘要：</b><span>${esc(x.ai_summary || "暂无摘要")}</span></div>
          <div class="ai-meta">
            <span><b>话题：</b>${esc(x.ai_topics || "未分类")}</span>
            <span><b>命中词：</b>${esc(x.ai_matched_terms || "无")}</span>
          </div>
        </div>

        <div class="clip-actions" style="margin-top:12px;">
          ${x.exists ? `<button class="play" onclick='playClip(decodeURIComponent("${encodeURIComponent(x.output)}"),${JSON.stringify(x.title || x.name)})'>▶ 播放</button>` : ""}
          ${x.exists && !published ? `
            <button class="upload" onclick='startJob("upload_douyin",{index:${x.index},output:decodeURIComponent("${encodeURIComponent(x.output)}"),...publishSettings()})'>自动发布</button>
          ` : ""}
          <button class="clip-editor-toggle" onclick='openClipDrawer(decodeURIComponent("${encodeURIComponent(x.output)}"))'>
            ✏️ 查看与编辑文案
          </button>
          <button onclick='setPublishStatus(${x.index},${JSON.stringify(published ? "pending" : "published")},${JSON.stringify(x.output)})'>
            ${published ? "改回待发布" : "标记已发布"}
          </button>
          ${!published ? `<button onclick='startJob("manual_publish",{output:decodeURIComponent("${encodeURIComponent(x.output)}")})'>手动发布</button>` : ""}
          ${!published ? `<button class="danger" onclick='deleteClip(decodeURIComponent("${encodeURIComponent(x.output)}"),${JSON.stringify(x.title || x.name)}, false)'>🗑️ 删除成片</button>` : ""}
          ${published && x.exists ? `<button class="secondary" title="清理本地大视频文件以释放磁盘空间，保留已发布状态与归因数据" onclick='cleanupPublishedClip(decodeURIComponent("${encodeURIComponent(x.output)}"),${JSON.stringify(x.title || x.name)})'>🧹 释放空间</button>` : ""}
          ${published ? `<button class="danger" title="彻底删除该成片的所有发布记录及本地文件" onclick='deleteClip(decodeURIComponent("${encodeURIComponent(x.output)}"),${JSON.stringify(x.title || x.name)}, false)'>🗑️ 彻底删除</button>` : ""}
          <button onclick='navigator.clipboard.writeText(${JSON.stringify(x.output)}); toast("路径已复制", "info")'>复制路径</button>
        </div>
      </article>
    `;
  }).join("");
}

function renderListRows(clips) {
  if (!clips.length) {
    return '<div class="empty-state">当前分类下没有符合条件的成片</div>';
  }

  return clips.map(x => {
    const published = x.douyin_status === "published";
    const failed = x.douyin_status === "failed";
    const statusText = published ? "已发布" : (failed ? "失败" : "待发布");
    const statusClass = published ? "published" : (failed ? "failed" : "ready");

    return `
      <div class="clip-row" data-output="${esc(x.output)}" onclick='if(!event.target.closest("button,input,a")) openClipDrawer(decodeURIComponent("${encodeURIComponent(x.output)}"))'>
        <div class="clip-row-select" onclick="event.stopPropagation()">
          <input type="checkbox" data-output="${esc(x.output)}" ${selectedClips.has(x.output) ? "checked" : ""}>
        </div>

        <div class="clip-row-thumb" onclick='event.stopPropagation(); playClip(decodeURIComponent("${encodeURIComponent(x.output)}"),${JSON.stringify(x.title || x.name)})' title="点击播放视频">
          <div class="thumb-poster">⚽</div>
          <div class="thumb-play">▶</div>
        </div>

        <div class="clip-row-info">
          <div class="clip-row-title">${esc(x.title || x.name)}</div>
          <div class="clip-row-meta">
            <span class="clip-row-score">⭐ ${esc(x.score)}分</span>
            <span>⏱️ ${formatDuration(x.duration)}</span>
            <span>🏷️ ${esc(x.ai_topics || "未分类")}</span>
            ${x.traffic && x.traffic.play_count ? `
              <span class="traffic-stat" style="color:var(--green);font-weight:750;">
                ${x.traffic.is_viral ? '🔥 ' : ''}👁️ ${formatTrafficNum(x.traffic.play_count)} · 👍 ${formatTrafficNum(x.traffic.like_count)}
              </span>
            ` : ''}
          </div>
        </div>

        <div style="display:flex;align-items:center;gap:4px;">
          ${published && !x.exists ? `<span class="badge" style="background:#e0e7ff;color:#3730a3;font-size:11px;">💾 已释放</span>` : ""}
          <span class="badge ${statusClass}">${statusText}</span>
        </div>

        <div class="clip-row-actions" onclick="event.stopPropagation()">
          <button onclick='openClipDrawer(decodeURIComponent("${encodeURIComponent(x.output)}"))'>✏️ 文案</button>
          ${x.exists && !published ? `<button class="upload" onclick='startJob("upload_douyin",{index:${x.index},output:decodeURIComponent("${encodeURIComponent(x.output)}"),...publishSettings()})'>发布</button>` : ""}
          ${x.exists ? `<button class="play" onclick='playClip(decodeURIComponent("${encodeURIComponent(x.output)}"),${JSON.stringify(x.title || x.name)})'>▶ 播</button>` : ""}
          ${!published ? `<button class="danger" style="padding:4px 8px;font-size:12px;" onclick='deleteClip(decodeURIComponent("${encodeURIComponent(x.output)}"),${JSON.stringify(x.title || x.name)}, false)'>🗑️ 删</button>` : ""}
          ${published && x.exists ? `<button class="secondary" style="padding:4px 8px;font-size:12px;" title="清理本地大视频文件释放磁盘空间" onclick='cleanupPublishedClip(decodeURIComponent("${encodeURIComponent(x.output)}"),${JSON.stringify(x.title || x.name)})'>🧹 释放空间</button>` : ""}
          ${published ? `<button class="danger" style="padding:4px 8px;font-size:12px;" title="彻底删除记录" onclick='deleteClip(decodeURIComponent("${encodeURIComponent(x.output)}"),${JSON.stringify(x.title || x.name)}, false)'>🗑️ 删记录</button>` : ""}
        </div>
      </div>
    `;
  }).join("");
}

function renderPagination(totalCount, totalPages) {
  let existing = $("#clip-pagination");
  if (!existing) {
    existing = document.createElement("div");
    existing.id = "clip-pagination";
    existing.className = "pagination-wrap";
    $("#clip-display-wrap").appendChild(existing);
  }

  if (totalCount === 0) {
    existing.innerHTML = "";
    return;
  }

  existing.innerHTML = `
    <div class="pagination-info">
      共 <strong>${totalCount}</strong> 条成片 · 每页 <strong>${PAGE_SIZE}</strong> 条
    </div>
    <div class="pagination-controls">
      <button class="page-btn" ${clipPage <= 1 ? "disabled" : ""} onclick="changeClipPage(1)">首页</button>
      <button class="page-btn" ${clipPage <= 1 ? "disabled" : ""} onclick="changeClipPage(${clipPage - 1})">上一页</button>
      <span class="page-cur-pill">${clipPage} / ${totalPages}</span>
      <button class="page-btn" ${clipPage >= totalPages ? "disabled" : ""} onclick="changeClipPage(${clipPage + 1})">下一页</button>
      <button class="page-btn" ${clipPage >= totalPages ? "disabled" : ""} onclick="changeClipPage(${totalPages})">末页</button>
    </div>
  `;
}

function changeClipPage(page) {
  clipPage = page;
  renderClips();
  const wrap = $("#clip-stage-tabs");
  if (wrap) wrap.scrollIntoView({ behavior: "smooth" });
}

/* ======================= 右侧抽屉式编辑 (Master-Detail Drawer) ======================= */

function openClipDrawer(output) {
  const clip = data.clips.find(x => x.output === output);
  if (!clip) return;
  currentDrawerClip = clip;

  const drawer = $("#clip-drawer");
  const badge = $("#drawer-badge");
  const title = $("#drawer-title");
  const body = $("#drawer-body");

  const published = clip.douyin_status === "published";
  const failed = clip.douyin_status === "failed";
  const statusText = published ? "抖音已发布" : (failed ? "自动发布失败" : "抖音待发布");
  const statusClass = published ? "published" : (failed ? "failed" : "ready");

  badge.className = `drawer-badge badge ${statusClass}`;
  badge.textContent = statusText;
  title.textContent = clip.title || clip.name;

  const draft = unsavedEdits.get(clip.output) || {};
  const titleValue = draft.title !== undefined ? draft.title : (clip.publish_title || clip.title || clip.name || "");
  const contentValue = draft.content !== undefined ? draft.content : (clip.publish_content || "");

  body.innerHTML = `
    <div class="drawer-video-box">
      <div class="drawer-video-toolbar">
        <span class="d-tag">画面比例</span>
        <button class="d-btn ${drawerRatio === 'auto' ? 'active' : ''}" data-drawer-ratio="auto" onclick="setDrawerRatio('auto')">自适应</button>
        <button class="d-btn ${drawerRatio === '16/9' ? 'active' : ''}" data-drawer-ratio="16/9" onclick="setDrawerRatio('16/9')">16:9</button>
        <button class="d-btn ${drawerRatio === '9/16' ? 'active' : ''}" data-drawer-ratio="9/16" onclick="setDrawerRatio('9/16')">9:16 竖屏</button>
        <button class="d-btn ${drawerFit === 'cover' ? 'active' : ''}" data-drawer-fit="toggle" onclick="toggleDrawerFit()">${drawerFit === 'cover' ? '裁切铺满' : '等比包含'}</button>
        <button class="d-btn primary-d-btn" onclick='playClip(decodeURIComponent("${encodeURIComponent(clip.output)}"),${JSON.stringify(clip.title || clip.name)})'>🎬 放大播放</button>
      </div>
      <div class="drawer-video-preview ${drawerRatio === '16/9' ? 'aspect-16-9' : (drawerRatio === '9/16' ? 'aspect-9-16' : '')}" id="drawer-video-container">
        <video id="drawer-video-player" class="${drawerFit === 'cover' ? 'fit-cover' : ''}" controls playsinline preload="metadata" src="/api/media?output=${encodeURIComponent(clip.output)}"></video>
      </div>
    </div>

    <div class="meta" style="font-size:13px;">
      <b style="font-size:15px;color:var(--ink);">${esc(clip.title || clip.name)}</b>
      <div style="margin-top:5px;color:var(--muted);">
        ⏱️ 时长：${esc(clip.duration)} 秒 · ⭐ 推荐评分：${esc(clip.score)} 分 · 路径：${esc(clip.output)}
      </div>
    </div>

    <div class="ai-copy-source" style="margin:0;">
      <div><b>AI内容摘要：</b><p style="margin:4px 0 0;line-height:1.5;">${esc(clip.ai_summary || "暂无摘要")}</p></div>
      <div class="ai-meta" style="margin-top:6px;">
        <span><b>话题：</b>${esc(clip.ai_topics || "未分类")}</span>
        <span><b>命中词：</b>${esc(clip.ai_matched_terms || "无")}</span>
      </div>
      ${clip.ai_reason ? `<details open style="margin-top:6px;"><summary>AI推荐理由</summary><p style="margin:4px 0 0;">${esc(clip.ai_reason)}</p></details>` : ""}
    </div>

    <div class="publish-editor" style="margin:0;">
      <label>
        <div class="field-header">
          <span>发布标题</span>
          <span class="char-count drawer-title-count ${titleValue.length > 100 ? "danger" : (titleValue.length >= 85 ? "warning" : "")}">${titleValue.length}/100</span>
        </div>
        <input class="publish-title drawer-input" maxlength="100" data-output="${esc(clip.output)}" value="${esc(titleValue)}">
      </label>

      <label>
        <div class="field-header">
          <span>发布正文（包含话题标签）</span>
          <span class="char-count drawer-content-count ${contentValue.length > 2000 ? "danger" : (contentValue.length >= 1800 ? "warning" : "")}">${contentValue.length}/2000</span>
        </div>
        <textarea class="publish-content drawer-textarea" maxlength="2000" rows="5" data-output="${esc(clip.output)}">${esc(contentValue)}</textarea>
      </label>

      <div style="display:flex;align-items:center;gap:8px;margin-top:6px;flex-wrap:wrap;">
        <select id="drawer-ai-engine" style="padding:7px 10px;border:1px solid var(--line);border-radius:7px;font-size:12px;background:#fff;cursor:pointer;">
          <option value="default">AI引擎: 跟随全局设置</option>
          <option value="ollama">AI引擎: 本地私有模型 (Ollama)</option>
          <option value="api">AI引擎: 云端大模型 API</option>
        </select>
        <select id="drawer-ai-style" style="padding:7px 10px;border:1px solid var(--line);border-radius:7px;font-size:12px;background:#fff;cursor:pointer;">
          <option value="tactical_youth" selected>风格: ⚽ 战术复盘与青训深度 (默认推荐)</option>
          <option value="tactical">风格: 🎯 硬核技战术打法复盘</option>
          <option value="youth">风格: 🌱 青训实战与球员成长深度观察</option>
          <option value="benchmark_viral">风格: 🔥 标杆爆款张力范式 (头部对齐)</option>
          <option value="opinionated">风格: ⚡ 犀利评析 (直击痛点不和稀泥)</option>
          <option value="humorous_meme">风格: 🎙️ 董路特色幽默相声金句</option>
        </select>
        <button class="ai-write" onclick='generateDrawerText(this, "${esc(clip.output)}")'>🤖 AI生成文案</button>
        <button class="primary" onclick='saveDrawerText(this, "${esc(clip.output)}")'>保存修改</button>
        <button onclick='copyDrawerText(this)'>复制文案</button>
        ${!published ? `<button class="danger" style="margin-left:auto;" onclick='deleteClip(decodeURIComponent("${encodeURIComponent(clip.output)}"),${JSON.stringify(clip.title || clip.name)}, false)'>🗑️ 删除成片</button>` : ""}
        ${published && clip.exists ? `<button class="secondary" title="清理本地大视频文件以释放磁盘空间，完整保留抖音已发布状态及流量归因记录" onclick='cleanupPublishedClip(decodeURIComponent("${encodeURIComponent(clip.output)}"),${JSON.stringify(clip.title || clip.name)})'>🧹 清理本地视频(释放空间)</button>` : ""}
        ${published && !clip.exists ? `<span class="badge" style="background:#e0e7ff;color:#3730a3;font-size:11px;padding:4px 8px;">💾 本地原片已释放</span>` : ""}
        ${published ? `<button class="danger" style="margin-left:auto;" onclick='deleteClip(decodeURIComponent("${encodeURIComponent(clip.output)}"),${JSON.stringify(clip.title || clip.name)}, false)'>🗑️ 彻底删除记录</button>` : ""}
      </div>
    </div>

    ${clip.douyin_status === "published" || clip.traffic ? `
      <div class="drawer-traffic-section" style="margin-top:12px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <strong style="font-size:13px;color:var(--ink);">📊 实时流量监控数据</strong>
          ${clip.traffic?.is_viral ? '<span class="viral-pill">🔥 爆款切片</span>' : ''}
        </div>
        <div class="drawer-traffic-grid" style="margin-top:8px;">
          <div class="traffic-input-box">
            <label>播放量</label>
            <input type="number" id="drawer-traffic-play" value="${clip.traffic?.play_count || 0}">
          </div>
          <div class="traffic-input-box">
            <label>点赞量</label>
            <input type="number" id="drawer-traffic-like" value="${clip.traffic?.like_count || 0}">
          </div>
          <div class="traffic-input-box">
            <label>评论数</label>
            <input type="number" id="drawer-traffic-comment" value="${clip.traffic?.comment_count || 0}">
          </div>
          <div class="traffic-input-box">
            <label>分享数</label>
            <input type="number" id="drawer-traffic-share" value="${clip.traffic?.share_count || 0}">
          </div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;">
          <small class="muted">互动率: ${(clip.traffic?.interaction_rate ? (clip.traffic.interaction_rate * 100).toFixed(2) : 0)}% ${clip.traffic?.velocity ? `· 增速: +${clip.traffic.velocity}/h` : ''}</small>
          <button class="secondary" style="padding:4px 10px;font-size:11px;" onclick='saveDrawerTraffic(decodeURIComponent("${encodeURIComponent(clip.output)}"))'>保存流量更新</button>
        </div>
      </div>
    ` : ''}
  `;

  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
}

function closeClipDrawer() {
  const drawer = $("#clip-drawer");
  const video = drawer.querySelector("video");
  if (video) {
    video.pause();
    video.removeAttribute("src");
    video.load();
  }
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
  currentDrawerClip = null;
}

async function saveDrawerText(button, output) {
  const drawer = $("#clip-drawer");
  const title = drawer.querySelector(".publish-title").value.trim();
  const content = drawer.querySelector(".publish-content").value.trim();
  if (!title) {
    toast("发布标题不能为空", "error");
    return;
  }
  const response = await fetch("/api/publish-text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ output, title, content })
  });
  const result = await response.json();
  if (!response.ok) {
    toast(result.error || "保存失败", "error");
    return;
  }
  unsavedEdits.delete(output);
  toast("文案已成功保存并同步！", "success");
  await refresh();
}

async function generateDrawerText(button, output) {
  const drawer = $("#clip-drawer");
  const styleSelect = $("#drawer-ai-style");
  const engineSelect = $("#drawer-ai-engine");
  const style = styleSelect ? styleSelect.value : "tactical";
  const provider = engineSelect && engineSelect.value !== "default" ? engineSelect.value : undefined;

  button.disabled = true;
  button.textContent = "AI正在创作中……";
  try {
    const response = await fetch("/api/generate-publish-text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ output, style, provider })
    });
    const result = await response.json();
    if (!response.ok) {
      toast(result.error || "AI生成失败", "error");
      return;
    }
    drawer.querySelector(".publish-title").value = result.publish_title;
    drawer.querySelector(".publish-content").value = result.publish_content;
    unsavedEdits.delete(output);

    const titleCount = drawer.querySelector(".drawer-title-count");
    const contentCount = drawer.querySelector(".drawer-content-count");
    if (titleCount) titleCount.textContent = `${result.publish_title.length}/100`;
    if (contentCount) contentCount.textContent = `${result.publish_content.length}/2000`;

    const engineName = result.provider === "api" ? `云端API (${result.model})` : `本地Ollama (${result.model})`;
    toast(`AI文案创作完成并自动保存！[${engineName}]`, "success");
    await refresh();
  } catch (error) {
    toast("AI生成文案请求异常：" + error, "error");
  } finally {
    button.disabled = false;
    button.textContent = "🤖 AI重新生成文案";
  }
}

function copyDrawerText(button) {
  const drawer = $("#clip-drawer");
  const title = drawer.querySelector(".publish-title").value.trim();
  const content = drawer.querySelector(".publish-content").value.trim();
  navigator.clipboard.writeText([title, content].filter(Boolean).join("\n")).then(() => {
    toast("发布文字已复制到剪贴板", "success");
  });
}

let currentVideoRatio = localStorage.getItem("video_ratio_pref") || "auto";
let currentVideoFit = localStorage.getItem("video_fit_pref") || "contain";
let hudTimer = null;
let drawerRatio = "auto";
let drawerFit = "contain";

function showVideoHud(text) {
  const hud = $("#video-hud");
  if (!hud) return;
  hud.textContent = text;
  hud.classList.add("show");
  if (hudTimer) clearTimeout(hudTimer);
  hudTimer = setTimeout(() => {
    hud.classList.remove("show");
  }, 1600);
}

function setVideoRatio(ratio) {
  currentVideoRatio = ratio;
  localStorage.setItem("video_ratio_pref", ratio);
  const video = $("#clip-player");
  if (!video) return;

  video.classList.remove("aspect-auto", "aspect-16-9", "aspect-9-16", "aspect-4-3", "aspect-21-9");
  const ratioMap = {
    "auto": "aspect-auto",
    "16/9": "aspect-16-9",
    "9/16": "aspect-9-16",
    "4/3": "aspect-4-3",
    "21/9": "aspect-21-9"
  };
  const cls = ratioMap[ratio] || "aspect-auto";
  video.classList.add(cls);

  $$(".v-ratio-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.ratio === ratio);
  });

  const labelMap = {
    "auto": "画面比例：自适应原始",
    "16/9": "画面比例：16:9 横屏",
    "9/16": "画面比例：9:16 竖屏短视频 (对齐抖音/小红书)",
    "4/3": "画面比例：4:3 标准",
    "21/9": "画面比例：21:9 超宽屏"
  };
  showVideoHud(labelMap[ratio] || `画面比例：${ratio}`);
}

function setVideoFit(fit) {
  currentVideoFit = fit;
  localStorage.setItem("video_fit_pref", fit);
  const video = $("#clip-player");
  if (!video) return;

  video.classList.remove("fit-contain", "fit-cover", "fit-fill");
  video.classList.add(`fit-${fit}`);

  $$(".v-fit-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.fit === fit);
  });

  const labelMap = {
    "contain": "填充模式：完整包含 (等比带黑边)",
    "cover": "填充模式：裁切铺满 (占满视窗·无黑边)",
    "fill": "填充模式：拉伸铺满 (填满画面)"
  };
  showVideoHud(labelMap[fit] || `填充模式：${fit}`);
}

function cycleVideoFit() {
  const fits = ["contain", "cover", "fill"];
  const nextIdx = (fits.indexOf(currentVideoFit) + 1) % fits.length;
  setVideoFit(fits[nextIdx]);
}

function toggleTheaterMode() {
  const dialog = $("#video-dialog");
  const btn = $("#btn-theater-mode");
  if (!dialog || !btn) return;
  const isTheater = dialog.classList.toggle("theater-mode");
  btn.textContent = isTheater ? "🗗 默认大小" : "🗖 剧院铺满";
  btn.classList.toggle("active", isTheater);
  showVideoHud(isTheater ? "已切换至：剧院铺满大屏 (98vw)" : "已恢复：标准播放器大小");
}

function toggleFullscreenMode() {
  const container = $("#video-player-container");
  if (!container) return;
  if (!document.fullscreenElement && !document.webkitFullscreenElement) {
    if (container.requestFullscreen) {
      container.requestFullscreen().catch(err => console.warn("Fullscreen error:", err));
    } else if (container.webkitRequestFullscreen) {
      container.webkitRequestFullscreen();
    }
  } else {
    if (document.exitFullscreen) {
      document.exitFullscreen();
    } else if (document.webkitExitFullscreen) {
      document.webkitExitFullscreen();
    }
  }
}

function updateFullscreenBtnState() {
  const btn = $("#btn-fullscreen-mode");
  if (!btn) return;
  const isFs = !!(document.fullscreenElement || document.webkitFullscreenElement);
  btn.textContent = isFs ? "⛶ 退出全屏" : "⛶ 铺满全屏";
  btn.classList.toggle("active", isFs);
  if (isFs) {
    showVideoHud("已铺满全屏幕 (按 Esc 退出)");
  }
}

function toggleFluidLayout() {
  const isFluid = document.body.classList.toggle("fluid-layout");
  const btn = $("#toggle-page-fluid");
  if (btn) {
    btn.textContent = isFluid ? "🗗 居中视口" : "🗖 宽屏铺满";
    btn.classList.toggle("active", isFluid);
  }
  localStorage.setItem("dashboard_fluid_layout", isFluid ? "true" : "false");
  toast(isFluid ? "已切换为：宽屏铺满模式（100%视口宽度）" : "已切换为：标准居中视口模式", "info");
}

function initFluidLayout() {
  const saved = localStorage.getItem("dashboard_fluid_layout");
  if (saved === "true") {
    document.body.classList.add("fluid-layout");
    const btn = $("#toggle-page-fluid");
    if (btn) {
      btn.textContent = "🗗 居中视口";
      btn.classList.add("active");
    }
  }
}

function setDrawerRatio(ratio) {
  drawerRatio = ratio;
  const container = $("#drawer-video-container");
  if (!container) return;
  container.classList.remove("aspect-16-9", "aspect-9-16");
  if (ratio === "16/9") container.classList.add("aspect-16-9");
  else if (ratio === "9/16") container.classList.add("aspect-9-16");

  $$(".drawer-video-toolbar [data-drawer-ratio]").forEach(b => {
    b.classList.toggle("active", b.dataset.drawerRatio === ratio);
  });
}

function toggleDrawerFit() {
  const video = $("#drawer-video-player");
  if (!video) return;
  drawerFit = drawerFit === "contain" ? "cover" : "contain";
  video.classList.toggle("fit-cover", drawerFit === "cover");
  const btn = $(".drawer-video-toolbar [data-drawer-fit]");
  if (btn) {
    btn.textContent = drawerFit === "cover" ? "裁切铺满" : "等比包含";
    btn.classList.toggle("active", drawerFit === "cover");
  }
}

function playClip(output, title) {
  const modal = $("#video-modal");
  const video = $("#clip-player");
  $("#video-modal-title").textContent = title || "播放成片";
  video.src = `/api/media?output=${encodeURIComponent(output)}`;

  // 恢复保存的比例与铺满模式
  setVideoRatio(currentVideoRatio);
  setVideoFit(currentVideoFit);

  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
  video.play().catch(() => {});
}

function closeClipPlayer() {
  const modal = $("#video-modal");
  const video = $("#clip-player");
  if (document.fullscreenElement || document.webkitFullscreenElement) {
    if (document.exitFullscreen) document.exitFullscreen();
  }
  const dialog = $("#video-dialog");
  if (dialog) dialog.classList.remove("theater-mode");
  const theaterBtn = $("#btn-theater-mode");
  if (theaterBtn) {
    theaterBtn.textContent = "🗖 剧院铺满";
    theaterBtn.classList.remove("active");
  }
  video.pause();
  video.removeAttribute("src");
  video.load();
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
}

let confirmResolver = null;
function showConfirm(title, message, isDanger = false) {
  return new Promise(resolve => {
    confirmResolver = resolve;
    const modal = $("#confirm-modal");
    if (!modal) {
      resolve(window.confirm(message));
      return;
    }
    $("#confirm-modal-title").textContent = title || "请确认操作";
    $("#confirm-modal-message").innerHTML = esc(message).replace(/\n/g, "<br>");
    const okBtn = $("#confirm-ok-btn");
    okBtn.className = isDanger ? "danger" : "primary";
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
  });
}

function closeConfirm(result) {
  const modal = $("#confirm-modal");
  if (modal) {
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
  }
  if (confirmResolver) {
    confirmResolver(result);
    confirmResolver = null;
  }
}

async function cancelAutoPublish() {
  const ok = await showConfirm(
    "取消自动发布",
    "确认取消当前正在运行的自动发布任务吗？\n正在上传或等待发布的视频会停止，不会标记为已发布。",
    true
  );
  if (!ok) return;
  const response = await fetch("/api/cancel-publish", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}"
  });
  const result = await response.json();
  if (!response.ok) {
    toast(result.error || "取消失败", "error");
    return;
  }
  toast(result.count ? `已取消 ${result.count} 个自动发布任务` : "当前没有正在运行的自动发布任务", "info");
  await refreshJobs();
}

async function deleteClip(output, title, cleanupFileOnly = false) {
  const modalTitle = cleanupFileOnly ? "清理本地成片视频（释放空间）" : "彻底删除成片";
  const modalMsg = cleanupFileOnly
    ? `确认清理该已发布成片的本地大视频文件以释放磁盘空间吗？\n${title}\n\n注意：本地视频文件将被物理删除以节省磁盘空间，但抖音已发布状态、文案及流量归因记录将完整保留！`
    : `确认彻底删除该成片记录吗？\n${title}\n\n注意：本地视频文件与所有发布记录将被彻底清除（原录制素材不受影响）。`;

  const ok = await showConfirm(modalTitle, modalMsg, true);
  if (!ok) return;
  const response = await fetch("/api/delete-clip", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ output, cleanup_file_only: cleanupFileOnly })
  });
  const result = await response.json();
  if (!response.ok) {
    toast(result.error || "操作失败", "error");
    return;
  }
  selectedClips.delete(output);
  unsavedEdits.delete(output);
  toast(cleanupFileOnly ? "本地视频文件已删除，磁盘空间已释放！" : "成片记录已彻底删除", "success");
  if (currentDrawerClip && currentDrawerClip.output === output) {
    closeClipDrawer();
  }
  await refresh();
}

window.cleanupPublishedClip = function(output, title) {
  return deleteClip(output, title, true);
};

async function cleanupSource(source) {
  const ok = await showConfirm(
    "删除原素材",
    "确认删除这个原录制直播视频吗？\n文件将移入系统回收站，剪辑成片不会删除。",
    true
  );
  if (!ok) return;
  const response = await fetch("/api/cleanup-source", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source })
  });
  const result = await response.json();
  if (!response.ok) {
    toast(result.error || "清理失败", "error");
    return;
  }
  toast("原素材已移入回收站", "success");
  await refresh();
}

async function cleanupSelectedSources() {
  const sources = [...selectedSources];
  if (!sources.length) {
    toast("请先勾选已经剪辑完成的原素材", "error");
    return;
  }
  const ok = await showConfirm(
    "批量删除原素材",
    `确认删除所选的 ${sources.length} 个原录制直播视频吗？\n文件将移入系统回收站，转写、分析记录和剪辑成片都会保留。`,
    true
  );
  if (!ok) return;
  let deleted = 0;
  let failed = 0;
  for (const source of sources) {
    try {
      const response = await fetch("/api/cleanup-source", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source })
      });
      if (response.ok) {
        selectedSources.delete(source);
        deleted += 1;
      } else {
        failed += 1;
      }
    } catch (error) {
      failed += 1;
    }
  }
  failed ? toast(`已删除 ${deleted} 个，失败 ${failed} 个`, "info") : toast(`已删除 ${deleted} 个原素材`, "success");
  await refresh();
}

async function setPublishStatus(index, status, output) {
  const actionText = status === "published" ? "标记为已发布" : "改回待发布";
  const ok = await showConfirm("修改发布状态", `确定要${actionText}吗？`);
  if (!ok) return;

  let response;
  let result;
  try {
    response = await fetch("/api/publish-status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        index: index,
        output: output,
        platform: "douyin",
        status: status
      })
    });
    result = await response.json();
  } catch (error) {
    toast("无法连接后台，状态没有更新", "error");
    return;
  }

  if (!response.ok) {
    toast(result.error || "状态更新失败", "error");
    return;
  }

  toast(status === "published" ? "已标记为抖音发布完成" : "已改回待发布", "success");
  await refresh();
}

async function startJob(action, extra = {}) {
  if (action === "upload_douyin" || action === "upload_selected") {
    const message = extra.auto_publish
      ? "将自动设置封面和声明，并在上传完成后点击发布。程序只有监控到明确成功状态才会标记已发布。继续吗？"
      : "将打开专用 Chrome 并填写发布信息，最终由你手动点击发布。继续吗？";
    const ok = await showConfirm("确认启动发布", message);
    if (!ok) return;
  }
  const r = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, ...extra })
  });
  const out = await r.json();
  if (!r.ok) {
    toast(out.error || "启动失败", "error");
    return;
  }
  toast("任务已启动", "info");
  currentLogId = out.id;
  document.querySelector('[data-tab="jobs"]').click();
  await refreshJobs();
  await showLog(out.id);
}

let _jobsPollTimer = null;
let _wasJobRunning = false;

function _formatJobElapsed(startedAt) {
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - (startedAt || 0)));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

async function refreshJobs() {
  try {
    jobs = await fetch("/api/jobs").then(r => r.json());
  } catch (e) {
    _scheduleJobsPoll(false);
    return;
  }
  const running = jobs.some(j => j.status === "running");
  const runningBadge = $("#tab-jobs-badge");
  if (runningBadge) {
    runningBadge.style.display = running ? "inline-block" : "none";
    const runningOne = jobs.find(j => j.status === "running");
    if (runningOne && typeof runningOne.progress === "number") {
      runningBadge.textContent = `${runningOne.progress}%`;
    } else {
      runningBadge.textContent = "进行中";
    }
  }

  $("#job-list").innerHTML = jobs.map(j => {
    const isRun = j.status === "running";
    const hasPct = typeof j.progress === "number";
    const pctVal = hasPct ? j.progress : 0;
    const elapsed = isRun ? ` · 已耗时 ${_formatJobElapsed(j.started_at)}` : "";
    const progLine = isRun ? `
      <div style="margin-top:6px;">
        <div style="display:flex;justify-content:space-between;font-size:11px;color:#0369a1;margin-bottom:3px;">
          <span>${esc(j.progress_text || "正在处理...")}</span>
          <span><b>${hasPct ? pctVal + "%" : "处理中"}</b>${elapsed}</span>
        </div>
        <div style="height:6px;background:#e2e8f0;border-radius:4px;overflow:hidden;">
          <div style="height:100%;width:${hasPct ? pctVal : 35}%;background:#0284c7;transition:width 0.3s ease;"></div>
        </div>
      </div>
    ` : "";

    return `
      <div class="job ${j.id === currentLogId ? "selected" : ""}" onclick="showLog('${j.id}')">
        <div style="flex:1;min-width:0;">
          <div style="display:flex;align-items:center;gap:8px;">
            <b>${esc(actionLabels[j.action] || j.action)}</b>
            <small>${new Date(j.started_at * 1000).toLocaleTimeString()}</small>
          </div>
          ${progLine}
        </div>
        <div class="job-status">
          <span class="badge ${j.status}">${esc(statusLabels[j.status] || j.status)}</span>
          ${j.status === "failed" ? `<button onclick='event.stopPropagation();startJob(${JSON.stringify(j.action)},${JSON.stringify(j.payload || {})})'>再次处理</button>` : ""}
        </div>
      </div>
    `;
  }).join("") || "暂无后台任务";

  const runningJob = jobs.find(j => j.status === "running");
  if (currentLogId || runningJob) {
    await showLog(currentLogId || (runningJob && runningJob.id));
  }
  if (_wasJobRunning && !running) {
    refresh({ scan: false });
  }
  _wasJobRunning = running;
  _scheduleJobsPoll(running);
}

function _scheduleJobsPoll(isRunning) {
  if (_jobsPollTimer) clearTimeout(_jobsPollTimer);
  _jobsPollTimer = setTimeout(refreshJobs, isRunning ? 900 : 3500);
}

async function showLog(id) {
  if (!id) return;
  currentLogId = id;
  const job = jobs.find(x => x.id === id);
  if (job) {
    const pctPart = (job.status === "running" && typeof job.progress === "number")
      ? ` · ${job.progress}% (${job.progress_text || ""})`
      : "";
    $("#log-title").textContent = `${actionLabels[job.action] || job.action} · ${statusLabels[job.status] || job.status}${pctPart}`;
  }
  const logView = $("#log-view");
  if (!logView) return;
  try {
    const res = await fetch(`/api/log?id=${encodeURIComponent(id)}`);
    const d = await res.json();
    const text = d.text || d.error || "等待输出……";

    const isAtBottom = (logView.scrollHeight - logView.clientHeight) <= (logView.scrollTop + 50);
    const isNewJob = logView.dataset.currentId !== id;
    logView.textContent = text;
    logView.dataset.currentId = id;

    if (isNewJob || isAtBottom) {
      logView.scrollTop = logView.scrollHeight;
    }
  } catch (err) {
    console.warn("读取任务日志失败:", err);
  }
}

/* ======================= 事件监听与初始化 ======================= */

document.querySelectorAll("[data-action]").forEach(b => {
  b.onclick = () => startJob(b.dataset.action);
});

document.querySelectorAll(".tab").forEach(b => {
  b.onclick = () => {
    document.querySelectorAll(".tab,.panel").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    const targetPanel = $("#" + b.dataset.tab);
    if (targetPanel) targetPanel.classList.add("active");
    if (b.dataset.tab === "recorder") {
      fetchRecorderStatus();
      fetchRecorderLogs();
    }
  };
});

/* ======================= 直播录制器 (DouyinLiveRecorder) 集成 ======================= */

async function fetchRecorderStatus() {
  try {
    const res = await safeFetchJson("/api/recorder/status");
    renderRecorder(res);
  } catch (err) {
    console.warn("fetchRecorderStatus err:", err);
  }
}

async function fetchRecorderLogs() {
  try {
    const res = await safeFetchJson("/api/recorder/logs");
    const pre = $("#recorder-log-view");
    if (pre && res.logs) {
      pre.textContent = res.logs;
      pre.scrollTop = pre.scrollHeight;
    }
  } catch (err) {
    console.warn("fetchRecorderLogs err:", err);
  }
}

function renderRecorder(rec) {
  if (!rec) return;
  const isRunning = !!rec.is_running;
  const statusVal = $("#rec-status-val");
  const streamVal = $("#rec-stream-val");
  const storageVal = $("#rec-storage-val");
  const roomsVal = $("#rec-rooms-val");
  const badge = $("#tab-recorder-badge");
  const startBtn = $("#btn-start-recorder");
  const stopBtn = $("#btn-stop-recorder");

  if (statusVal) {
    statusVal.textContent = isRunning ? `🟢 运行中 (PID: ${rec.pid})` : "⚪ 未运行";
    statusVal.style.color = isRunning ? "#16a34a" : "#64748b";
  }
  if (badge) {
    badge.style.display = isRunning ? "inline-block" : "none";
    badge.textContent = rec.active_stream_count > 0 ? `录制中(${rec.active_stream_count})` : "监控中";
    badge.className = `tab-badge ${rec.active_stream_count > 0 ? "running-badge" : ""}`;
  }
  if (startBtn) startBtn.disabled = isRunning;
  if (stopBtn) stopBtn.disabled = !isRunning;

  if (streamVal) {
    if (rec.active_stream_count > 0) {
      const names = (rec.ffmpeg_streams || []).map(s => s.anchor).join(" | ");
      streamVal.textContent = `🔴 捕获中 (${rec.active_stream_count}): ${names}`;
      streamVal.style.color = "#ef4444";
    } else {
      streamVal.textContent = "0 场 (待机检测)";
      streamVal.style.color = "#0284c7";
    }
  }
  if (storageVal) storageVal.textContent = `${rec.total_recordings_size_gb || 0} GB`;
  if (roomsVal) roomsVal.textContent = `${rec.rooms ? rec.rooms.length : 0} 个主播`;

  // 渲染监控直播间列表表格
  const tbody = $("#recorder-rooms-body");
  if (tbody && rec.rooms) {
    if (!rec.rooms.length) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:20px;">暂无监控直播间，可在下方添加</td></tr>`;
    } else {
      tbody.innerHTML = rec.rooms.map(r => `
        <tr>
          <td><span class="badge ${r.enabled ? "published" : "failed"}">${r.enabled ? "启用" : "禁用"}</span></td>
          <td><b>${esc(r.name || "未命名")}</b></td>
          <td><span style="color:#0284c7;font-weight:600;">${esc(r.platform || "直播")}</span></td>
          <td style="word-break:break-all;font-family:monospace;font-size:12px;">${esc(r.url)}</td>
          <td style="text-align:right;">
            <button class="danger" style="padding:4px 8px;font-size:11px;" onclick="deleteRecorderRoom('${encodeURIComponent(r.url)}')">删除</button>
          </td>
        </tr>
      `).join("");
    }
  }
}

async function startRecorderService() {
  try {
    toast("正在启动直播录制服务...", "info");
    const res = await safeFetchJson("/api/recorder/start", { method: "POST" });
    toast(res.message || "启动完成", res.success ? "success" : "error");
    await fetchRecorderStatus();
    await fetchRecorderLogs();
  } catch (err) {
    toast("启动失败: " + err.message, "error");
  }
}

async function stopRecorderService() {
  const ok = await showConfirm("停止直播录制服务", "确定要停止 DouyinLiveRecorder 录制服务吗？\n如果当前正在录制直播，将安全收尾分段并关闭。", true);
  if (!ok) return;
  try {
    toast("正在停止录制服务...", "info");
    const res = await safeFetchJson("/api/recorder/stop", { method: "POST" });
    toast(res.message || "已停止", "info");
    await fetchRecorderStatus();
  } catch (err) {
    toast("停止失败: " + err.message, "error");
  }
}

async function restartRecorderService() {
  try {
    toast("正在重启录制服务...", "info");
    const res = await safeFetchJson("/api/recorder/restart", { method: "POST" });
    toast(res.message || "已重启", res.success ? "success" : "error");
    await fetchRecorderStatus();
  } catch (err) {
    toast("重启失败: " + err.message, "error");
  }
}

async function addRecorderRoom() {
  const urlInput = $("#new-room-url");
  const nameInput = $("#new-room-name");
  const url = urlInput ? urlInput.value.trim() : "";
  const name = nameInput ? nameInput.value.trim() : "";
  if (!url) {
    toast("请输入直播间 URL", "error");
    return;
  }
  try {
    const res = await safeFetchJson("/api/recorder/rooms/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, name })
    });
    toast(`已添加直播间：${name || url}`, "success");
    if (urlInput) urlInput.value = "";
    if (nameInput) nameInput.value = "";
    if (data.recorder) data.recorder.rooms = res.rooms;
    renderRecorder({ rooms: res.rooms, ...data.recorder });
  } catch (err) {
    toast("添加失败: " + err.message, "error");
  }
}

async function deleteRecorderRoom(encodedUrl) {
  const url = decodeURIComponent(encodedUrl);
  const ok = await showConfirm("删除直播间", `确定要移除直播间【${url}】吗？`, true);
  if (!ok) return;
  try {
    const res = await safeFetchJson("/api/recorder/rooms/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url })
    });
    toast("已移除直播间", "success");
    if (data.recorder) data.recorder.rooms = res.rooms;
    renderRecorder({ rooms: res.rooms, ...data.recorder });
  } catch (err) {
    toast("删除失败: " + err.message, "error");
  }
}

// 绑定录制器事件
const btnStartRec = $("#btn-start-recorder");
if (btnStartRec) btnStartRec.onclick = startRecorderService;

const btnStopRec = $("#btn-stop-recorder");
if (btnStopRec) btnStopRec.onclick = stopRecorderService;

const btnRestartRec = $("#btn-restart-recorder");
if (btnRestartRec) btnRestartRec.onclick = restartRecorderService;

const btnRefreshRec = $("#btn-refresh-recorder");
if (btnRefreshRec) btnRefreshRec.onclick = () => { fetchRecorderStatus(); fetchRecorderLogs(); };

const btnAddRoom = $("#btn-add-room");
if (btnAddRoom) btnAddRoom.onclick = addRecorderRoom;

const btnCopyRecLog = $("#btn-copy-rec-log");
if (btnCopyRecLog) {
  btnCopyRecLog.onclick = () => {
    const pre = $("#recorder-log-view");
    if (pre) {
      navigator.clipboard.writeText(pre.textContent).then(() => toast("日志已复制", "success"));
    }
  };
}

const btnReloadRecLog = $("#btn-reload-rec-log");
if (btnReloadRecLog) btnReloadRecLog.onclick = fetchRecorderLogs;

// 素材事件
$("#source-search").addEventListener("input", renderSources);
$("#source-body").addEventListener("change", event => {
  const box = event.target.closest(".source-select");
  if (!box) return;
  const path = decodeURIComponent(box.dataset.source);
  box.checked ? selectedSources.add(path) : selectedSources.delete(path);
  renderSources();
});
$("#select-cleanable-sources").onclick = () => {
  visibleSources().filter(sourceCanDelete).forEach(x => selectedSources.add(x.path));
  renderSources();
};
$("#clear-source-selection").onclick = () => {
  selectedSources.clear();
  renderSources();
};
$("#delete-selected-sources").onclick = cleanupSelectedSources;
$("#source-filters").addEventListener("click", event => {
  const button = event.target.closest("[data-filter]");
  if (!button) return;
  sourceFilter = button.dataset.filter;
  renderSourceFilters();
  renderSources();
});

// 底部悬浮操作栏事件
const floatingDeleteBtn = $("#floating-delete-btn");
if (floatingDeleteBtn) floatingDeleteBtn.onclick = cleanupSelectedSources;
const floatingCancelBtn = $("#floating-cancel-btn");
if (floatingCancelBtn) floatingCancelBtn.onclick = () => {
  selectedSources.clear();
  renderSources();
};

// 成片分段切换 (待发布 / 已发布 / 全部成片)
const stageTabs = $("#clip-stage-tabs");
if (stageTabs) {
  stageTabs.addEventListener("click", event => {
    const btn = event.target.closest(".stage-tab");
    if (!btn) return;
    document.querySelectorAll(".stage-tab").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    currentClipStage = btn.dataset.stage;
    clipPage = 1;
    selectedClips.clear();
    const pendingActions = $("#pending-actions-group");
    const publishedActions = $("#published-actions-group");
    if (pendingActions && publishedActions) {
      if (currentClipStage === "published") {
        pendingActions.style.display = "none";
        publishedActions.style.display = "inline-flex";
      } else {
        pendingActions.style.display = "inline-flex";
        publishedActions.style.display = "none";
      }
    }
    renderClips();
  });
}

// 视图切换器 (⊞ 网格 vs ☰ 列表)
const viewSwitcher = $("#view-switcher");
if (viewSwitcher) {
  viewSwitcher.addEventListener("click", event => {
    const btn = event.target.closest(".view-btn");
    if (!btn) return;
    document.querySelectorAll(".view-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    currentViewMode = btn.dataset.view;
    renderClips();
  });
}

// 成片筛选与排序事件
$("#clip-filters").addEventListener("click", event => {
  const button = event.target.closest("[data-clip-filter]");
  if (!button) return;
  document.querySelectorAll(".clip-filter").forEach(b => b.classList.remove("active"));
  button.classList.add("active");
  clipFilter = button.dataset.clipFilter;
  clipPage = 1;
  renderClips();
});

$("#clip-sort").addEventListener("change", event => {
  clipSort = event.target.value;
  clipPage = 1;
  renderClips();
});

$("#clip-search").addEventListener("input", () => {
  clipPage = 1;
  renderClips();
});

// 成片复选框事件
$("#clips").addEventListener("change", event => {
  const box = event.target.closest("input[data-output]");
  if (!box) return;
  box.checked ? selectedClips.add(box.dataset.output) : selectedClips.delete(box.dataset.output);
});

// 实时字数统计监听 (包括抽屉与卡片)
document.addEventListener("input", event => {
  const isTitle = event.target.classList.contains("publish-title");
  const isContent = event.target.classList.contains("publish-content");
  if (!isTitle && !isContent) return;

  const output = event.target.dataset.output;
  if (!output) return;

  const container = event.target.closest(".publish-editor");
  if (!container) return;
  const title = container.querySelector(".publish-title")?.value || "";
  const content = container.querySelector(".publish-content")?.value || "";
  unsavedEdits.set(output, { title, content });

  if (isTitle) {
    const countEl = container.querySelector(".char-count");
    if (countEl) {
      countEl.textContent = `${title.length}/100`;
      countEl.className = `char-count ${title.length > 100 ? "danger" : (title.length >= 85 ? "warning" : "")}`;
    }
  } else if (isContent) {
    const countEls = container.querySelectorAll(".char-count");
    const countEl = countEls[countEls.length - 1];
    if (countEl) {
      countEl.textContent = `${content.length}/2000`;
      countEl.className = `char-count ${content.length > 2000 ? "danger" : (content.length >= 1800 ? "warning" : "")}`;
    }
  }
});

$("#select-all-pending").onclick = () => {
  data.clips.filter(x => x.exists && x.douyin_status !== "published").forEach(x => selectedClips.add(x.output));
  renderClips();
};

$("#upload-selected").onclick = () => {
  const outputs = [...selectedClips];
  if (!outputs.length) {
    toast("请先选择待发布成片", "error");
    return;
  }
  startJob("upload_selected", { outputs, ...publishSettings() });
};

$("#cancel-auto-publish").onclick = cancelAutoPublish;

// 抽屉关闭事件
$("#close-clip-drawer").onclick = closeClipDrawer;
$("#close-drawer-backdrop").onclick = closeClipDrawer;

// 播放弹窗事件
$("#close-video-modal").onclick = closeClipPlayer;
$("#video-modal").addEventListener("click", event => {
  if (event.target.id === "video-modal") closeClipPlayer();
});

// 画面比例与铺满切换按钮
$$(".v-ratio-btn").forEach(btn => {
  btn.onclick = () => setVideoRatio(btn.dataset.ratio);
});
$$(".v-fit-btn").forEach(btn => {
  btn.onclick = () => setVideoFit(btn.dataset.fit);
});
const theaterBtn = $("#btn-theater-mode");
if (theaterBtn) theaterBtn.onclick = toggleTheaterMode;

const fsBtn = $("#btn-fullscreen-mode");
if (fsBtn) fsBtn.onclick = toggleFullscreenMode;

// 监听浏览器全屏变化
document.addEventListener("fullscreenchange", updateFullscreenBtnState);
document.addEventListener("webkitfullscreenchange", updateFullscreenBtnState);

// 双击播放画面：循环切换 完整包含 -> 裁切铺满(无黑边) -> 拉伸铺满
const clipPlayer = $("#clip-player");
if (clipPlayer) {
  clipPlayer.addEventListener("dblclick", event => {
    event.preventDefault();
    cycleVideoFit();
  });
}

// 页面 100% 宽屏铺满屏幕切换
const fluidToggleBtn = $("#toggle-page-fluid");
if (fluidToggleBtn) {
  fluidToggleBtn.onclick = toggleFluidLayout;
}

document.addEventListener("keydown", event => {
  const isVideoOpen = $("#video-modal").classList.contains("open");
  const isTyping = ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName);

  if (event.key === "Escape") {
    closeClipPlayer();
    closeClipDrawer();
    closeConfirm(false);
    closeAiConfigModal();
    closeTrafficInsights();
  } else if (isVideoOpen && !isTyping) {
    if (event.key === "f" || event.key === "F") {
      event.preventDefault();
      toggleFullscreenMode();
    } else if (event.key === "t" || event.key === "T") {
      event.preventDefault();
      toggleTheaterMode();
    } else if (event.code === "Space") {
      event.preventDefault();
      const v = $("#clip-player");
      if (v) {
        if (v.paused) v.play();
        else v.pause();
      }
    } else if (event.key === "m" || event.key === "M") {
      event.preventDefault();
      const v = $("#clip-player");
      if (v) {
        v.muted = !v.muted;
        showVideoHud(v.muted ? "已静音" : "恢复声音");
      }
    }
  }
});

// 确认弹窗事件绑定
const confirmOk = $("#confirm-ok-btn");
const confirmCancel = $("#confirm-cancel-btn");
const confirmClose = $("#confirm-close-btn");
const confirmBackdrop = $("#confirm-backdrop");
if (confirmOk) confirmOk.onclick = () => closeConfirm(true);
if (confirmCancel) confirmCancel.onclick = () => closeConfirm(false);
if (confirmClose) confirmClose.onclick = () => closeConfirm(false);
if (confirmBackdrop) confirmBackdrop.onclick = () => closeConfirm(false);

// 批量操作：批量AI写文案 & 批量删除成片
async function batchAiWrite() {
  let targets = [];
  if (selectedClips.size > 0) {
    targets = data.clips.filter(c => selectedClips.has(c.output) && c.exists);
  } else {
    targets = visibleClips().filter(c => (!c.publish_content || c.publish_content.startsWith("【董路足球")) && c.exists);
    if (!targets.length) {
      targets = visibleClips().filter(c => c.exists);
    }
  }
  if (!targets.length) {
    toast("当前没有可生成文案的成片", "info");
    return;
  }

  const ok = await showConfirm(
    "批量 AI 撰写文案",
    `即将为选中的 ${targets.length} 条成片依次调用 AI 大模型生成专业足球评论文案。\n这可能需要一些时间，请保持网页开启。是否继续？`
  );
  if (!ok) return;

  const btn = $("#batch-ai-write");
  const originalText = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
  }
  let successCount = 0;
  let failCount = 0;
  window.__isBatchAiWriting = true;

  try {
    for (let i = 0; i < targets.length; i++) {
      const clip = targets[i];
      if (btn) btn.innerHTML = `🤖 生成中 (${i + 1}/${targets.length})...`;
      toast(`正在生成第 ${i + 1}/${targets.length} 条文案：${clip.title || clip.name}...`, "info");
      try {
        const resp = await fetch("/api/generate-publish-text", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ output: clip.output, style: "tactical_youth" })
        });
        const res = await resp.json();
        if (resp.ok) {
          successCount++;
        } else {
          failCount++;
        }
      } catch (err) {
        failCount++;
      }
    }
  } finally {
    window.__isBatchAiWriting = false;
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalText;
    }
  }
  toast(`批量生成完成：成功 ${successCount} 条，失败 ${failCount} 条`, successCount > 0 ? "success" : "error");
  await refresh();
}

async function batchDeleteClips() {
  const outputs = [...selectedClips];
  if (!outputs.length) {
    toast("请先勾选需要删除的成片", "error");
    return;
  }
  const ok = await showConfirm(
    "批量删除未发布成片",
    `确认彻底删除勾选的 ${outputs.length} 个未发布成片并立即释放磁盘空间吗？\n\n注意：本地视频文件将被物理删除以节省磁盘空间（原录制素材及转写分析记录不受影响）。`,
    true
  );
  if (!ok) return;

  let deleted = 0;
  let failed = 0;
  for (const output of outputs) {
    try {
      const resp = await fetch("/api/delete-clip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ output })
      });
      if (resp.ok) {
        selectedClips.delete(output);
        deleted++;
      } else {
        failed++;
      }
    } catch (e) {
      failed++;
    }
  }
  toast(`批量删除完成：成功 ${deleted} 个，失败 ${failed} 个`, "info");
  await refresh();
}

const batchAiWriteBtn = $("#batch-ai-write");
if (batchAiWriteBtn) batchAiWriteBtn.onclick = batchAiWrite;

const batchDeleteClipsBtn = $("#batch-delete-clips");
if (batchDeleteClipsBtn) batchDeleteClipsBtn.onclick = batchDeleteClips;

async function batchCleanupPublished() {
  const outputs = [...selectedClips];
  const targets = (data.clips || []).filter(x => outputs.includes(x.output) && x.douyin_status === "published" && x.exists);
  if (!targets.length) {
    toast("请先勾选本地大视频文件仍存在的已发布成片", "error");
    return;
  }
  const totalMb = targets.reduce((sum, x) => sum + (x.size || 0), 0) / (1024 * 1024);
  const sizeDesc = totalMb >= 1024 ? `${(totalMb / 1024).toFixed(2)} GB` : `${totalMb.toFixed(1)} MB`;

  const ok = await showConfirm(
    "批量清理已发布成片本地视频",
    `确认清理勾选的 ${targets.length} 个已发布成片的本地视频文件以释放磁盘空间吗？\n\n预计将立即释放磁盘空间约 ${sizeDesc}！\n\n注意：仅删除本地大视频文件，抖音已发布状态、文案及流量归因记录将完整保留！`,
    true
  );
  if (!ok) return;

  let cleaned = 0;
  let failed = 0;
  for (const item of targets) {
    try {
      const resp = await fetch("/api/delete-clip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ output: item.output, cleanup_file_only: true })
      });
      if (resp.ok) {
        cleaned++;
        selectedClips.delete(item.output);
      } else {
        failed++;
      }
    } catch (e) {
      failed++;
    }
  }
  toast(`已成功清理 ${cleaned} 个成片的本地视频，释放约 ${sizeDesc} 空间！${failed ? `(${failed}个失败)` : ""}`, "success");
  await refresh();
}

async function batchDeletePublished() {
  const outputs = [...selectedClips];
  const targets = (data.clips || []).filter(x => outputs.includes(x.output) && x.douyin_status === "published");
  if (!targets.length) {
    toast("请先勾选需要彻底删除的已发布成片记录", "error");
    return;
  }
  const ok = await showConfirm(
    "彻底删除已发布成片记录",
    `确认彻底删除勾选的 ${targets.length} 条已发布成片记录吗？\n\n注意：本地视频文件（若存在）及抖音发布记录、流量归因数据将被彻底清除（原录制素材不受影响）。`,
    true
  );
  if (!ok) return;

  let deleted = 0;
  let failed = 0;
  for (const item of targets) {
    try {
      const resp = await fetch("/api/delete-clip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ output: item.output, cleanup_file_only: false })
      });
      if (resp.ok) {
        deleted++;
        selectedClips.delete(item.output);
      } else {
        failed++;
      }
    } catch (e) {
      failed++;
    }
  }
  toast(`已彻底删除 ${deleted} 条已发布成片记录${failed ? `(${failed}个失败)` : ""}`, "success");
  await refresh();
}

async function batchRevertPublished() {
  const outputs = [...selectedClips];
  const targets = (data.clips || []).filter(x => outputs.includes(x.output) && x.douyin_status === "published");
  if (!targets.length) {
    toast("请先勾选需要改回待发布的成片", "error");
    return;
  }
  let reverted = 0;
  for (const item of targets) {
    try {
      const resp = await fetch("/api/publish-status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index: item.index, platform: "douyin", status: "pending", output: item.output })
      });
      if (resp.ok) {
        reverted++;
        selectedClips.delete(item.output);
      }
    } catch (e) {
      console.error(e);
    }
  }
  toast(`已将 ${reverted} 条成片状态改回待发布`, "success");
  await refresh();
}

const selectAllPublishedBtn = $("#select-all-published");
if (selectAllPublishedBtn) {
  selectAllPublishedBtn.onclick = () => {
    (data.clips || []).filter(x => x.douyin_status === "published").forEach(x => selectedClips.add(x.output));
    renderClips();
  };
}

const deselectAllPublishedBtn = $("#deselect-all-published");
if (deselectAllPublishedBtn) {
  deselectAllPublishedBtn.onclick = () => {
    selectedClips.clear();
    renderClips();
  };
}

const batchCleanupPublishedBtn = $("#batch-cleanup-published");
if (batchCleanupPublishedBtn) batchCleanupPublishedBtn.onclick = batchCleanupPublished;

const batchDeletePublishedBtn = $("#batch-delete-published");
if (batchDeletePublishedBtn) batchDeletePublishedBtn.onclick = batchDeletePublished;

const batchRevertPublishedBtn = $("#batch-revert-published");
if (batchRevertPublishedBtn) batchRevertPublishedBtn.onclick = batchRevertPublished;

// AI 大模型配置面板交互逻辑
let currentAiConfig = null;

const API_PRESETS = {
  deepseek: {
    base_url: "https://api.deepseek.com/v1",
    model: "deepseek-chat"
  },
  qwen: {
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus"
  },
  siliconflow: {
    base_url: "https://api.siliconflow.cn/v1",
    model: "deepseek-ai/DeepSeek-V3"
  },
  zhipu: {
    base_url: "https://open.bigmodel.cn/api/paas/v4",
    model: "glm-4-flash"
  },
  moonshot: {
    base_url: "https://api.moonshot.cn/v1",
    model: "moonshot-v1-8k"
  },
  openai: {
    base_url: "https://api.openai.com/v1",
    model: "gpt-4o-mini"
  },
  custom: {
    base_url: "",
    model: ""
  }
};

function updateAiBadge(ai) {
  const pill = $("#ai-status-pill");
  const badgeText = $("#ai-badge-text");
  if (!pill || !badgeText) return;
  if (!ai) return;
  if (ai.provider === "api") {
    pill.classList.add("api-mode");
    badgeText.textContent = `云端 API: ${ai.model || "deepseek-chat"}`;
  } else {
    pill.classList.remove("api-mode");
    badgeText.textContent = `本地 AI: ${ai.model || "qwen2.5:7b"}`;
  }
}

async function loadAiConfig() {
  try {
    const res = await fetch("/api/ai-config");
    if (res.ok) {
      currentAiConfig = await res.json();
      if (currentAiConfig) {
        const provider = currentAiConfig.provider;
        const model = provider === "api" ? currentAiConfig.api?.model : currentAiConfig.ollama?.model;
        updateAiBadge({ provider, model });
      }
    }
  } catch (e) {
    console.error("加载 AI 配置失败:", e);
  }
}

function syncProviderCards(provider) {
  const ollamaCard = $("#card-provider-ollama");
  const apiCard = $("#card-provider-api");
  const ollamaSec = $("#section-ollama");
  const apiSec = $("#section-api");

  if (provider === "api") {
    if (ollamaCard) ollamaCard.classList.remove("active");
    if (apiCard) apiCard.classList.add("active");
    if (ollamaSec) ollamaSec.style.display = "none";
    if (apiSec) apiSec.style.display = "flex";
  } else {
    if (ollamaCard) ollamaCard.classList.add("active");
    if (apiCard) apiCard.classList.remove("active");
    if (ollamaSec) ollamaSec.style.display = "flex";
    if (apiSec) apiSec.style.display = "none";
  }
}

function openAiConfigModal() {
  const modal = $("#ai-config-modal");
  if (!modal) return;
  const testBox = $("#ai-test-result");
  if (testBox) testBox.style.display = "none";

  if (currentAiConfig) {
    const provider = currentAiConfig.provider || "ollama";
    const radio = document.querySelector(`input[name="ai-provider-radio"][value="${provider}"]`);
    if (radio) {
      radio.checked = true;
      syncProviderCards(provider);
    }
    if (currentAiConfig.ollama) {
      const urlEl = $("#ollama-base-url");
      const modelEl = $("#ollama-model");
      if (urlEl) urlEl.value = currentAiConfig.ollama.base_url || "http://127.0.0.1:11434";
      if (modelEl) modelEl.value = currentAiConfig.ollama.model || "qwen2.5:7b";
    }
    if (currentAiConfig.api) {
      const preset = currentAiConfig.api.preset || "deepseek";
      const presetEl = $("#api-preset-select");
      const urlEl = $("#api-base-url");
      const keyEl = $("#api-key");
      const modelEl = $("#api-model");
      if (presetEl) presetEl.value = preset;
      if (urlEl) urlEl.value = currentAiConfig.api.base_url || "https://api.deepseek.com/v1";
      if (keyEl) keyEl.value = currentAiConfig.api.api_key || "";
      if (modelEl) modelEl.value = currentAiConfig.api.model || "deepseek-chat";
    }
    const temp = (provider === "api" ? currentAiConfig.api?.temperature : currentAiConfig.ollama?.temperature) ?? 0.55;
    const tempSlider = $("#ai-temperature");
    const tempVal = $("#temp-val");
    if (tempSlider) tempSlider.value = temp;
    if (tempVal) tempVal.textContent = temp;
  }

  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
}

function closeAiConfigModal() {
  const modal = $("#ai-config-modal");
  if (!modal) return;
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
}

const aiPill = $("#ai-status-pill");
if (aiPill) aiPill.onclick = openAiConfigModal;

const closeAiModalBtn = $("#close-ai-config-modal");
if (closeAiModalBtn) closeAiModalBtn.onclick = closeAiConfigModal;

const cancelAiBtn = $("#btn-cancel-ai-config");
if (cancelAiBtn) cancelAiBtn.onclick = closeAiConfigModal;

const aiBackdrop = $("#ai-config-backdrop");
if (aiBackdrop) aiBackdrop.onclick = closeAiConfigModal;

// 切换提供商卡片点击
const cardOllama = $("#card-provider-ollama");
if (cardOllama) {
  cardOllama.onclick = () => {
    const radio = cardOllama.querySelector('input[type="radio"]');
    if (radio) radio.checked = true;
    syncProviderCards("ollama");
  };
}
const cardApi = $("#card-provider-api");
if (cardApi) {
  cardApi.onclick = () => {
    const radio = cardApi.querySelector('input[type="radio"]');
    if (radio) radio.checked = true;
    syncProviderCards("api");
  };
}

// 预设选择切换自动填入
const presetSelect = $("#api-preset-select");
if (presetSelect) {
  presetSelect.onchange = e => {
    const presetKey = e.target.value;
    const p = API_PRESETS[presetKey];
    if (p && presetKey !== "custom") {
      const urlEl = $("#api-base-url");
      const modelEl = $("#api-model");
      if (urlEl) urlEl.value = p.base_url;
      if (modelEl) modelEl.value = p.model;
    }
  };
}

// 密钥可见性切换
const toggleKeyBtn = $("#toggle-key-visibility");
if (toggleKeyBtn) {
  toggleKeyBtn.onclick = () => {
    const input = $("#api-key");
    if (!input) return;
    input.type = input.type === "password" ? "text" : "password";
  };
}

// 温度滑块
const tempSlider = $("#ai-temperature");
if (tempSlider) {
  tempSlider.oninput = e => {
    const valEl = $("#temp-val");
    if (valEl) valEl.textContent = e.target.value;
  };
}

// 测试连接
const btnTestAi = $("#btn-test-ai");
if (btnTestAi) {
  btnTestAi.onclick = async () => {
    const provider = document.querySelector('input[name="ai-provider-radio"]:checked')?.value || "ollama";
    const resultBox = $("#ai-test-result");
    if (!resultBox) return;
    resultBox.style.display = "block";
    resultBox.className = "ai-test-box loading";
    resultBox.innerHTML = `⏳ 正在连接测试 ${provider === "api" ? "云端大模型 API" : "本地 Ollama"}，请稍候...`;

    const temp = parseFloat($("#ai-temperature")?.value) || 0.55;
    const config = {
      provider,
      ollama: {
        base_url: $("#ollama-base-url")?.value.trim() || "http://127.0.0.1:11434",
        model: $("#ollama-model")?.value.trim() || "qwen2.5:7b",
        temperature: temp
      },
      api: {
        preset: $("#api-preset-select")?.value || "deepseek",
        base_url: $("#api-base-url")?.value.trim() || "https://api.deepseek.com/v1",
        api_key: $("#api-key")?.value.trim() || "",
        model: $("#api-model")?.value.trim() || "deepseek-chat",
        temperature: temp
      }
    };

    try {
      const res = await fetch("/api/ai-test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, config })
      });
      const data = await res.json();
      if (data.ok) {
        resultBox.className = "ai-test-box success";
        resultBox.innerHTML = `<strong>✓ 连接测试成功！</strong> (响应耗时 ${data.latency_ms}ms)<br>模型 <code>${esc(data.model)}</code> 回复：${esc(data.reply)}`;
      } else {
        resultBox.className = "ai-test-box error";
        resultBox.innerHTML = `<strong>✗ 连接测试失败</strong> (耗时 ${data.latency_ms}ms)<br>${esc(data.error || "未知错误")}`;
      }
    } catch (err) {
      resultBox.className = "ai-test-box error";
      resultBox.innerHTML = `<strong>✗ 请求异常</strong>：${esc(String(err))}`;
    }
  };
}

// 保存 AI 配置
const btnSaveAi = $("#btn-save-ai-config");
if (btnSaveAi) {
  btnSaveAi.onclick = async () => {
    const provider = document.querySelector('input[name="ai-provider-radio"]:checked')?.value || "ollama";
    const temp = parseFloat($("#ai-temperature")?.value) || 0.55;
    const payload = {
      provider,
      ollama: {
        base_url: $("#ollama-base-url")?.value.trim() || "http://127.0.0.1:11434",
        model: $("#ollama-model")?.value.trim() || "qwen2.5:7b",
        temperature: temp
      },
      api: {
        preset: $("#api-preset-select")?.value || "deepseek",
        base_url: $("#api-base-url")?.value.trim() || "https://api.deepseek.com/v1",
        api_key: $("#api-key")?.value.trim() || "",
        model: $("#api-model")?.value.trim() || "deepseek-chat",
        temperature: temp
      }
    };

    try {
      const res = await fetch("/api/ai-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const updated = await res.json();
      if (!res.ok) {
        toast(updated.error || "保存失败", "error");
        return;
      }
      currentAiConfig = updated;
      const model = provider === "api" ? updated.api?.model : updated.ollama?.model;
      updateAiBadge({ provider, model });
      toast(`AI 配置已保存：已切换为 ${provider === "api" ? "云端 API" : "本地 Ollama"} (${model})`, "success");
      closeAiConfigModal();
      await refresh();
    } catch (err) {
      toast("保存 AI 配置失败：" + err, "error");
    }
  };
}

// 初始化加载 AI 配置
loadAiConfig();

// 日志复制事件
$("#copy-log-btn").onclick = () => {
  const logView = $("#log-view");
  const text = logView.textContent;
  if (!text || text === "等待任务……") {
    toast("暂无可复制的日志", "info");
    return;
  }
  navigator.clipboard.writeText(text).then(() => {
    toast("日志已复制到剪贴板", "success");
  });
};

// 漏斗流程条节点点击联动
document.querySelectorAll(".funnel-step").forEach(step => {
  step.onclick = () => {
    const tab = step.dataset.targetTab;
    const filter = step.dataset.targetFilter;
    if (!tab) return;

    const tabBtn = document.querySelector(`.tab[data-tab="${tab}"]`);
    if (tabBtn) tabBtn.click();

    if (tab === "sources") {
      sourceFilter = filter || "all";
      renderSourceFilters();
      renderSources();
    } else if (tab === "clips") {
      if (filter === "needs_copy" || filter === "ready_copy") {
        clipFilter = filter;
      } else {
        clipFilter = "all";
      }
      const clipFilterBtn = document.querySelector(`[data-clip-filter="${clipFilter}"]`);
      if (clipFilterBtn) {
        document.querySelectorAll(".clip-filter").forEach(b => b.classList.remove("active"));
        clipFilterBtn.classList.add("active");
      }
      clipPage = 1;
      renderClips();
    }
  };
});

// 一键瘦身快捷操作
const quickCleanBtn = $("#quick-clean-btn");
if (quickCleanBtn) {
  quickCleanBtn.onclick = () => {
    const sourcesTab = document.querySelector('.tab[data-tab="sources"]');
    if (sourcesTab) sourcesTab.click();
    sourceFilter = "clipped";
    renderSourceFilters();
    visibleSources().filter(sourceCanDelete).forEach(x => selectedSources.add(x.path));
    renderSources();
    const count = selectedSources.size;
    const gb = data.storage?.cleanable_gb || 0;
    if (count > 0) {
      toast(`已自动全选 ${count} 个已剪辑原素材（共可释放约 ${gb} GB），点击“删除所选原素材”即可清理！`, "success");
    } else {
      toast("当前没有可清理的已剪辑原素材", "info");
    }
  };
}

// 点击顶部扫描徽章可随时手动立即重新扫描
const scanPill = $("#auto-scan-pill");
if (scanPill) {
  scanPill.onclick = async () => {
    toast("正在扫描录制目录新视频……", "info");
    await refresh({ scan: true });
    toast("新素材扫描完成并已同步！", "success");
  };
}

// 流量监控相关操作与交互
async function saveDrawerTraffic(output) {
  const play = parseInt($("#drawer-traffic-play")?.value) || 0;
  const like = parseInt($("#drawer-traffic-like")?.value) || 0;
  const comment = parseInt($("#drawer-traffic-comment")?.value) || 0;
  const share = parseInt($("#drawer-traffic-share")?.value) || 0;

  try {
    const result = await safeFetchJson("/api/traffic/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        output,
        play_count: play,
        like_count: like,
        comment_count: comment,
        share_count: share
      })
    });
    toast("流量数据已保存更新！", "success");
    await refresh();
  } catch (err) {
    toast(err.message || "更新流量失败", "error");
  }
}

async function syncTrafficData() {
  const btn = $("#btn-sync-traffic");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳ 同步中...";
  }
  try {
    const data = await safeFetchJson("/api/traffic/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}"
    });
    toast(`流量数据已刷新同步！(已追踪 ${data.summary?.tracked_count || 0} 条切片)`, "success");
    await refresh();
  } catch (e) {
    toast(e.message || "流量同步失败", "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "🔄 刷新流量";
    }
  }
}

async function openTrafficInsights() {
  const modal = $("#traffic-insights-modal");
  if (!modal) return;
  const body = $("#traffic-insights-body");
  body.innerHTML = '<div class="insights-loading" style="padding:30px;text-align:center;color:var(--muted);">⏳ 正在分析各题材播放量与转化率...</div>';
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");

  try {
    const data = await safeFetchJson("/api/traffic");
    renderTrafficInsightsBody(data);
  } catch (err) {
    body.innerHTML = `<div class="error-text" style="padding:24px;line-height:1.7;background:#fff2f2;border-radius:10px;border:1px solid #fecaca;">
      <strong style="font-size:14px;color:#991b1b;display:block;margin-bottom:6px;">⚠️ 无法获取流量数据</strong>
      ${esc(err.message || String(err))}
    </div>`;
  }
}

function closeTrafficInsights() {
  const modal = $("#traffic-insights-modal");
  if (!modal) return;
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
}

function renderTrafficInsightsBody(data) {
  const body = $("#traffic-insights-body");
  if (!body) return;
  const s = data.summary || {};
  const rankings = data.keyword_ranking || [];
  const recs = data.recommendations || [];

  body.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;padding:12px;background:#f8faf9;border-radius:10px;border:1px solid var(--line);">
      <div><span style="font-size:11px;color:var(--muted);">总播放量</span><div style="font-size:16px;font-weight:800;color:var(--green);">${formatTrafficNum(s.total_plays || 0)}</div></div>
      <div><span style="font-size:11px;color:var(--muted);">总点赞</span><div style="font-size:16px;font-weight:800;">${formatTrafficNum(s.total_likes || 0)}</div></div>
      <div><span style="font-size:11px;color:var(--muted);">🔥 爆款切片率</span><div style="font-size:16px;font-weight:800;color:#ea580c;">${s.viral_count || 0}条 / ${s.tracked_count || 0}条</div></div>
      <div><span style="font-size:11px;color:var(--muted);">均互动率</span><div style="font-size:16px;font-weight:800;">${s.avg_interaction_rate_pct || 0}%</div></div>
    </div>

    <div>
      <h4 style="margin:0 0 8px;font-size:14px;color:var(--ink);">📈 关键词题材流量排行与 AI 建议权重</h4>
      <div style="overflow-x:auto;">
        <table class="kw-rank-table">
          <thead>
            <tr>
              <th>题材关键词</th>
              <th>已剪辑发布数</th>
              <th>场均播放量</th>
              <th>场均点赞</th>
              <th>AI 优化权重建议</th>
            </tr>
          </thead>
          <tbody>
            ${rankings.map((r, i) => `
              <tr>
                <td><strong>${i + 1}. ${esc(r.keyword)}</strong></td>
                <td>${r.count} 条</td>
                <td><strong>${formatTrafficNum(r.avg_plays)}</strong></td>
                <td>${formatTrafficNum(r.avg_likes)}</td>
                <td>
                  <span class="weight-badge ${r.score_weight_recommendation > 1.2 ? 'high' : ''}">
                    ${r.score_weight_recommendation > 1.0 ? '提权' : (r.score_weight_recommendation < 0.8 ? '降权' : '保持')} ${r.score_weight_recommendation}x
                  </span>
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </div>

    <div class="rec-box">
      <h4>💡 AI 流量归因诊断与策略建议</h4>
      ${recs.map(r => `<div class="rec-item">${esc(r)}</div>`).join("")}
    </div>
  `;
}

async function applyTrafficWeights() {
  const btn = $("#btn-apply-traffic-weights");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳ 正在写入切片优化权重...";
  }
  try {
    const data = await safeFetchJson("/api/traffic/apply-weights", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}"
    });
    toast(`高流量题材权重优化成功！已提权 ${data.top_keywords.join("、")}`, "success");
    closeTrafficInsights();
    await refresh();
  } catch (e) {
    toast(e.message || "应用权重失败", "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "⚡ 一键应用 AI 流量权重优化";
    }
  }
}

// 流量事件绑定
const btnSyncTraffic = $("#btn-sync-traffic");
if (btnSyncTraffic) btnSyncTraffic.onclick = syncTrafficData;

const btnTrafficInsights = $("#btn-traffic-insights");
if (btnTrafficInsights) btnTrafficInsights.onclick = openTrafficInsights;

const closeTrafficBtn = $("#close-traffic-modal");
if (closeTrafficBtn) closeTrafficBtn.onclick = closeTrafficInsights;

const trafficBackdrop = $("#traffic-insights-backdrop");
if (trafficBackdrop) trafficBackdrop.onclick = closeTrafficInsights;

const btnCloseTrafficInsights = $("#btn-close-traffic-insights");
if (btnCloseTrafficInsights) btnCloseTrafficInsights.onclick = closeTrafficInsights;

const btnApplyTrafficWeights = $("#btn-apply-traffic-weights");
if (btnApplyTrafficWeights) btnApplyTrafficWeights.onclick = applyTrafficWeights;

// 🎯 标杆爆款雷达与同款拦截系统 (Benchmark Radar Logic)
function updateRadarBadge(radar) {
  const badge = $("#radar-breaking-badge");
  if (!badge) return;
  const count = radar.breaking_count ?? 0;
  badge.textContent = count;
  badge.style.display = count > 0 ? "inline-block" : "none";
}

async function openRadarModal() {
  const modal = $("#benchmark-radar-modal");
  if (!modal) return;
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
  await loadRadarData();
}

function closeRadarModal() {
  const modal = $("#benchmark-radar-modal");
  if (!modal) return;
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
}

async function loadRadarData() {
  const container = $("#radar-items-container");
  if (container) {
    container.innerHTML = '<div class="insights-loading" style="padding:24px;text-align:center;color:var(--muted);">正在侦测标杆实时爆款并比对素材库...</div>';
  }
  try {
    const data = await safeFetchJson("/api/radar");
    renderRadarData(data);
  } catch (err) {
    if (container) {
      container.innerHTML = `<div class="error-text" style="padding:20px;line-height:1.7;background:#fff2f2;border-radius:10px;border:1px solid #fecaca;">
        <strong style="font-size:14px;color:#991b1b;display:block;margin-bottom:6px;">⚠️ 无法获取标杆雷达数据</strong>
        ${esc(err.message || String(err))}
      </div>`;
    }
  }
}

function renderRadarData(data) {
  const trackedEl = $("#radar-tracked-count");
  const breakingEl = $("#radar-breaking-stat");
  const matchedEl = $("#radar-matched-stat");
  const container = $("#radar-items-container");

  if (trackedEl) trackedEl.textContent = (data.tracked_accounts || []).length;
  if (breakingEl) breakingEl.textContent = data.breaking_count || 0;
  if (matchedEl) matchedEl.textContent = data.matched_sources_count || 0;

  // 渲染监控账号列表
  const accountsList = $("#radar-accounts-list");
  if (accountsList) {
    const accounts = data.tracked_accounts || [];
    if (!accounts.length) {
      accountsList.innerHTML = '<span style="font-size:12px;color:var(--muted);padding:4px 0;">暂无监控账号，请在下方表单添加</span>';
    } else {
      accountsList.innerHTML = accounts.map(a => `
        <div class="account-chip">
          <span class="platform-tag">${esc(a.platform === "douyin" ? "抖音" : (a.platform === "kuaishou" ? "快手" : (a.platform === "channels" ? "视频号" : "小红书")))}</span>
          <span>${esc(a.name)}</span>
          <button class="btn-del-account" title="移除该监控账号" onclick="deleteTrackedAccount('${esc(a.id)}')">✕</button>
        </div>
      `).join("");
    }
  }

  if (!container) return;

  const items = data.items || [];
  if (!items.length) {
    container.innerHTML = '<div class="empty-state">当前雷达爆款列表为空（因平台反爬限制无法静默抓取账号主页）。可点击右上角【📥 载入标杆范例】或【+ 手动录入同行爆款】，也可直接在上方输入爆款标题搜自己录像同款！</div>';
    return;
  }

  container.innerHTML = items.map(item => {
    const isBreaking = item.is_breaking;
    const v = item.velocity || 0;
    const hasMatch = item.has_match;
    const match = item.best_match;

    let matchHtml = "";
    if (hasMatch && match) {
      matchHtml = `
        <div class="match-box">
          <div class="match-head">
            <span class="match-status">✅ 在素材库中定位到同款 (匹配度 ${match.match_score}%)</span>
            <span style="font-size:11px;color:var(--muted);">${esc(match.source_name)} · ${formatDuration(match.start)} - ${formatDuration(match.end)}</span>
          </div>
          <div class="match-snippet">
            " ${esc(match.snippet)} "
          </div>
          <div class="match-actions">
            ${match.source_exists ? `
              <button class="btn-quick-cut" data-source="${esc(match.source_path)}" data-start="${match.start}" data-end="${match.end}" data-title="${esc(item.title)}">
                ✂️ 一键跟剪同款成片 (${match.duration}s)
              </button>
            ` : `
              <span style="font-size:12px;color:#b91c1c;background:#fef2f2;border:1px solid #fecaca;padding:4px 10px;border-radius:6px;">
                ⚠️ 该场直播原视频已清理，仅保留文本记录
              </span>
            `}
          </div>
        </div>
      `;
    } else {
      matchHtml = `
        <div class="match-box no-match">
          <div class="match-head">
            <span class="match-status not-found">未在现有录像转写中发现直接同款</span>
            <button class="secondary-sm" onclick="prefillRadarSearch('${esc(item.title).replace(/'/g, "\\'")}')">手动搜索相关素材</button>
          </div>
        </div>
      `;
    }

    return `
      <div class="radar-card ${isBreaking ? 'breaking' : ''}">
        <div class="radar-card-top">
          <div style="flex:1;">
            <h5 class="radar-title">${esc(item.title)}</h5>
            <div class="radar-author-meta">
              <span>👤 ${esc(item.author || "标杆同行")}</span>
              <span>👍 ${formatTrafficNum(item.likes || 0)} 赞</span>
              <div class="radar-kws">
                ${(item.keywords || []).map(k => `<span class="radar-kw-tag">#${esc(k)}</span>`).join("")}
              </div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            <span class="radar-v-badge ${isBreaking ? 'fire' : 'norm'}">
              ${isBreaking ? '🔥 实时爆发' : '⚡ 稳健上升'} +${Math.round(v)}/h
            </span>
            <button class="btn-del-radar" title="移除此项" onclick="deleteRadarItem('${item.id}')">✕</button>
          </div>
        </div>
        ${matchHtml}
      </div>
    `;
  }).join("");

  // 绑定一键跟剪按钮
  container.querySelectorAll(".btn-quick-cut").forEach(btn => {
    btn.onclick = async () => {
      const src = btn.getAttribute("data-source");
      const start = parseFloat(btn.getAttribute("data-start") || 0);
      const end = parseFloat(btn.getAttribute("data-end") || 0);
      const title = btn.getAttribute("data-title");
      await executeQuickCut(src, start, end, title, "标杆爆款雷达实时拦截跟剪", btn);
    };
  });
}

window.prefillRadarSearch = function(txt) {
  const input = $("#radar-search-input");
  if (input) {
    input.value = txt;
    searchRadarMatch();
  }
};

window.deleteTrackedAccount = async function(id) {
  try {
    await safeFetchJson("/api/radar/accounts/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id })
    });
    toast("已移除监控标杆账号", "info");
    await loadRadarData();
  } catch (e) {
    toast(e.message || "删除失败", "error");
  }
};

window.deleteRadarItem = async function(id) {
  try {
    await safeFetchJson("/api/radar/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id })
    });
    toast("已从雷达监控列表移除", "info");
    await loadRadarData();
  } catch (e) {
    toast(e.message || "删除失败", "error");
  }
};

async function searchRadarMatch() {
  const input = $("#radar-search-input");
  const query = (input ? input.value : "").trim();
  const resBox = $("#radar-search-results");
  if (!query) {
    toast("请输入要检索的话题或标杆文案", "info");
    return;
  }
  if (!resBox) return;

  resBox.style.display = "block";
  resBox.innerHTML = '<div style="padding:16px;text-align:center;color:var(--muted);font-size:12px;">🔍 正在全素材库转写文本中进行毫秒级全文匹配...</div>';

  try {
    const data = await safeFetchJson("/api/radar/match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query })
    });
    const matches = data.matches || [];
    if (!matches.length) {
      resBox.innerHTML = '<div style="padding:14px;text-align:center;color:var(--muted);font-size:12px;">未在当前录像素材中找到匹配片段，建议尝试其他关键词或导入新素材</div>';
      return;
    }

    resBox.innerHTML = `
      <div style="font-size:12px;color:var(--muted);margin-bottom:8px;">
        🎯 命中 <strong>${matches.length}</strong> 处录像素材：
      </div>
      <div style="display:flex;flex-direction:column;gap:8px;">
        ${matches.map(m => `
          <div class="match-box">
            <div class="match-head">
              <span class="match-status">匹配度 ${m.match_score}% · ${esc(m.source_name)}</span>
              <span style="font-size:11px;color:var(--muted);">${formatDuration(m.start)} - ${formatDuration(m.end)} (${m.duration}s)</span>
            </div>
            <div class="match-snippet">" ${esc(m.snippet)} "</div>
            <div class="match-actions">
              ${m.source_exists ? `
                <button class="btn-quick-cut" data-source="${esc(m.source_path)}" data-start="${m.start}" data-end="${m.end}" data-title="${esc(query)}">
                  ✂️ 一键跟剪此片段 (${m.duration}s)
                </button>
              ` : `
                <span style="font-size:12px;color:#b91c1c;background:#fef2f2;border:1px solid #fecaca;padding:4px 10px;border-radius:6px;">
                  ⚠️ 该场直播原视频已清理，仅保留文本记录
                </span>
              `}
            </div>
          </div>
        `).join("")}
      </div>
    `;

    resBox.querySelectorAll(".btn-quick-cut").forEach(btn => {
      btn.onclick = async () => {
        const src = btn.getAttribute("data-source");
        const start = parseFloat(btn.getAttribute("data-start") || 0);
        const end = parseFloat(btn.getAttribute("data-end") || 0);
        const title = btn.getAttribute("data-title");
        await executeQuickCut(src, start, end, title, "检索命中跟剪", btn);
      };
    });
  } catch (e) {
    resBox.innerHTML = `<div class="error-text">${esc(e.message || String(e))}</div>`;
  }
}

async function executeQuickCut(sourcePath, start, end, title, whyViral, btnEl) {
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.textContent = "⏳ 正在精确剪辑中...";
  }
  try {
    const res = await safeFetchJson("/api/radar/quick-cut", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_path: sourcePath,
        start: start,
        end: end,
        title: title,
        why_viral: whyViral,
      })
    });
    toast(`✂️ 跟剪成功！已生成成片并推入发布队列：${title}`, "success");
    if (btnEl) btnEl.textContent = "✅ 已跟剪入库";
    await refresh({ scan: false });
  } catch (e) {
    toast(e.message || "跟剪失败", "error");
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.textContent = "✂️ 一键跟剪同款成片";
    }
  }
}

// 标杆雷达事件绑定
const radarStatusPill = $("#radar-status-pill");
if (radarStatusPill) radarStatusPill.onclick = openRadarModal;

const closeRadarModalBtn = $("#close-radar-modal");
if (closeRadarModalBtn) closeRadarModalBtn.onclick = closeRadarModal;

const radarBackdrop = $("#radar-backdrop");
if (radarBackdrop) radarBackdrop.onclick = closeRadarModal;

const btnCloseRadar = $("#btn-close-radar");
if (btnCloseRadar) btnCloseRadar.onclick = closeRadarModal;

const btnRefreshRadar = $("#btn-refresh-radar");
if (btnRefreshRadar) btnRefreshRadar.onclick = loadRadarData;

const btnRadarSearch = $("#btn-radar-search");
if (btnRadarSearch) btnRadarSearch.onclick = searchRadarMatch;

const radarSearchInput = $("#radar-search-input");
if (radarSearchInput) {
  radarSearchInput.onkeydown = (e) => {
    if (e.key === "Enter") searchRadarMatch();
  };
}

const btnSeedRadar = $("#btn-seed-radar");
if (btnSeedRadar) {
  btnSeedRadar.onclick = async () => {
    btnSeedRadar.disabled = true;
    try {
      const res = await safeFetchJson("/api/radar/seed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}"
      });
      toast(`已载入 ${res.added || 0} 条标杆爆款范例并匹配素材库`, "success");
      await loadRadarData();
    } catch (e) {
      toast(e.message || "载入失败", "error");
    } finally {
      btnSeedRadar.disabled = false;
    }
  };
}

const btnShuffleRadar = $("#btn-shuffle-radar");
if (btnShuffleRadar) {
  btnShuffleRadar.onclick = async () => {
    btnShuffleRadar.disabled = true;
    try {
      const res = await safeFetchJson("/api/radar/shuffle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}"
      });
      toast(`已成功轮换 ${res.count || 0} 条全新标杆热点选题！`, "success");
      await loadRadarData();
    } catch (e) {
      toast(e.message || "换一批失败", "error");
    } finally {
      btnShuffleRadar.disabled = false;
    }
  };
}

const btnDiscoverRadar = $("#btn-discover-radar");
if (btnDiscoverRadar) {
  btnDiscoverRadar.onclick = async () => {
    btnDiscoverRadar.disabled = true;
    try {
      const res = await safeFetchJson("/api/radar/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}"
      });
      toast(`AI 已深度挖掘并录入 ${res.count || 0} 条高光热点议题！`, "success");
      await loadRadarData();
    } catch (e) {
      toast(e.message || "挖掘失败", "error");
    } finally {
      btnDiscoverRadar.disabled = false;
    }
  };
}

const btnToggleAddRadar = $("#btn-toggle-add-radar");
const addRadarForm = $("#add-radar-form");
if (btnToggleAddRadar && addRadarForm) {
  btnToggleAddRadar.onclick = () => {
    const open = addRadarForm.style.display !== "none";
    addRadarForm.style.display = open ? "none" : "flex";
    btnToggleAddRadar.textContent = open ? "+ 手动录入同行爆款" : "收起录入表单";
  };
}

const btnSubmitAddRadar = $("#btn-submit-add-radar");
if (btnSubmitAddRadar) {
  btnSubmitAddRadar.onclick = async () => {
    const titleInput = $("#new-radar-title");
    const authorInput = $("#new-radar-author");
    const velInput = $("#new-radar-velocity");
    const likesInput = $("#new-radar-likes");
    const title = (titleInput ? titleInput.value : "").trim();
    if (!title) {
      toast("请输入爆款标题或文案", "info");
      return;
    }
    btnSubmitAddRadar.disabled = true;
    try {
      await safeFetchJson("/api/radar/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          author: authorInput ? authorInput.value.trim() : "",
          velocity: parseFloat(velInput ? velInput.value : 500),
          likes: parseInt(likesInput ? likesInput.value : 5000),
        })
      });
      toast("新增标杆爆款记录成功！", "success");
      if (titleInput) titleInput.value = "";
      if (addRadarForm) addRadarForm.style.display = "none";
      if (btnToggleAddRadar) btnToggleAddRadar.textContent = "+ 手动录入同行爆款";
      await loadRadarData();
    } catch (e) {
      toast(e.message || "录入失败", "error");
    } finally {
      btnSubmitAddRadar.disabled = false;
    }
  };
}

// 👥 标杆监控账号面板与新增
const boxTrackedAccounts = $("#box-tracked-accounts");
const radarAccountsPanel = $("#radar-accounts-panel");
if (boxTrackedAccounts && radarAccountsPanel) {
  boxTrackedAccounts.onclick = () => {
    const isHidden = radarAccountsPanel.style.display === "none";
    radarAccountsPanel.style.display = isHidden ? "flex" : "none";
  };
}

const btnSubmitAddAccount = $("#btn-submit-add-account");
if (btnSubmitAddAccount) {
  btnSubmitAddAccount.onclick = async () => {
    const nameInput = $("#new-account-name");
    const platformSelect = $("#new-account-platform");
    const homepageInput = $("#new-account-homepage");

    const name = (nameInput ? nameInput.value : "").trim();
    if (!name) {
      toast("请输入标杆账号名称", "info");
      return;
    }

    btnSubmitAddAccount.disabled = true;
    try {
      await safeFetchJson("/api/radar/accounts/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name,
          platform: platformSelect ? platformSelect.value : "douyin",
          homepage: homepageInput ? homepageInput.value.trim() : "",
        })
      });
      toast(`成功添加监控标杆账号：${name}`, "success");
      if (nameInput) nameInput.value = "";
      if (homepageInput) homepageInput.value = "";
      await loadRadarData();
    } catch (err) {
      toast(err.message || "添加账号失败", "error");
    } finally {
      btnSubmitAddAccount.disabled = false;
    }
  };
}

// 🎬 标杆视频无水印下载与智能二次创作
const btnStartRemix = $("#btn-start-remix");
const remixUrlInput = $("#remix-url-input");
const remixStatusBox = $("#remix-status-box");

if (btnStartRemix) {
  btnStartRemix.onclick = async () => {
    const rawText = (remixUrlInput ? remixUrlInput.value : "").trim();
    if (!rawText) {
      toast("请先粘贴抖音或快手的视频分享链接", "info");
      return;
    }

    const chkSpeed = $("#chk-remix-speed");
    const speedFactor = chkSpeed && chkSpeed.checked ? 1.02 : 1.0;

    btnStartRemix.disabled = true;
    const origBtnText = btnStartRemix.textContent;
    btnStartRemix.textContent = "⏳ 正在解析并二次创作中 (约需15~30s)...";

    if (remixStatusBox) {
      remixStatusBox.style.display = "block";
      remixStatusBox.innerHTML = `
        <div style="display:flex;align-items:center;gap:8px;color:#047857;">
          <span class="pulse-dot"></span>
          <span>正在高速解析无水印原片、应用 1.02x 无感微变速、画质增强并由 AI 撰写全新爆款标题...</span>
        </div>
      `;
    }

    try {
      const res = await safeFetchJson("/api/remix/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: rawText,
          speed: speedFactor,
        })
      });

      if (remixStatusBox) {
        remixStatusBox.innerHTML = `
          <div style="color:#15803d;font-weight:800;font-size:14px;margin-bottom:6px;">
            🎉 二次创作大成功！已生成高画质成片并置顶入库
          </div>
          <div style="font-size:12px;color:#334155;line-height:1.6;margin-bottom:10px;">
            <strong>全新原创标题：</strong>${esc(res.title)} (${res.duration}秒)<br/>
            <strong>原作者归属：</strong>${esc(res.original_author)}<br/>
            <strong>文案预览：</strong>${esc(res.publish_content).slice(0, 80)}...
          </div>
          <div style="display:flex;gap:10px;">
            <button class="primary" style="padding:6px 14px;font-size:12px;" onclick="closeRadarModal(); switchTab('clips');">
              👀 立即去成片库查看 / 发布
            </button>
            <button class="secondary" style="padding:6px 14px;font-size:12px;" onclick="$('#remix-status-box').style.display='none';">
              继续二创下一条
            </button>
          </div>
        `;
      }

      if (remixUrlInput) remixUrlInput.value = "";
      toast(`二创成功！成片已就绪：${res.title}`, "success");
      await refresh({ scan: false });
    } catch (err) {
      if (remixStatusBox) {
        remixStatusBox.innerHTML = `
          <div class="error-text" style="color:#b91c1c;">
            <strong>⚠️ 二次创作失败：</strong>${esc(err.message || String(err))}
          </div>
        `;
      }
      toast(err.message || "二次创作失败", "error");
    } finally {
      btnStartRemix.disabled = false;
      btnStartRemix.textContent = origBtnText;
    }
  };
}

// 启动：进入网页或刷新时立即执行一次新素材扫描
initFluidLayout();
refresh({ scan: true });
setInterval(() => {
  if (!window.__isBatchAiWriting) refresh({ scan: false });
}, 15000); // 周期轮询仅同步状态，不触发扫描
