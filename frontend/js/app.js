import { api } from "./api.js";

const STORAGE_KEY = "wordsaga_active_session";
const THINKING_PREF_KEY = "wordsaga_enable_thinking";

function loadThinkingPref() {
  return localStorage.getItem(THINKING_PREF_KEY) === "1";
}

function saveThinkingPref(enabled) {
  localStorage.setItem(THINKING_PREF_KEY, enabled ? "1" : "0");
}

const STATUS_LABELS = {
  stage1: "读故事",
  stage2: "猜词义",
  stage3: "写卡片",
  stage4: "默写",
};

const state = {
  view: "home",
  homePath: "learn",
  mode: "frequency",
  sessionId: null,
  sessionMode: null,
  sessionMix: { review: 0, wrong: 0, new: 0 },
  stage: 1,
  vocabCount: 0,
  dueReview: { due_count: 0, words: [] },
  weakReview: { weak_count: 0 },
  resumableSession: null,
  skippedWords: [],
  sessionWords: [],
  wordProfile: null,
  stage1: null,
  stage2: null,
  stage3: null,
  stage3Report: null,
  stage4: null,
  doneSummary: null,
  wrongBook: [],
  loading: false,
  loadingText: "",
  generating: null,
};

const app = document.getElementById("app");
const toast = document.getElementById("toast");

function showToast(message) {
  toast.textContent = message;
  toast.classList.remove("hidden");
  setTimeout(() => toast.classList.add("hidden"), 4000);
}

function formatReviewWhen(iso) {
  const target = new Date(iso);
  const now = new Date();
  const diffMs = target - now;
  const days = Math.ceil(diffMs / 86400000);
  if (days <= 0) {
    return "今天";
  }
  if (days === 1) {
    return "明天";
  }
  if (days <= 7) {
    return `${days} 天后`;
  }
  return `${target.getMonth() + 1} 月 ${target.getDate()} 日`;
}

function memoryHint(card) {
  if (card.next_review_at) {
    return `下次复习：${formatReviewWhen(card.next_review_at)}`;
  }
  if (card.incomplete_due_at) {
    return `巩固提醒：${formatReviewWhen(card.incomplete_due_at)}`;
  }
  return "";
}

function persistSession() {
  if (!state.sessionId) {
    return;
  }
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      sessionId: state.sessionId,
      view: state.view,
      stage: state.stage,
    })
  );
}

function clearPersistedSession() {
  localStorage.removeItem(STORAGE_KEY);
}

function buildSessionMix(words) {
  const mix = { review: 0, wrong: 0, new: 0 };
  for (const row of words) {
    if (row.source === "review") {
      mix.review += 1;
    } else if (row.source === "wrong") {
      mix.wrong += 1;
    } else if (row.source === "new") {
      mix.new += 1;
    }
  }
  return mix;
}

function renderSessionMixHint() {
  if (state.sessionMode !== "frequency") {
    return "";
  }
  const mixed = state.sessionMix.review + state.sessionMix.wrong;
  if (mixed === 0) {
    return "";
  }
  let text = `本轮含 <strong>${mixed}</strong> 个复习词`;
  if (state.sessionMix.review > 0 && state.sessionMix.wrong > 0) {
    text += `（到期 ${state.sessionMix.review} · 错题 ${state.sessionMix.wrong}）`;
  } else if (state.sessionMix.wrong > 0) {
    text += `（错题巩固）`;
  }
  if (state.sessionMix.new > 0) {
    text += `，<strong>${state.sessionMix.new}</strong> 个新词`;
  }
  return `<p class="session-mix-hint">${text}</p>`;
}

function isRecallMode() {
  return state.sessionMode === "review" || state.sessionMode === "weak";
}

function recallModeLabel() {
  if (state.sessionMode === "weak") {
    return "薄弱巩固";
  }
  if (state.sessionMode === "review") {
    return "复习";
  }
  return "";
}

function applyCreatedSession(result) {
  const session = result.session;
  state.sessionId = session.id;
  state.sessionMode = session.mode;
  state.sessionWords = session.words.map((w) => w.word);
  state.sessionMix = buildSessionMix(session.words);
  state.skippedWords = result.skipped_words;
  persistSession();
}

function renderSkippedWordsHint() {
  if (!state.skippedWords.length) {
    return "";
  }
  const list = state.skippedWords.map((row) => escapeHtml(row.word)).join("、");
  return `<p class="skipped-words-hint">另有 <strong>${state.skippedWords.length}</strong> 个词暂无例句已跳过：${list}</p>`;
}

