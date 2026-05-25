const API_BASE = "";
const DEFAULT_TIMEOUT_MS = 30000;

async function request(path, options = {}) {
  const { timeout = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...(fetchOptions.headers || {}) },
      signal: controller.signal,
      ...fetchOptions,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || `请求失败：${response.status}`);
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("请求超时，请确认后端已在 backend 目录启动");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function parseSseBuffer(buffer, onEvent) {
  const lines = buffer.split("\n");
  const rest = lines.pop() ?? "";
  for (const line of lines) {
    if (!line.startsWith("data: ")) {
      continue;
    }
    const event = JSON.parse(line.slice(6));
    onEvent(event);
    if (event.type === "error") {
      throw new Error(event.message);
    }
  }
  return rest;
}

export const api = {
  vocabularyCount: () => request("/api/vocabulary/count"),
  selectFrequency: (body) =>
    request("/api/vocabulary/select/frequency", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createSession: (body) =>
    request("/api/sessions", { method: "POST", body: JSON.stringify(body) }),
  generateStory: (sessionId) =>
    request(`/api/sessions/${sessionId}/generate`, { method: "POST", timeout: 600000 }),
  generateStoryStream: async (sessionId, onEvent) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 600000);
    let response;
    try {
      response = await fetch(`${API_BASE}/api/sessions/${sessionId}/generate/stream`, {
        method: "POST",
        signal: controller.signal,
      });
    } catch (error) {
      clearTimeout(timer);
      if (error.name === "AbortError") {
        throw new Error("剧情生成超时，请稍后重试");
      }
      throw error;
    }

    if (!response.ok) {
      clearTimeout(timer);
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || `请求失败：${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        buffer = parseSseBuffer(buffer, onEvent);
      }
      if (buffer.trim()) {
        parseSseBuffer(`${buffer}\n`, onEvent);
      }
    } finally {
      clearTimeout(timer);
    }
  },
  getStory: (sessionId) => request(`/api/sessions/${sessionId}/story`),
  getStage1: (sessionId) => request(`/api/sessions/${sessionId}/stage/1`),
  completeStage1: (sessionId) =>
    request(`/api/sessions/${sessionId}/stage/1/complete`, { method: "POST" }),
  getStage2: (sessionId) => request(`/api/sessions/${sessionId}/stage/2`),
  submitStage2: (sessionId, answers) =>
    request(`/api/sessions/${sessionId}/stage/2/submit`, {
      method: "POST",
      body: JSON.stringify({ answers }),
    }),
  getStage3: (sessionId) => request(`/api/sessions/${sessionId}/stage/3`),
  submitStage3: (sessionId, answers) =>
    request(`/api/sessions/${sessionId}/stage/3/submit`, {
      method: "POST",
      body: JSON.stringify({ answers }),
      timeout: 180000,
    }),
  getStage4: (sessionId) => request(`/api/sessions/${sessionId}/stage/4`),
  submitStage4: (sessionId, answers) =>
    request(`/api/sessions/${sessionId}/stage/4/submit`, {
      method: "POST",
      body: JSON.stringify({ answers }),
      timeout: 180000,
    }),
  getWrongBook: () => request("/api/wrong-book"),
};
