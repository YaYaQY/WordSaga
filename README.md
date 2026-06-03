# WordSaga · 词境

把单词放进 AI 写的小故事里，用「读 → 猜 → 写 → 默写」四步完成记忆；复习时复用历史例句，按 SM-2 间隔调度。
---
<img width="1773" height="2364" alt="微信图片_20260602231611_23_3" src="https://github.com/user-attachments/assets/21b1bee9-5f8b-49a8-ae44-c62e63f6bf77" />


## 功能概览

| 模块 | 说明 |
|------|------|
| **新学** | 按词频或手动选词 → AI 流式生成原创小故事 → 四阶段学习 |
| **复习** | 到期词直接进入 stage3/4，复用你之前学过的例句，不重新写故事 |
| **薄弱巩固** | 专练常错/掌握不稳/顽固词，不推进词频，复用例句走 stage3/4 |
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
├── .env.example              # 配置模板（复制为 .env）
└── .gitignore                # 忽略 .env 与用户学习数据
```

> **Git 说明**：`data/` 下的学习进度（`word_memory.json` 等）和 `.env` **不会**提交到仓库，只留在本机。克隆后需自行配置 `.env`；学习数据会在你使用过程中自动生成。

---

## 快速开始

### 1. 环境要求

- Python 3.10+
- 可访问的 OpenAI 兼容 API

### 2. 配置 `.env`

复制模板并填写密钥：

```powershell
copy .env.example .env
```

编辑 `.env`：

```env
OPENAI_API_KEY=你的_API_Key
OPENAI_MODEL=你的模型名
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
   - **词频模式**会自动混入约 **30%** 的到期/错题复习词；生成故事与读故事页会显示「本轮含 X 个复习词，Y 个新词」。纯新词复习请用首页「复习」入口。  
2. 等待 AI 流式写故事（可边看边读）  
3. 点「读完了，去猜词」进入四阶段  
4. stage3 提交后查看 **批改报告**，再进入默写  
5. 完成页显示每个词的掌握度与 **下次复习时间**

### 复习

1. 首页选「复习」→ 查看到期词数量  
2. 开始复习后直接进入写卡片（复用历史例句）  
3. 缺少例句的词会自动跳过，界面会列出跳过名单  
4. 走完默写后 SM-2 更新复习间隔

### 薄弱巩固

1. 首页选「薄弱巩固」→ 查看待巩固词数量  
2. 不推进 `last_learned_rank`，专门练错题多、掌握度低、顽固词  
3. 流程与复习相同（stage3/4 + 复用例句），同样会跳过无例句的词

### 自选练习（手动）

不推进词频进度，可重复指定同一批词；仍会写入学习事件与记忆曲线。

### 断点续学

- **stage1–4**：首页「继续上次」回到对应阶段  
- **故事未生成**：继续流式生成  
- **生成中断**：可选择「继续写完」（清空半成品后重生成）或「放弃这轮」

### 单词档案

错题本中点击单词名，可查看掌握度、下次复习时间与学习事件时间线。

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
| `POST` | `/api/sessions` | 创建 session（`mode`: `frequency` / `manual` / `review` / `weak`），返回 `skipped_words` |
| `GET` | `/api/vocabulary/weak/count` | 薄弱巩固候选词数量 |
| `POST` | `/api/sessions/{id}/reset-story` | 生成中断后清空半成品故事 |
| `DELETE` | `/api/sessions/{id}` | 放弃未完成的生成 session |
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

| 界面提示 | 可能原因 | 处理 |
|----------|----------|------|
| 无法连接后端 | 未启动 Uvicorn 或端口不对 | 在 `backend` 目录执行 `.\run.ps1`，访问 http://127.0.0.1:8000/health |
| 请求超时 | 默认 30s；故事流最长约 10 分钟；stage3/4 批改 180s | 减少本轮词数或换更快模型 |
| API 密钥无效或未授权 | `.env` 中 `OPENAI_API_KEY` 错误 | 对照 `.env.example` 检查，必要时在平台轮换密钥 |
| 请求过于频繁或被限流 | 上游 429 | 稍后再试或降低并发 |
| 服务器错误（5xx） | 后端 `RuntimeError`（如记忆字段缺失） | 看终端日志；`word_memory` 过旧时运行 `migrate_memory.py` |
| 缺少配置文件 | 无 `.env` | `copy .env.example .env` 并填写 |

**复习词缺少例句**  
复习依赖历史 session 中的 enriched 例句；若该词从未完整走完过新学流程，会报错，需先新学该词。

**从 Git 克隆后没有学习记录**  
学习数据在本地 `data/`，不在仓库中，属正常现象。

---

## License

个人学习项目，按需使用与修改。