const EVENT_STAGE_LABELS = {
  1: "读故事",
  2: "猜词义",
  3: "写卡片",
  4: "默写",
};

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function highlightAnnotatedStory(text) {
  return escapeHtml(text).replace(
    /（([a-zA-Z'-]+)）/g,
    '<span class="hl-word">（$1）</span>'
  );
}

function extractJsonStringField(buffer, fieldName) {
  const marker = `"${fieldName}"`;
  const idx = buffer.indexOf(marker);
  if (idx === -1) {
    return "";
  }

  let i = idx + marker.length;
  while (i < buffer.length && /[\s:]/.test(buffer[i])) {
    i += 1;
  }
  if (buffer[i] !== '"') {
    return "";
  }
  i += 1;

  let result = "";
  while (i < buffer.length) {
    const ch = buffer[i];
    if (ch === "\\") {
      if (i + 1 >= buffer.length) {
        break;
      }
      const next = buffer[i + 1];
      if (next === "n") result += "\n";
      else if (next === "r") result += "\r";
      else if (next === "t") result += "\t";
      else if (next === "u" && i + 5 < buffer.length) {
        result += String.fromCharCode(parseInt(buffer.slice(i + 2, i + 6), 16));
        i += 6;
        continue;
      } else result += next;
      i += 2;
      continue;
    }
    if (ch === '"') {
      break;
    }
    result += ch;
    i += 1;
  }
  return result;
}

function getStreamingChapterView(gen) {
  if (gen.chapterIndex <= 0) {
    return { visible: false, label: "", storyHtml: "" };
  }

  const alreadyDone = gen.completedChapters.some(
    (ch) => ch.chapter_index === gen.chapterIndex
  );
  if (alreadyDone && !gen.streamText) {
    return { visible: false, label: "", storyHtml: "" };
  }

  const title = extractJsonStringField(gen.streamText, "title");
  const storyText = extractJsonStringField(gen.streamText, "annotated_story_zh");
  const label = title
    ? `第 ${gen.chapterIndex} 章 · ${title}`
    : storyText
      ? `第 ${gen.chapterIndex} 章 · 撰写中…`
      : `第 ${gen.chapterIndex} 章 · 构思中…`;

  if (!storyText) {
    const placeholder = gen.thinkingActive
      ? '<p class="stream-placeholder">模型正在深度思考，完成后会开始输出故事…</p>'
      : title
        ? '<p class="stream-placeholder">正文正在输出…</p>'
        : '<p class="stream-placeholder"><span class="stream-cursor" aria-hidden="true"></span></p>';
    return { visible: true, label, storyHtml: placeholder };
  }

  return {
    visible: true,
    label,
    storyHtml: `${highlightAnnotatedStory(storyText)}<span class="stream-cursor" aria-hidden="true"></span>`,
  };
}

function renderStepper(current) {
  const steps = isRecallMode()
      ? [
          { n: 3, label: "写卡片" },
          { n: 4, label: "默写" },
        ]
      : [
          { n: 1, label: "读故事" },
          { n: 2, label: "猜词义" },
          { n: 3, label: "写卡片" },
          { n: 4, label: "默写" },
        ];
  return `<div class="stepper ${isRecallMode() ? "stepper--review" : ""}">${steps
    .map((s) => {
      const cls = s.n === current ? "active" : s.n < current ? "done" : "";
      return `<div class="step ${cls}"><span>${s.n}</span>${s.label}</div>`;
    })
    .join("")}</div>`;
}

function renderResumeBanner() {
  const r = state.resumableSession;
  if (!r) {
    return "";
  }
  const modeLabel =
    r.mode === "review" ? "复习" : r.mode === "weak" ? "薄弱巩固" : "新学";
  let statusText;
  if (r.resume_kind === "generating_interrupted") {
    statusText = "故事生成中断";
  } else if (r.resume_kind === "generating") {
    statusText = "故事尚未生成";
  } else {
    statusText = `停在「${STATUS_LABELS[r.status]}」`;
  }
  const titlePart = r.story_title
    ? `《${escapeHtml(r.story_title)}》`
    : `${r.word_count} 个词`;
  return `
    <div class="resume-banner">
      <div class="resume-banner__text">
        <strong>继续上次${modeLabel}</strong>
        <span class="meta-line">${titlePart} · ${statusText}</span>
      </div>
      <button type="button" class="btn btn-primary" id="resumeBtn">继续</button>
    </div>`;
}

function renderLearnForm() {
  return `
    <p class="panel__section-title">新学设置</p>
    <div class="form-grid">
      <div class="mode-tabs">
        <button type="button" class="mode-tab ${state.mode === "frequency" ? "selected" : ""}" data-mode="frequency">
          <strong>词频计划</strong>
          按词频自动选词，混合复习
        </button>
        <button type="button" class="mode-tab ${state.mode === "manual" ? "selected" : ""}" data-mode="manual">
          <strong>自选练习</strong>
          指定单词，不推进词频
        </button>
      </div>

      <details class="style-details">
        <summary>故事风格（可选）</summary>
        <div class="style-details__body">
          <p class="style-details__hint">AI 会写一段原创小故事，风格每次可能不同。这里仅作参考提示。</p>
          <div class="field">
            <input id="style" value="日常治愈系原创小故事" />
          </div>
        </div>
      </details>

      <label class="thinking-option">
        <input type="checkbox" id="enableThinking" ${loadThinkingPref() ? "checked" : ""} />
        <span>启用模型深度思考</span>
      </label>
      <p class="panel__subtitle thinking-option__hint" id="thinkingHint" ${
        loadThinkingPref() ? "" : 'hidden'
      }>
        开启后模型会先进行链式推理再写故事，通常更慢（可能多等 1～3 分钟），期间界面会提示「思考中」。
      </p>

      ${
        state.mode === "frequency"
          ? `
        <div class="field">
          <label>词库范围</label>
          <select id="level">
            <option value="basic">四级</option>
            <option value="cet6">六级</option>
            <option value="all">全部</option>
          </select>
        </div>
        <div class="field">
          <label>本轮词数</label>
          <input id="count" type="number" min="1" max="300" value="5" />
        </div>
        <p class="panel__subtitle learn-mix-note">词频新学会自动混入约 30% 的到期/错题复习词，选词后界面会标明数量。</p>`
          : `
        <div class="field">
          <label>单词列表（空格或逗号分隔）</label>
          <textarea id="words" placeholder="investigate, dilemma, perspective"></textarea>
        </div>
        <p class="panel__subtitle learn-mix-note">自选练习不推进词频进度，可重复练习同一词；仍会记录学习事件与记忆曲线。</p>`
      }

      <div class="btn-row">
        <button type="button" class="btn btn-primary" id="startBtn">开始今天的词境</button>
      </div>
    </div>`;
}

function renderReviewForm() {
  const dueCount = state.dueReview.due_count;
  const defaultCount = dueCount > 0 ? Math.min(dueCount, 10) : 5;
  return `
    <p class="panel__section-title">复习设置</p>
    <div class="form-grid">
      <p class="panel__subtitle" style="margin-bottom:0.5rem;">
        ${
          dueCount > 0
            ? `有 <strong>${dueCount}</strong> 个词到了该见面的时候。复习会复用你之前学过的例句，不再生成新故事。`
            : "目前还没有到期的复习词。可以先新学几个单词。"
        }
      </p>
      <div class="field">
        <label>词库范围</label>
        <select id="reviewLevel">
          <option value="basic">四级</option>
          <option value="cet6">六级</option>
        </select>
      </div>
      <div class="field">
        <label>本轮复习词数</label>
        <input id="reviewCount" type="number" min="1" max="300" value="${defaultCount}" />
      </div>
      <div class="btn-row">
        <button type="button" class="btn btn-primary" id="startReviewBtn" ${dueCount === 0 ? "disabled" : ""}>
          开始复习
        </button>
      </div>
    </div>`;
}

function renderWeakForm() {
  const weakCount = state.weakReview.weak_count;
  const defaultCount = weakCount > 0 ? Math.min(weakCount, 10) : 5;
  return `
    <p class="panel__section-title">薄弱巩固设置</p>
    <div class="form-grid">
      <p class="panel__subtitle" style="margin-bottom:0.5rem;">
        ${
          weakCount > 0
            ? `有 <strong>${weakCount}</strong> 个词掌握不稳或常错。不推进新词频，专练薄弱项。`
            : "目前还没有需要薄弱巩固的词。可以先新学，或等出现错题后再来。"
        }
      </p>
      <div class="field">
        <label>词库范围</label>
        <select id="weakLevel">
          <option value="basic">四级</option>
          <option value="cet6">六级</option>
        </select>
      </div>
      <div class="field">
        <label>本轮词数</label>
        <input id="weakCount" type="number" min="1" max="300" value="${defaultCount}" />
      </div>
      <div class="btn-row">
        <button type="button" class="btn btn-primary" id="startWeakBtn" ${weakCount === 0 ? "disabled" : ""}>
          开始薄弱巩固
        </button>
      </div>
    </div>`;
}

function renderHome() {
  const dueCount = state.dueReview.due_count;
  const weakCount = state.weakReview.weak_count;
  let formHtml = renderLearnForm();
  if (state.homePath === "review") {
    formHtml = renderReviewForm();
  } else if (state.homePath === "weak") {
    formHtml = renderWeakForm();
  }
  return `
    <section class="panel">
      <h1 class="home-greeting">今天想学什么？</h1>
      ${renderResumeBanner()}
      <div class="entry-cards entry-cards--triple">
        <button type="button" class="entry-card ${state.homePath === "learn" ? "selected" : ""}" data-path="learn">
          <div class="entry-card__icon">📖</div>
          <span class="entry-card__title">新学</span>
          <span class="entry-card__desc">推进词频，读新故事，四步记忆。</span>
        </button>
        <button type="button" class="entry-card entry-card--review ${state.homePath === "review" ? "selected" : ""}" data-path="review">
          <div class="entry-card__icon">🌿</div>
          <span class="entry-card__title">复习</span>
          <span class="entry-card__desc">到期词再见面，复用历史例句。</span>
          ${
            dueCount > 0
              ? `<span class="entry-card__badge">${dueCount} 个词在等你</span>`
              : ""
          }
        </button>
        <button type="button" class="entry-card entry-card--weak ${state.homePath === "weak" ? "selected" : ""}" data-path="weak">
          <div class="entry-card__icon">🔥</div>
          <span class="entry-card__title">薄弱巩固</span>
          <span class="entry-card__desc">不推进词频，专练常错和掌握不稳的词。</span>
          ${
            weakCount > 0
              ? `<span class="entry-card__badge">${weakCount} 个词待巩固</span>`
              : ""
          }
        </button>
      </div>
      ${formHtml}
    </section>`;
}

function renderLoading() {
  return `
    <section class="panel loading">
      <div class="loading__dots"><span></span><span></span><span></span></div>
      <p class="loading__text">${escapeHtml(state.loadingText)}</p>
    </section>`;
}

function renderGenerating() {
  const gen = state.generating;
  const progress =
    gen.chapterTotal > 0
      ? `正在写第 ${gen.chapterIndex}/${gen.chapterTotal} 章`
      : "准备写故事…";
  const completed = gen.completedChapters
    .map(
      (ch) => `
      <div class="chapter-label">第 ${ch.chapter_index} 章 · ${escapeHtml(ch.title)}</div>
      <div class="story-block">${highlightAnnotatedStory(ch.annotated_story_zh)}</div>`
    )
    .join("");
  const current = getStreamingChapterView(gen);
  const currentChapter = current.visible
    ? `
      <div class="chapter-label" id="genCurrentLabel">${escapeHtml(current.label)}</div>
      <div class="story-block story-block--streaming" id="genCurrentStory">${current.storyHtml}</div>`
    : "";
  const allChaptersDone =
    gen.chapterTotal > 0 && gen.completedChapters.length >= gen.chapterTotal;
  const actionBtn =
    gen.finished || allChaptersDone
      ? `
      <div class="btn-row">
        <button type="button" class="btn btn-primary" id="enterStage1">读完了，去猜词</button>
      </div>`
      : "";
  return `
    <section class="panel generating">
      <h2 class="panel__title">${allChaptersDone || gen.finished ? "小故事写好了" : "正在为你写今天的小故事…"}</h2>
      <p class="panel__subtitle" id="genStatus">${escapeHtml(
        allChaptersDone || gen.finished
          ? "先读故事吧。例句卡片会在后台悄悄准备好。"
          : `${progress} · 单词会藏在故事里`
      )}</p>
      ${renderSessionMixHint()}
      ${renderSkippedWordsHint()}
      <div class="word-tags">${state.sessionWords.map((w) => `<span class="word-tag">${escapeHtml(w)}</span>`).join("")}</div>
      <div class="story-page">
        <div id="genCompleted">${completed}</div>
        <div id="genCurrent">${currentChapter}</div>
      </div>
      ${actionBtn}
    </section>`;
}

function renderGenerationInterrupted() {
  return `
    <section class="panel">
      <h2 class="panel__title">上次故事没写完</h2>
      <p class="panel__subtitle">同一批词可以接着写完，也可以放弃这轮重新选词。</p>
      <div class="word-tags">${state.sessionWords.map((w) => `<span class="word-tag">${escapeHtml(w)}</span>`).join("")}</div>
      <div class="btn-row">
        <button type="button" class="btn btn-primary" id="continueGenerate">继续写完</button>
        <button type="button" class="btn btn-ghost" id="abandonSession">放弃这轮</button>
      </div>
    </section>`;
}

function renderStage1() {
  const data = state.stage1;
  const chapters = data.chapters
    .map(
      (ch) => `
      <div class="chapter-label">第 ${ch.chapter_index} 章</div>
      <div class="story-block">${highlightAnnotatedStory(ch.annotated_story_zh)}</div>`
    )
    .join("");
  return `
    ${renderStepper(1)}
    <section class="panel">
      <h2 class="panel__title">${escapeHtml(data.title)}</h2>
      ${data.summary ? `<p class="panel__subtitle">${escapeHtml(data.summary)}</p>` : ""}
      ${renderSessionMixHint()}
      ${renderSkippedWordsHint()}
      <div class="word-tags">${state.sessionWords.map((w) => `<span class="word-tag">${escapeHtml(w)}</span>`).join("")}</div>
      <div class="story-page">${chapters}</div>
      <div class="btn-row">
        <button type="button" class="btn btn-primary" id="nextStage1">读完了，去猜词</button>
      </div>
    </section>`;
}

function renderStage2() {
  const data = state.stage2;
  const chapters = data.chapters
    .map(
      (ch) => `
      <div class="chapter-label">第 ${ch.chapter_index} 章</div>
      <div class="story-block">${highlightAnnotatedStory(ch.masked_story)}</div>`
    )
    .join("");
  const rows = data.words
    .map(
      (word) => `
      <div class="recall-row">
        <label class="word-label">${escapeHtml(word)}</label>
        <input data-word="${escapeHtml(word)}" placeholder="填中文释义" />
        <label class="skip-label"><input type="checkbox" data-skip="${escapeHtml(word)}" /> 这词我先放过</label>
      </div>`
    )
    .join("");
  return `
    ${renderStepper(2)}
    <section class="panel">
      <h2 class="panel__title">猜词义</h2>
      <p class="panel__subtitle">括号里的英文已藏起来了。根据语境回忆词义，也可以先放过。</p>
      <div class="story-page">${chapters}</div>
      <h3 class="panel__section-title" style="margin-top:2rem;">填写回忆</h3>
      ${rows}
      <div class="btn-row">
        <button type="button" class="btn btn-primary" id="submitStage2">进入写卡片</button>
      </div>
    </section>`;
}

function renderStage3() {
  const cards = state.stage3.cards
    .map(
      (card, index) => {
        const hint = memoryHint(card);
        return `
      <article class="word-card">
        <div class="word-card__head">
          <span class="word-card__word">${escapeHtml(card.word)}</span>
          <span class="word-card__pos">${escapeHtml(card.pos)}</span>
          ${card.is_leech ? '<span class="result-badge fail">顽固词</span>' : ""}
        </div>
        ${hint ? `<div class="word-card__memory">${escapeHtml(hint)} · 掌握 ${Math.round(card.mastery * 100)}%</div>` : ""}
        <div class="word-card__meaning">${escapeHtml(card.meaning)}</div>
        <div class="word-card__sentence-wrap">
          <div class="word-card__sentence">${card.sentence_en_highlighted}</div>
        </div>
        <div class="word-card__zh">${escapeHtml(card.sentence_zh)}</div>
        <input data-spelling="${index}" placeholder="默写英文单词" />
        <input data-meaning="${index}" placeholder="填写中文释义" />
        <textarea data-sentence="${index}" placeholder="可选：默写整句英文"></textarea>
      </article>`;
      }
    )
    .join("");
  const subtitle = isRecallMode()
      ? `${recallModeLabel()}：复用你学过的例句，完成默写后 AI 会帮你批改。`
      : "看例句、联想故事，完成默写后 AI 会帮你批改。";
  return `
    ${renderStepper(3)}
    <section class="panel">
      <h2 class="panel__title">${isRecallMode() ? `${recallModeLabel()} · 写卡片` : "写卡片"}</h2>
      ${renderSkippedWordsHint()}
      <p class="panel__subtitle">${subtitle}</p>
      <div class="card-list">${cards}</div>
      <div class="btn-row">
        <button type="button" class="btn btn-primary" id="submitStage3">提交批改</button>
      </div>
    </section>`;
}

function renderStage3Report() {
  const items = state.stage3Report
    .map((result) => {
      const ok =
        result.spelling_correct && result.meaning_correct && result.sentence_correct;
      const badge = ok
        ? '<span class="result-badge ok">通过</span>'
        : '<span class="result-badge fail">需加强</span>';
      const checks = [
        result.spelling_correct ? "拼写 ✓" : "拼写 ✗",
        result.meaning_correct ? "释义 ✓" : "释义 ✗",
        result.sentence_correct ? "造句 ✓" : "造句 ✗",
      ].join(" · ");
      const errors = result.errors.length
        ? `<ul class="report-errors">${result.errors.map((e) => `<li>${escapeHtml(e)}</li>`).join("")}</ul>`
        : "";
      const suggestions = result.suggestions.length
        ? `<div class="report-suggestions"><strong>建议：</strong>${result.suggestions.map((s) => escapeHtml(s)).join("；")}</div>`
        : "";
      return `
      <article class="report-item">
        <div class="report-item__head">
          <strong>${escapeHtml(result.word)}</strong>
          ${badge}
        </div>
        <div class="meta-line">${checks}</div>
        ${errors}
        ${suggestions}
      </article>`;
    })
    .join("");
  return `
    ${renderStepper(3)}
    <section class="panel">
      <h2 class="panel__title">批改报告</h2>
      <p class="panel__subtitle">看一下 AI 的反馈，再进入最后一关默写。</p>
      <div class="report-list">${items}</div>
      <div class="btn-row">
        <button type="button" class="btn btn-primary" id="continueStage4">进入默写</button>
      </div>
    </section>`;
}

function renderStage4() {
  const rows = state.stage4.words
    .map(
      (word) => `
      <div class="recall-row">
        <label class="word-label">${escapeHtml(word)}</label>
        <input data-s4-spelling="${escapeHtml(word)}" placeholder="默写英文" />
        <input data-s4-meaning="${escapeHtml(word)}" placeholder="中文释义" />
      </div>`
    )
    .join("");
  return `
    ${renderStepper(4)}
    <section class="panel stage4-panel">
      <h2 class="panel__title">${isRecallMode() ? `${recallModeLabel()} · 默写` : "默写"}</h2>
      <p class="panel__subtitle">最后一关：无提示，凭记忆完成。</p>
      ${rows}
      <div class="btn-row">
        <button type="button" class="btn btn-primary" id="submitStage4">完成本轮学习</button>
      </div>
    </section>`;
}

function renderDone() {
  const summaries = state.doneSummary;
  const correctCount = summaries.filter((s) => s.session_correct).length;
  const rows = summaries
    .map((s) => {
      let reviewText;
      if (s.next_review_at) {
        reviewText = `${formatReviewWhen(s.next_review_at)}再见（间隔 ${s.interval_days} 天）`;
      } else if (s.same_day_sm2_blocked) {
        reviewText = "今天已复习过，间隔不变";
      } else {
        reviewText = "尚未安排复习";
      }
      const statusBadge = s.session_correct
        ? '<span class="result-badge ok">本轮掌握</span>'
        : '<span class="result-badge fail">需再巩固</span>';
      const leech = s.is_leech ? '<span class="result-badge fail">顽固词</span>' : "";
      return `
      <article class="done-summary-item">
        <div class="done-summary-item__head">
          <strong>${escapeHtml(s.word)}</strong>
          ${statusBadge}${leech}
        </div>
        <div class="meta-line">掌握度 ${Math.round(s.mastery * 100)}% · ${escapeHtml(reviewText)}</div>
      </article>`;
    })
    .join("");
  return `
    <section class="panel">
      <h2 class="panel__title">${isRecallMode() ? `${recallModeLabel()}完成` : "本轮学习完成"}</h2>
      <p class="panel__subtitle">本轮 ${correctCount}/${summaries.length} 个词顺利过关。</p>
      <div class="done-summary-list">${rows}</div>
      <div class="btn-row">
        <button type="button" class="btn btn-primary" data-view="home">开始新一轮</button>
        <button type="button" class="btn btn-ghost" data-view="wrong">查看错题本</button>
      </div>
    </section>`;
}

function renderWrongBook() {
  if (state.wrongBook.length === 0) {
    return `
      <section class="panel">
        <h2 class="panel__title">错题本</h2>
        <p class="panel__subtitle">还没有错题，继续保持。</p>
        <div class="btn-row">
          <button type="button" class="btn btn-ghost" data-view="home">返回</button>
        </div>
      </section>`;
  }
  const items = state.wrongBook
    .slice()
    .reverse()
    .map(
      (item) => `
      <article class="wrong-item">
        <button type="button" class="wrong-item__word" data-word-profile="${escapeHtml(item.word)}">${escapeHtml(item.word)}</button>
        <small> · ${EVENT_STAGE_LABELS[item.stage] || `阶段 ${item.stage}`} · ${escapeHtml(item.created_at.slice(0, 10))}</small>
        <div class="meta-line">你的答案：${escapeHtml(item.user_answer)} · 参考：${escapeHtml(item.correct_answer)}</div>
      </article>`
    )
    .join("");
  return `
    <section class="panel">
      <h2 class="panel__title">这些词还想再见面</h2>
      <p class="panel__subtitle">它们会在之后的复习里再次出现。</p>
      <div class="wrong-list">${items}</div>
      <div class="btn-row">
        <button type="button" class="btn btn-ghost" data-view="home">返回</button>
      </div>
    </section>`;
}

function formatEventLine(event) {
  const stageLabel = EVENT_STAGE_LABELS[event.stage] || `阶段 ${event.stage}`;
  if (event.event_type === "stage1_complete") {
    return "完成读故事";
  }
  const resultLabel =
    event.result === "correct" ? "对" : event.result === "partial" ? "部分对" : "错";
  return `${stageLabel} · ${resultLabel}`;
}

function renderWordProfile() {
  const profile = state.wordProfile;
  if (!profile) {
    return "";
  }
  const { word, memory, events } = profile;
  let reviewHint = "尚未安排复习";
  if (memory.next_review_at) {
    reviewHint = `${formatReviewWhen(memory.next_review_at)}再见（间隔 ${memory.interval_days} 天）`;
  } else if (memory.incomplete_due_at) {
    reviewHint = `巩固提醒：${formatReviewWhen(memory.incomplete_due_at)}`;
  }
  const leech = memory.is_leech ? '<span class="result-badge fail">顽固词</span>' : "";
  const timeline = events
    .slice()
    .reverse()
    .map(
      (event) => `
      <article class="timeline-item">
        <div class="timeline-item__when">${escapeHtml(event.occurred_at.slice(0, 16).replace("T", " "))}</div>
        <div class="timeline-item__what">${escapeHtml(formatEventLine(event))}</div>
      </article>`
    )
    .join("");
  return `
    <section class="panel">
      <h2 class="panel__title">${escapeHtml(word)}</h2>
      <p class="panel__subtitle word-profile__summary">
        掌握度 ${Math.round(memory.mastery * 100)}% · 复习 ${memory.review_count} 次
        · 对 ${memory.correct_count} / 错 ${memory.wrong_count}
        ${leech}
      </p>
      <p class="meta-line">${escapeHtml(reviewHint)}</p>
      <h3 class="panel__section-title">学习轨迹</h3>
      <div class="timeline-list">${timeline}</div>
      <div class="btn-row">
        <button type="button" class="btn btn-ghost" data-view="wrong">返回错题本</button>
        <button type="button" class="btn btn-ghost" data-view="home">回首页</button>
      </div>
    </section>`;
}

function updateGeneratingDom(options = {}) {
  const { streamOnly = false } = options;
  const status = document.getElementById("genStatus");
  const completed = document.getElementById("genCompleted");
  const currentWrap = document.getElementById("genCurrent");
  if (!status || !currentWrap || !state.generating) {
    return;
  }
  const gen = state.generating;
  const allDone = gen.chapterTotal > 0 && gen.completedChapters.length >= gen.chapterTotal;
  let statusLine = "正在为你写今天的小故事…";
  if (gen.chapterTotal > 0) {
    statusLine = gen.thinkingActive
      ? `正在写第 ${gen.chapterIndex}/${gen.chapterTotal} 章 · 模型深度思考中，请稍候…`
      : `正在写第 ${gen.chapterIndex}/${gen.chapterTotal} 章 · 单词会藏在故事里`;
  }
  status.textContent = allDone || gen.finished
    ? "先读故事吧。例句卡片会在后台悄悄准备好。"
    : statusLine;

  const current = getStreamingChapterView(gen);
  currentWrap.innerHTML = current.visible
    ? `
      <div class="chapter-label" id="genCurrentLabel">${escapeHtml(current.label)}</div>
      <div class="story-block story-block--streaming" id="genCurrentStory">${current.storyHtml}</div>`
    : "";

  const storyEl = document.getElementById("genCurrentStory");
  if (storyEl) {
    storyEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  if (streamOnly || !completed) {
    return;
  }
  if (document.querySelector(".generating") && state.generating?.finished) {
    bindGeneratingIfReady();
  }
  completed.innerHTML = gen.completedChapters
    .map(
      (ch) => `
      <div class="chapter-label">第 ${ch.chapter_index} 章 · ${escapeHtml(ch.title)}</div>
      <div class="story-block">${highlightAnnotatedStory(ch.annotated_story_zh)}</div>`
    )
    .join("");
}

function handleStreamEvent(event) {
  if (!state.generating) {
    return;
  }
  const gen = state.generating;
  switch (event.type) {
    case "start":
      gen.chapterTotal = event.chapter_total;
      updateGeneratingDom();
      break;
    case "chapter_start":
      gen.chapterIndex = event.chapter_index;
      gen.streamText = "";
      gen.thinkingActive = false;
      updateGeneratingDom();
      break;
    case "thinking":
      gen.thinkingActive = true;
      updateGeneratingDom({ streamOnly: true });
      break;
    case "delta":
      gen.thinkingActive = false;
      gen.streamText += event.text;
      updateGeneratingDom({ streamOnly: true });
      break;
    case "chapter_done":
      gen.completedChapters.push({
        chapter_index: event.chapter_index,
        title: event.title,
        annotated_story_zh: event.annotated_story_zh,
      });
      gen.streamText = "";
      if (gen.completedChapters.length >= gen.chapterTotal && gen.chapterTotal > 0) {
        gen.finished = true;
      }
      updateGeneratingDom();
      bindGeneratingIfReady();
      break;
    case "done":
      gen.finished = true;
      updateGeneratingDom();
      bindGeneratingIfReady();
      break;
    default:
      break;
  }
}

function render() {
  if (state.loading) {
    app.innerHTML = renderLoading();
    return;
  }
  switch (state.view) {
    case "generating":
      app.innerHTML = renderGenerating();
      bindGeneratingIfReady();
      break;
    case "generating-interrupted":
      app.innerHTML = renderGenerationInterrupted();
      bindGenerationInterrupted();
      break;
    case "word-profile":
      app.innerHTML = renderWordProfile();
      bindNav();
      break;
    case "home":
      app.innerHTML = renderHome();
      bindHome();
      break;
    case "stage1":
      app.innerHTML = renderStage1();
      bindStage1();
      break;
    case "stage2":
      app.innerHTML = renderStage2();
      bindStage2();
      break;
    case "stage3":
      app.innerHTML = renderStage3();
      bindStage3();
      break;
    case "stage3-report":
      app.innerHTML = renderStage3Report();
      bindStage3Report();
      break;
    case "stage4":
      app.innerHTML = renderStage4();
      bindStage4();
      break;
    case "done":
      app.innerHTML = renderDone();
      bindNav();
      break;
    case "wrong":
      app.innerHTML = renderWrongBook();
      bindWrongBook();
      break;
    default:
      app.innerHTML = renderHome();
      bindHome();
  }
  updateNav();
}

function updateNav() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    const isHome =
      state.view === "home" ||
      state.view === "generating" ||
      state.view === "generating-interrupted" ||
      state.view.startsWith("stage") ||
      state.view === "done";
    const activeView =
      btn.dataset.view === "home"
        ? isHome && state.view !== "wrong"
        : btn.dataset.view === state.view;
    btn.classList.toggle("active", activeView);
  });
}

