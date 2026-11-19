# Study Assistant

A Docker-based Bible study helper chatbot with a **React** frontend, **FastAPI + LangGraph** backend, and a **PostgreSQL** database — all wired together with Docker Compose and ready to open in VS Code Dev Containers.

---

## 📁 Project Structure

```
study_assistant/
├── .devcontainer/
│   └── devcontainer.json        # VS Code Dev Container configuration
├── frontend/                    # React (Vite) chatbot UI
│   ├── src/
│   │   ├── components/
│   │   │   └── ChatInterface.jsx
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── Dockerfile
├── backend/                     # FastAPI + LangGraph Python service
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point + CORS
│   │   ├── agent/
│   │   │   └── graph.py         # LangGraph agent graph
│   │   ├── database/
│   │   │   ├── session.py       # SQLAlchemy engine, session, Base
│   │   │   └── models.py        # Checkpointer ORM model
│   │   └── routes/
│   │       └── agent.py         # /invoke and /checkpointer routes
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml           # Orchestrates frontend + backend + db
├── .env.example                 # Environment variable template
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose)
- [VS Code](https://code.visualstudio.com/) with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) *(optional but recommended)*

### 1. Clone and configure environment variables

```bash
git clone https://github.com/IjtsiRamos/study_assistant.git
cd study_assistant
cp .env.example .env
```

Open `.env` and fill in at minimum your **OpenAI API key**:

```
OPENAI_API_KEY=sk-your-key-here
```

### 2. Start all services with Docker Compose

```bash
docker compose up --build
```

| Service   | URL                            |
|-----------|--------------------------------|
| Frontend  | http://localhost:5173          |
| Backend   | http://localhost:8000          |
| API Docs  | http://localhost:8000/docs     |
| PostgreSQL| localhost:5432                 |

### 3. Stop services

```bash
docker compose down
```

To also remove the database volume:

```bash
docker compose down -v
```

---

## 🖥️ Opening in VS Code Dev Container

1. Open VS Code in the project root.
2. Press **F1** → `Dev Containers: Reopen in Container`.
3. VS Code will build the images, start all services, and open a terminal inside the **backend** container with Python already configured.
4. Ports 5173, 8000, and 5432 are forwarded automatically.

---

## 🛠️ Local Development (without Docker)

### Frontend

```bash
cd frontend
npm install          # install dependencies
npm run dev          # start Vite dev server at http://localhost:5173
```

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# Make sure PostgreSQL is running and DATABASE_URL is set, then:
uvicorn app.main:app --reload
```

---

## 🔌 API Reference

### `POST /api/agent/invoke`

Send a message to the LangGraph agent.

**Request body:**
```json
{
  "message": "Explain Genesis 1:1",
  "thread_id": "unique-conversation-id"
}
```

**Response:**
```json
{
  "response": "In the beginning God created...",
  "thread_id": "unique-conversation-id"
}
```

### `DELETE /api/agent/checkpointer/{thread_id}`

Delete / reset the conversation checkpointer for a thread. Returns `204 No Content`.  
Use this to clear a stuck or buggy conversation from the database.

### `GET /health`

Returns `{"status": "ok"}` — useful for Docker health checks.

---

## 🧩 Architecture

```
Browser
  │
  │  HTTP (port 5173)
  ▼
┌─────────────┐
│  Frontend   │  React + Vite
│  (port 5173)│
└──────┬──────┘
       │ HTTP /api/* (proxied to backend:8000)
       ▼
┌─────────────┐
│  Backend    │  FastAPI + LangGraph
│  (port 8000)│
└──────┬──────┘
       │ SQLAlchemy (port 5432)
       ▼
┌─────────────┐
│  PostgreSQL │  Checkpointer storage
│  (port 5432)│
└─────────────┘
```

The Vite dev server proxies all `/api/*` requests to the backend, so the frontend never has to hardcode the backend port in production-like usage.

---

## 🔧 Extending the Agent

The LangGraph agent lives in `backend/app/agent/graph.py`.  
To add tools or more complex graph nodes:

1. Define `@tool`-decorated functions in `backend/app/agent/graph.py`.
2. Bind them to the model: `llm.bind_tools(tools)`.
3. Add a `ToolNode` and conditional edges as documented in [LangGraph docs](https://langchain-ai.github.io/langgraph/).

---

## 📦 Tech Stack

| Layer     | Technology                  |
|-----------|-----------------------------|
| Frontend  | React 18, Vite 5, Axios     |
| Backend   | Python 3.11, FastAPI, Uvicorn |
| AI/Agent  | LangGraph, LangChain, OpenAI |
| Database  | PostgreSQL 15, SQLAlchemy 2 |
| Container | Docker, Docker Compose      |
