const API_BASE = "";
const DEFAULT_TIMEOUT_MS = 30000;

function formatApiDetail(detail) {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || JSON.stringify(item)).join("；");
  }
  return null;
}

async function readJsonResponse(response) {
  const text = await response.text();
  if (!text) {
    return null;
  }
  return JSON.parse(text);
}

function buildHttpError(response, data) {
  const detail = data ? formatApiDetail(data.detail) : null;
  if (response.status === 401 || response.status === 403) {
    return new Error(detail || "API 密钥无效或未授权，请检查 .env 中的 OPENAI_API_KEY");
  }
  if (response.status === 429) {
    return new Error(detail || "请求过于频繁或被限流，请稍后再试");
  }
  if (response.status >= 500) {
    return new Error(detail || `服务器错误（${response.status}），请查看后端终端日志`);
  }
  if (response.status === 400) {
    return new Error(detail || `请求无效（${response.status}）`);
  }
  if (response.status === 404) {
    return new Error(detail || "资源不存在");
  }
  return new Error(detail || `请求失败：${response.status}`);
}

function buildNetworkError(error) {
  if (error.name === "AbortError") {
    return new Error("请求超时，请确认后端已在 backend 目录启动");
  }
  if (error instanceof TypeError) {
    return new Error("无法连接后端，请确认已在 backend 目录启动服务（http://127.0.0.1:8000）");
  }
  return error;
}

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
    const data = await readJsonResponse(response);
    if (!response.ok) {
      throw buildHttpError(response, data);
    }
    return data;
  } catch (error) {
    throw buildNetworkError(error);
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
  resetStory: (sessionId) =>
    request(`/api/sessions/${sessionId}/reset-story`, { method: "POST" }),
  abandonSession: async (sessionId) => {
    const response = await fetch(`${API_BASE}/api/sessions/${sessionId}`, { method: "DELETE" });
    const data = await readJsonResponse(response);
    if (!response.ok) {
      throw buildHttpError(response, data);
    }
    return data;
  },
  getWeakCount: (level = "basic") =>
    request(`/api/vocabulary/weak/count?level=${encodeURIComponent(level)}`),
  getWordMemory: (word) => request(`/api/words/${encodeURIComponent(word)}/memory`),
  getWordEvents: (word) => request(`/api/words/${encodeURIComponent(word)}/events`),
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
      throw buildNetworkError(error);
    }

    if (!response.ok) {
      clearTimeout(timer);
      const data = await readJsonResponse(response);
      throw buildHttpError(response, data);
    }

    if (!response.body) {
      clearTimeout(timer);
      throw new Error("服务器未返回流式数据");
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
    } catch (error) {
      if (error.name === "AbortError") {
        throw new Error("剧情生成超时，请稍后重试");
      }
      throw error;
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
  getReviewDue: (level = "basic", limit = 50) =>
    request(`/api/vocabulary/review/due?level=${encodeURIComponent(level)}&limit=${limit}`),
  getResumable: async () => {
    let response;
    try {
      response = await fetch(`${API_BASE}/api/sessions/resumable`);
    } catch (error) {
      throw buildNetworkError(error);
    }
    if (response.status === 404) {
      return null;
    }
    const data = await readJsonResponse(response);
    if (!response.ok) {
      throw buildHttpError(response, data);
    }
    return data;
  },
};