function bindNav() {
  document.querySelectorAll("[data-view]").forEach((el) => {
    el.addEventListener("click", async () => {
      const view = el.dataset.view;
      if (view === "wrong") {
        state.wrongBook = await api.getWrongBook();
      }
      if (view === "home") {
        await refreshHomeStats();
        state.resumableSession = await api.getResumable();
      }
      state.view = view;
      render();
    });
  });
}

async function refreshDueReview() {
  const level = state.homePath === "review"
    ? document.getElementById("reviewLevel")?.value || "basic"
    : "basic";
  state.dueReview = await api.getReviewDue(level, 50);
}

async function refreshWeakCount() {
  const level = state.homePath === "weak"
    ? document.getElementById("weakLevel")?.value || "basic"
    : "basic";
  state.weakReview = await api.getWeakCount(level);
}

async function refreshHomeStats() {
  await Promise.all([refreshDueReview(), refreshWeakCount()]);
}

function bindHome() {
  document.querySelectorAll(".entry-card").forEach((card) => {
    card.addEventListener("click", async () => {
      state.homePath = card.dataset.path;
      if (state.homePath === "review") {
        await refreshDueReview();
      }
      if (state.homePath === "weak") {
        await refreshWeakCount();
      }
      render();
    });
  });

  document.querySelectorAll(".mode-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.mode = tab.dataset.mode;
      render();
    });
  });

  const thinkingToggle = document.getElementById("enableThinking");
  const thinkingHint = document.getElementById("thinkingHint");
  if (thinkingToggle) {
    thinkingToggle.addEventListener("change", () => {
      saveThinkingPref(thinkingToggle.checked);
      if (thinkingHint) {
        thinkingHint.hidden = !thinkingToggle.checked;
      }
    });
  }

  const startBtn = document.getElementById("startBtn");
  if (startBtn) {
    startBtn.addEventListener("click", startLearning);
  }

  const reviewBtn = document.getElementById("startReviewBtn");
  if (reviewBtn) {
    reviewBtn.addEventListener("click", startReview);
  }

  const weakBtn = document.getElementById("startWeakBtn");
  if (weakBtn) {
    weakBtn.addEventListener("click", startWeak);
  }

  const resumeBtn = document.getElementById("resumeBtn");
  if (resumeBtn) {
    resumeBtn.addEventListener("click", resumeSession);
  }

  const reviewLevel = document.getElementById("reviewLevel");
  if (reviewLevel) {
    reviewLevel.addEventListener("change", async () => {
      state.dueReview = await api.getReviewDue(reviewLevel.value, 50);
      render();
    });
  }

  const weakLevel = document.getElementById("weakLevel");
  if (weakLevel) {
    weakLevel.addEventListener("change", async () => {
      await refreshWeakCount();
      render();
    });
  }

  bindNav();
}

