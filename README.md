# WordSaga · 词境

把单词放进 AI 写的小故事里，用「读 → 猜 → 写 → 默写」四步完成记忆；复习时复用历史例句，按 SM-2 间隔调度。

本地运行，数据存 JSON，无需数据库。

---

## 功能概览

| 模块 | 说明 |
|------|------|
| **新学** | 按词频或手动选词 → AI 流式生成原创小故事 → 四阶段学习 |
| **复习** | 到期词直接进入 stage3/4，复用你之前学过的例句，不重新写故事 |
| **记忆系统** | 事件流 + 聚合卡片；SM-2 仅在 stage4 结束时更新一次 |
| **批改** | stage3/4 由 AI 批量批改；stage3 提交后展示批改报告 |
| **断点续学** | 首页「继续上次」+ `localStorage` 记录进度 |
| **错题本** | 从学习事件流读取，复习时自动混入 |

### 四阶段流程（新学）

1. **读故事** — 带标注的原创中文故事，单词以 `（word）` 形式嵌入语境  
2. **猜词义** — 故事中的英文被遮住，根据语境回忆释义  
3. **写卡片** — 看例句完成拼写、释义、造句，AI 批改并给出反馈  
4. **默写** — 无提示最后一关；完成后展示每个词的下次复习时间  

复习模式跳过前两步，只走「写卡片 → 默写」。

---

## 技术栈

- **后端**：Python 3.10+、FastAPI、Uvicorn、OpenAI SDK（兼容 SiliconFlow 等 OpenAI 格式 API）
- **前端**：原生 HTML / CSS / JS（ES Module），无构建步骤
- **存储**：本地 JSON 文件（`data/` 目录）
- **AI**：故事生成、例句补全、释义/拼写/造句批改

---

## 项目结构

```
WordSaga/
├── backend/
│   ├── app/
│   │   ├── api/          # REST 路由
│   │   ├── services/     # 业务逻辑（故事、记忆、批改、调度）
│   │   ├── schemas/      # Pydantic 模型
│   │   └── storage/      # JSON 读写
│   ├── scripts/          # 数据迁移与重算脚本
│   ├── tests/            # 单元测试
│   └── run.ps1           # Windows 启动脚本
├── frontend/
│   ├── index.html
│   ├── css/main.css
│   └── js/
│       ├── app.js        # 页面与交互
│       └── api.js        # API 封装
├── data/
│   ├── cet_full_list.json    # 词库（四级/六级）
│   ├── learning_data.json    # Session 与学习记录
│   ├── word_memory.json      # 单词记忆聚合卡片
│   ├── word_events.json      # 学习事件流
│   └── settings.json         # 词频进度等
└── .env                      # API 密钥（需自行创建）
```

---

## 快速开始

### 1. 环境要求

- Python 3.10+
- 可访问的 OpenAI 兼容 API（默认 [SiliconFlow](https://siliconflow.cn)）

### 2. 配置 `.env`

在项目根目录创建 `.env`：

```env
OPENAI_API_KEY=你的_API_Key
OPENAI_MODEL=你的模型名
# 可选，默认 https://api.siliconflow.cn/v1
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
```

### 3. 安装依赖

```powershell
cd backend
pip install -r requirements.txt
```

### 4. 启动服务

**Windows（推荐）：**

```powershell
cd backend
.\run.ps1
```

**或手动：**

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
```

### 5. 打开应用

浏览器访问：**http://127.0.0.1:8000**

后端同时托管前端静态文件，改 `frontend/` 或 `backend/app/` 后刷新即可（开发模式带热重载）。

健康检查：`GET http://127.0.0.1:8000/health`

---

## 使用说明

### 新学

1. 首页选「新学」→ 词频计划或手动指定单词  
2. 等待 AI 流式写故事（可边看边读）  
3. 点「读完了，去猜词」进入四阶段  
4. stage3 提交后查看 **批改报告**，再进入默写  
5. 完成页显示每个词的掌握度与 **下次复习时间**

### 复习

1. 首页选「复习」→ 查看到期词数量  
2. 开始复习后直接进入写卡片（复用历史例句）  
3. 走完默写后 SM-2 更新复习间隔

### 断点续学

中途关闭页面后，再次打开首页会出现「继续上次」横幅，可从上次停留的阶段接着学。

---

## 数据与脚本

| 文件 | 用途 |
|------|------|
| `word_events.json` | 每次 stage 提交的原始事件（真相来源） |
| `word_memory.json` | 从事件聚合出的 SM-2 卡片 |
| `learning_data.json` | Session、故事、各阶段答案 |

**从旧版迁移（一次性）：**

```powershell
cd backend
python scripts/migrate_memory.py
```

**从事件流重算记忆卡片：**

```powershell
cd backend
python scripts/recompute_memory.py
```

> 记忆卡片字段必须完整；若 `word_memory.json` 结构过旧，请先跑迁移脚本，而不是依赖运行时自动补字段。

---

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/vocabulary/count` | 词库总量 |
| `GET` | `/api/vocabulary/review/due` | 到期复习词 |
| `POST` | `/api/sessions` | 创建 session（`mode`: `frequency` / `manual` / `review`） |
| `GET` | `/api/sessions/resumable` | 可续学的 session（无则 404） |
| `POST` | `/api/sessions/{id}/generate/stream` | SSE 流式生成故事 |
| `GET/POST` | `/api/sessions/{id}/stage/{1-4}` | 各阶段读写 |
| `GET` | `/api/words/{word}/memory` | 单词记忆档案 |
| `GET` | `/api/words/{word}/events` | 单词学习事件时间线 |
| `GET` | `/api/wrong-book` | 错题本 |

完整交互式文档：启动后访问 http://127.0.0.1:8000/docs

---

## 测试

```powershell
cd backend
python -m unittest tests.test_memory_service -v
```

---

## 记忆算法要点

- **Stage1 完成**：记录首次学习，设置 `incomplete_due_at`（+1 天），不推 SM-2  
- **Stage2/3**：只写事件，不更新 SM-2  
- **Stage4 完成**：按 stage2/3/4 加权 composite 质量更新 SM-2；skip 或任阶段错误则本轮不算掌握  
- **复习 track**（`source=review/wrong`）：composite 只计 stage3+4  
- **Leech**：连续失败或高错误率标记为顽固词  
- **Mastered**：高掌握度 + 足够重复 → 30/90 天长间隔  

---

## 常见问题

**页面提示「无法连接后端」**  
确认在 `backend` 目录启动了 Uvicorn，且端口 8000 未被占用。

**故事生成超时**  
词数较多或 API 较慢时，流式接口最长等待约 10 分钟；stage3/4 批改约 180 秒。

**复习词缺少例句**  
复习依赖历史 session 中的 enriched 例句；若该词从未完整走完过新学流程，会报错，需先新学该词。

**`.env` 缺失**  
启动时会抛出 `缺少配置文件`，在项目根目录创建 `.env` 并填入上述变量。

---

## License

个人学习项目，按需使用与修改。
