# Werewolf AI

AI 狼人杀 —— 多 LLM Agent 对战的狼人杀模拟平台。

## 架构

- **backend/** — FastAPI (Python)，游戏引擎、LLM 客户端、Agent 系统、SSE 实时通信
- **frontend/** — React 19 + TypeScript + Vite，游戏界面、回放、设置

## 快速开始

### 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

### 配置 API Provider

启动后端后访问 http://localhost:5173/settings，添加 LLM Provider（智谱、DeepSeek、Kimi 等）。

或直接编辑 `backend/data/settings.json`，填入你的 API Key。

## 游戏流程

1. 设置页面创建对局（选择板子、配置玩家、分配模型）
2. 实时观看 AI Agent 发言、投票、使用技能
3. 对局结束后自动保存复盘数据
4. 历史对局页可回放完整复盘

## License

MIT