function bindWrongBook() {
  document.querySelectorAll("[data-word-profile]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        state.loading = true;
        state.loadingText = "加载单词档案…";
        render();
        const word = btn.dataset.wordProfile;
        const [memory, events] = await Promise.all([
          api.getWordMemory(word),
          api.getWordEvents(word),
        ]);
        state.wordProfile = { word, memory, events };
        state.loading = false;
        state.view = "word-profile";
        render();
      } catch (error) {
        state.loading = false;
        showToast(error.message);
        render();
      }
    });
  });
  bindNav();
}

function bindGenerationInterrupted() {
  document.getElementById("continueGenerate").addEventListener("click", continueInterruptedGeneration);
  document.getElementById("abandonSession").addEventListener("click", abandonInterruptedSession);
}

async function continueInterruptedGeneration() {
  try {
    state.loading = true;
    state.loadingText = "准备继续写故事…";
    render();
    await api.resetStory(state.sessionId);
    state.loading = false;
    state.view = "generating";
    state.generating = {
      chapterTotal: 0,
      chapterIndex: 0,
      streamText: "",
      completedChapters: [],
      finished: false,
      thinkingActive: false,
    };
    render();
    await api.generateStoryStream(state.sessionId, handleStreamEvent);
    if (state.generating) {
      state.generating.finished = true;
    }
    state.resumableSession = null;
    render();
  } catch (error) {
    state.loading = false;
    showToast(error.message);
    render();
  }
}

