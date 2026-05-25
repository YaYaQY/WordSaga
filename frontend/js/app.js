import { api } from "./api.js";

const state = {
  view: "home",
  mode: "frequency",
  sessionId: null,
  stage: 1,
  vocabCount: 0,
  sessionWords: [],
  stage1: null,
  stage2: null,
  stage3: null,
  stage4: null,
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
    return { visible: true, label, storyHtml: "" };
  }

  return {
    visible: true,
    label,
    storyHtml: `${highlightAnnotatedStory(storyText)}<span class="stream-cursor" aria-hidden="true"></span>`,
  };
}

function renderStepper(current) {
  const steps = [
    { n: 1, label: "语境初识" },
    { n: 2, label: "猜词回忆" },
    { n: 3, label: "卡片深学" },
    { n: 4, label: "终极复盘" },
  ];
  return `<div class="stepper">${steps
    .map((s) => {
      const cls =
        s.n === current ? "active" : s.n < current ? "done" : "";
      return `<div class="step ${cls}"><span>${s.n}</span>${s.label}</div>`;
    })
    .join("")}</div>`;
}

function renderHome() {
  return `
    <section class="panel">
      <h1 class="panel__title">开启一轮剧情记忆</h1>
      <p class="panel__subtitle">
        选择词频计划或手动指定单词，AI 将生成连贯剧情，带你完成四阶段主动回忆。
      </p>
      <div class="form-grid">
        <div class="mode-tabs">
          <button type="button" class="mode-tab ${state.mode === "frequency" ? "selected" : ""}" data-mode="frequency">
            <strong>词频计划</strong>
            按词频自动选词，混合复习
          </button>
          <button type="button" class="mode-tab ${state.mode === "manual" ? "selected" : ""}" data-mode="manual">
            <strong>手动指定</strong>
            输入你想学的单词
          </button>
        </div>

        <div class="field">
          <label>故事风格</label>
          <input id="style" value="喜欢的故事风格和故事主题" />
        </div>

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
            <label>本轮词数（每 20 词 1 章）</label>
            <input id="count" type="number" min="1" max="300" value="5" />
          </div>`
            : `
          <div class="field">
            <label>单词列表（空格或逗号分隔）</label>
            <textarea id="words" placeholder="investigate, murder, secret"></textarea>
          </div>`
        }

        <div class="btn-row">
          <button type="button" class="btn btn-primary" id="startBtn">生成剧情并开始</button>
        </div>
      </div>
    </section>`;
}

function renderLoading() {
  return `
    <section class="panel loading">
      <div class="loading__spinner"></div>
      <p class="loading__text">${escapeHtml(state.loadingText)}</p>
    </section>`;
}

function renderGenerating() {
  const gen = state.generating;
  const progress =
    gen.chapterTotal > 0
      ? `正在生成第 ${gen.chapterIndex}/${gen.chapterTotal} 章`
      : "准备生成剧情…";
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
  const actionBtn = gen.finished || allChaptersDone
    ? `
      <div class="btn-row">
        <button type="button" class="btn btn-primary" id="enterStage1">读完了，进入猜词</button>
      </div>`
    : "";
  return `
    <section class="panel generating">
      <h2 class="panel__title">${allChaptersDone || gen.finished ? "剧情生成完成" : "AI 正在撰写剧情"}</h2>
      <p class="panel__subtitle" id="genStatus">${escapeHtml(
        allChaptersDone || gen.finished
          ? "正文已就绪，单词卡片在后台补全。点击下方进入第一阶段学习。"
          : `${progress} · 先展示正文，单词卡片等会在后台补全`
      )}</p>
      <div class="word-tags">${state.sessionWords.map((w) => `<span class="word-tag">${escapeHtml(w)}</span>`).join("")}</div>
      <div id="genCompleted">${completed}</div>
      <div id="genCurrent">${currentChapter}</div>
      ${actionBtn}
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
      <p class="panel__subtitle">${escapeHtml(data.summary)}</p>
      <div class="word-tags">${state.sessionWords.map((w) => `<span class="word-tag">${escapeHtml(w)}</span>`).join("")}</div>
      ${chapters}
      <div class="btn-row">
        <button type="button" class="btn btn-primary" id="nextStage1">读完了，进入猜词</button>
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
        <label>${escapeHtml(word)}</label>
        <input data-word="${escapeHtml(word)}" placeholder="填写中文释义，或留空跳过" />
        <label><input type="checkbox" data-skip="${escapeHtml(word)}" /> 跳过</label>
      </div>`
    )
    .join("");
  return `
    ${renderStepper(2)}
    <section class="panel">
      <h2 class="panel__title">隐藏注释 · 语境猜词</h2>
      <p class="panel__subtitle">括号内的英文已隐藏。根据中文语境回忆单词，也可以跳过。</p>
      ${chapters}
      <h3 class="panel__title" style="font-size:1.2rem;margin-top:2rem;">填写回忆</h3>
      ${rows}
      <div class="btn-row">
        <button type="button" class="btn btn-primary" id="submitStage2">进入卡片深学</button>
      </div>
    </section>`;
}

function renderStage3() {
  const cards = state.stage3.cards
    .map(
      (card, index) => `
      <article class="word-card">
        <div class="word-card__head">
          <span class="word-card__word">${escapeHtml(card.word)}</span>
          <span class="word-card__pos">${escapeHtml(card.pos)}</span>
        </div>
        <div class="word-card__meaning">${escapeHtml(card.meaning)}</div>
        <div class="word-card__sentence">${card.sentence_en_highlighted}</div>
        <div class="word-card__zh">${escapeHtml(card.sentence_zh)}</div>
        <input data-spelling="${index}" placeholder="默写英文单词" />
        <input data-meaning="${index}" placeholder="填写中文释义" />
        <textarea data-sentence="${index}" placeholder="可选：默写整句英文"></textarea>
      </article>`
    )
    .join("");
  return `
    ${renderStepper(3)}
    <section class="panel">
      <h2 class="panel__title">单词卡片 · 深度学习</h2>
      <p class="panel__subtitle">看场景、联想剧情，完成默写后 AI 将自动批改。</p>
      <div class="card-list">${cards}</div>
      <div class="btn-row">
        <button type="button" class="btn btn-primary" id="submitStage3">提交批改</button>
      </div>
    </section>`;
}

function renderStage4() {
  const rows = state.stage4.words
    .map(
      (word) => `
      <div class="recall-row">
        <label>${escapeHtml(word)}</label>
        <input data-s4-spelling="${escapeHtml(word)}" placeholder="默写英文" />
        <input data-s4-meaning="${escapeHtml(word)}" placeholder="中文释义" />
      </div>`
    )
    .join("");
  return `
    ${renderStepper(4)}
    <section class="panel">
      <h2 class="panel__title">终极复盘</h2>
      <p class="panel__subtitle">无剧情、无提示。仅凭记忆完成最后一轮自测。</p>
      ${rows}
      <div class="btn-row">
        <button type="button" class="btn btn-primary" id="submitStage4">完成本轮学习</button>
      </div>
    </section>`;
}

function renderDone() {
  return `
    <section class="panel">
      <h2 class="panel__title">本轮学习完成</h2>
      <p class="panel__subtitle">学习记录已保存到本地。错题会自动加入后续复习权重。</p>
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
        <p class="panel__subtitle">暂无错题记录。</p>
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
        <strong>${escapeHtml(item.word)}</strong>
        <small> · Stage ${item.stage} · ${escapeHtml(item.created_at.slice(0, 10))}</small>
        <div class="meta-line">你的答案：${escapeHtml(item.user_answer)} · 正确答案：${escapeHtml(item.correct_answer)}</div>
      </article>`
    )
    .join("");
  return `
    <section class="panel">
      <h2 class="panel__title">错题本</h2>
      <p class="panel__subtitle">这些词会在后续词频计划中提高复现权重。</p>
      <div class="wrong-list">${items}</div>
      <div class="btn-row">
        <button type="button" class="btn btn-ghost" data-view="home">返回</button>
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
  status.textContent =
    gen.chapterTotal > 0
      ? `正在生成第 ${gen.chapterIndex}/${gen.chapterTotal} 章 · 先展示正文，单词卡片等会在后台补全`
      : "准备生成剧情…";

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
  const genRoot = document.querySelector(".generating");
  if (genRoot && state.generating?.finished) {
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
      updateGeneratingDom();
      break;
    case "delta":
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
      bindNav();
      break;
    default:
      app.innerHTML = renderHome();
      bindHome();
  }
  updateNav();
}