async function abandonInterruptedSession() {
  try {
    await api.abandonSession(state.sessionId);
    state.sessionId = null;
    state.resumableSession = null;
    clearPersistedSession();
    state.view = "home";
    await refreshHomeStats();
    render();
  } catch (error) {
    showToast(error.message);
  }
}

async function startLearning() {
  const style = document.getElementById("style").value.trim();
  const enableThinking = document.getElementById("enableThinking")?.checked ?? false;
  const payload =
    state.mode === "frequency"
      ? {
          mode: "frequency",
          level: document.getElementById("level").value,
          count: Number(document.getElementById("count").value),
          style,
          enable_thinking: enableThinking,
        }
      : {
          mode: "manual",
          words: document
            .getElementById("words")
            .value.trim()
            .split(/[\s,，;；]+/)
            .filter(Boolean),
          style,
          enable_thinking: enableThinking,
        };

  try {
    state.loading = true;
    state.loadingText = "正在选词，准备写故事…";
    render();

    const result = await api.createSession(payload);
    applyCreatedSession(result);
    state.skippedWords = [];

    state.loading = false;
    state.view = "generating";
    state.generating = {
      chapterTotal: 0,
      chapterIndex: 0,
      streamText: "",
      completedChapters: [],
      finished: false,
      thinkingActive: false,
    };
    render();

    await api.generateStoryStream(state.sessionId, handleStreamEvent);

    if (state.generating) {
      state.generating.finished = true;
    }
    render();
  } catch (error) {
    state.loading = false;
    state.generating = null;
    showToast(error.message);
    render();
  }
}

async function startWeak() {
  const level = document.getElementById("weakLevel").value;
  const count = Number(document.getElementById("weakCount").value);

  try {
    state.loading = true;
    state.loadingText = "正在挑选薄弱词…";
    render();

    const result = await api.createSession({
      mode: "weak",
      level,
      count,
      style: "薄弱巩固",
    });
    applyCreatedSession(result);
    if (result.skipped_words.length) {
      showToast(`${result.skipped_words.length} 个词因缺少例句已跳过`);
    }

    state.stage3 = await api.getStage3(state.sessionId);
    state.loading = false;
    state.view = "stage3";
    state.stage = 3;
    render();
    await refreshHomeStats();
  } catch (error) {
    state.loading = false;
    showToast(error.message);
    render();
  }
}

async function startReview() {
  const level = document.getElementById("reviewLevel").value;
  const count = Number(document.getElementById("reviewCount").value);

  try {
    state.loading = true;
    state.loadingText = "正在准备复习词…";
    render();

    const result = await api.createSession({
      mode: "review",
      level,
      count,
      style: "复习",
    });
    applyCreatedSession(result);
    if (result.skipped_words.length) {
      showToast(`${result.skipped_words.length} 个词因缺少例句已跳过`);
    }

    state.stage3 = await api.getStage3(state.sessionId);
    state.loading = false;
    state.view = "stage3";
    state.stage = 3;
    render();
    await refreshHomeStats();
  } catch (error) {
    state.loading = false;
    showToast(error.message);
    render();
  }
}