function updateNav() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === state.view);
  });
}

function bindNav() {
  document.querySelectorAll("[data-view]").forEach((el) => {
    el.addEventListener("click", async () => {
      const view = el.dataset.view;
      if (view === "wrong") {
        state.wrongBook = await api.getWrongBook();
      }
      state.view = view;
      render();
    });
  });
}

function bindHome() {
  document.querySelectorAll(".mode-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.mode = tab.dataset.mode;
      render();
    });
  });
  document.getElementById("startBtn").addEventListener("click", startLearning);
  bindNav();
}

async function startLearning() {
  const style = document.getElementById("style").value.trim();
  const payload =
    state.mode === "frequency"
      ? {
          mode: "frequency",
          level: document.getElementById("level").value,
          count: Number(document.getElementById("count").value),
          style,
        }
      : {
          mode: "manual",
          words: document
            .getElementById("words")
            .value.trim()
            .split(/[\s,，;；]+/)
            .filter(Boolean),
          style,
        };

  try {
    state.loading = true;
    state.loadingText = "正在选词并创建学习会话…";
    render();

    const session = await api.createSession(payload);

    state.sessionId = session.id;
    state.sessionWords = session.words.map((w) => w.word);

    state.loading = false;
    state.view = "generating";
    state.generating = {
      chapterTotal: 0,
      chapterIndex: 0,
      streamText: "",
      completedChapters: [],
      finished: false,
    };
    render();

    await api.generateStoryStream(session.id, handleStreamEvent);

    state.stage1 = await api.getStage1(session.id);
    state.generating = null;
    state.view = "stage1";
    state.stage = 1;
    render();
  } catch (error) {
    state.loading = false;
    state.generating = null;
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

async function enterStage1FromGenerating() {
  try {
    state.stage1 = await api.getStage1(state.sessionId);
    state.generating = null;
    state.view = "stage1";
    state.stage = 1;
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
      state.loadingText = "保存回忆记录…";
      render();
      await api.submitStage2(state.sessionId, answers);
      state.stage3 = await api.getStage3(state.sessionId);
      state.loading = false;
      state.view = "stage3";
      state.stage = 3;
      render();
    } catch (error) {
      state.loading = false;
      showToast(error.message);
      render();
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
      await api.submitStage3(state.sessionId, answers);
      state.stage4 = await api.getStage4(state.sessionId);
      state.loading = false;
      state.view = "stage4";
      state.stage = 4;
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
      state.loadingText = "提交终极复盘…";
      render();
      await api.submitStage4(state.sessionId, answers);
      state.loading = false;
      state.view = "done";
      render();
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
    state.view = btn.dataset.view;
    render();
  });
});

async function init() {
  render();
  try {
    const data = await api.vocabularyCount();
    state.vocabCount = data.count;
  } catch (error) {
    showToast(error.message || "无法连接后端，请先启动 API 服务");
  }
  render();
}

init();