function bindGeneratingIfReady() {
  const btn = document.getElementById("enterStage1");
  if (!btn || btn.dataset.bound === "1") {
    return;
  }
  btn.dataset.bound = "1";
  btn.addEventListener("click", enterStage1FromGenerating);
}

async function resumeSession() {
  const r = state.resumableSession;
  if (!r) {
    return;
  }
  try {
    state.loading = true;
    state.loadingText = "正在恢复上次进度…";
    render();

    state.sessionId = r.id;
    state.sessionMode = r.mode;
    state.sessionWords = r.words.map((w) => w.word);
    state.sessionMix = buildSessionMix(r.words);
    state.skippedWords = [];
    if (r.mode === "review") {
      state.homePath = "review";
    } else if (r.mode === "weak") {
      state.homePath = "weak";
    } else {
      state.homePath = "learn";
    }

    if (r.resume_kind === "generating_interrupted") {
      state.loading = false;
      state.view = "generating-interrupted";
      persistSession();
      render();
      return;
    }

    if (r.resume_kind === "generating") {
      state.loading = false;
      state.view = "generating";
      state.generating = {
        chapterTotal: 0,
        chapterIndex: 0,
        streamText: "",
        completedChapters: [],
        finished: false,
        thinkingActive: false,
      };
      persistSession();
      render();
      await api.generateStoryStream(state.sessionId, handleStreamEvent);
      if (state.generating) {
        state.generating.finished = true;
      }
      state.resumableSession = null;
      render();
      return;
    }

    if (r.status === "stage1") {
      state.stage1 = await api.getStage1(state.sessionId);
      state.view = "stage1";
      state.stage = 1;
    } else if (r.status === "stage2") {
      state.stage2 = await api.getStage2(state.sessionId);
      state.view = "stage2";
      state.stage = 2;
    } else if (r.status === "stage3") {
      state.stage3 = await api.getStage3(state.sessionId);
      state.view = "stage3";
      state.stage = 3;
    } else if (r.status === "stage4") {
      state.stage4 = await api.getStage4(state.sessionId);
      state.view = "stage4";
      state.stage = 4;
    } else {
      throw new Error(`无法续学：${r.status}`);
    }

    state.loading = false;
    persistSession();
    render();
  } catch (error) {
    state.loading = false;
    showToast(error.message);
    render();
  }
}

async function enterStage1FromGenerating() {
  try {
    state.stage1 = await api.getStage1(state.sessionId);
    state.generating = null;
    state.view = "stage1";
    state.stage = 1;
    persistSession();
    render();
  } catch (error) {
    showToast(error.message);
  }
}

function bindStage1() {
  document.getElementById("nextStage1").addEventListener("click", async () => {
    try {
      await api.completeStage1(state.sessionId);
      state.stage2 = await api.getStage2(state.sessionId);
      state.view = "stage2";
      state.stage = 2;
      persistSession();
      render();
    } catch (error) {
      showToast(error.message);
    }
  });
}

function bindStage2() {
  document.getElementById("submitStage2").addEventListener("click", async () => {
    try {
      const answers = state.stage2.words.map((word) => {
        const input = document.querySelector(`input[data-word="${word}"]`);
        const skip = document.querySelector(`input[data-skip="${word}"]`);
        return {
          word,
          meaning_answer: input.value.trim(),
          skipped: skip.checked,
        };
      });
      state.loading = true;
      state.loadingText = "AI 正在看你的释义…";
      render();
      await api.submitStage2(state.sessionId, answers);
      state.stage3 = await api.getStage3(state.sessionId);
      state.loading = false;
      state.view = "stage3";
      state.stage = 3;
      persistSession();
      render();
    } catch (error) {
      state.loading = false;
      showToast(error.message);
      render();
    }
  });
}

function bindStage3Report() {
  document.getElementById("continueStage4").addEventListener("click", async () => {
    try {
      state.stage4 = await api.getStage4(state.sessionId);
      state.stage3Report = null;
      state.view = "stage4";
      state.stage = 4;
      persistSession();
      render();
    } catch (error) {
      showToast(error.message);
    }
  });
}

function bindStage3() {
  document.getElementById("submitStage3").addEventListener("click", async () => {
    try {
      const answers = state.stage3.cards.map((card, index) => ({
        word: card.word,
        spelling_answer: document.querySelector(`input[data-spelling="${index}"]`).value.trim(),
        meaning_answer: document.querySelector(`input[data-meaning="${index}"]`).value.trim(),
        sentence_answer: document.querySelector(`textarea[data-sentence="${index}"]`).value.trim(),
      }));
      state.loading = true;
      state.loadingText = "AI 正在批改，约需 10～30 秒…";
      render();
      const response = await api.submitStage3(state.sessionId, answers);
      state.stage3Report = response.results;
      state.loading = false;
      state.view = "stage3-report";
      persistSession();
      render();
    } catch (error) {
      state.loading = false;
      showToast(error.message);
      render();
    }
  });
}

function bindStage4() {
  document.getElementById("submitStage4").addEventListener("click", async () => {
    try {
      const answers = state.stage4.words.map((word) => ({
        word,
        spelling_answer: document.querySelector(`input[data-s4-spelling="${word}"]`).value.trim(),
        meaning_answer: document.querySelector(`input[data-s4-meaning="${word}"]`).value.trim(),
      }));
      state.loading = true;
      state.loadingText = "提交最后一关…";
      render();
      const response = await api.submitStage4(state.sessionId, answers);
      state.doneSummary = response.word_summaries;
      state.loading = false;
      state.view = "done";
      state.resumableSession = null;
      clearPersistedSession();
      render();
      await refreshHomeStats();
    } catch (error) {
      state.loading = false;
      showToast(error.message);
      render();
    }
  });
}

document.querySelectorAll(".header__nav .nav-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    if (btn.dataset.view === "wrong") {
      state.wrongBook = await api.getWrongBook();
    }
    if (btn.dataset.view === "home") {
      await refreshHomeStats();
      state.resumableSession = await api.getResumable();
    }
    state.view = btn.dataset.view;
    render();
  });
});

async function init() {
  render();
  const results = await Promise.allSettled([
    api.vocabularyCount(),
    api.getReviewDue("basic", 50),
    api.getWeakCount("basic"),
    api.getResumable(),
  ]);
  if (results[0].status === "fulfilled") {
    state.vocabCount = results[0].value.count;
  }
  if (results[1].status === "fulfilled") {
    state.dueReview = results[1].value;
  }
  if (results[2].status === "fulfilled") {
    state.weakReview = results[2].value;
  }
  if (results[3].status === "fulfilled") {
    state.resumableSession = results[3].value;
  }
  const failed = results.filter((r) => r.status === "rejected");
  if (failed.length === results.length) {
    showToast("无法连接后端，请先启动 API 服务");
  }
  render();
}

init();
