# ai-engineer-assesment-sutra-ai

Submission for the assessment of AI Engineer at Sutra.AI

A light-weight assistant for "ACME Corporation" (AI generated corporation name and documents) that answers policy questions from documents, numeric questions from a branch revenue/orders CSV, and external questions via web search. It runs on the Claude Agent SDK with all capabilities exposed as tools over an MCP server.

## Setup

- Run the following commands in a terminal to clone the repo and navigate to the directory: 

```
git clone https://github.com/sharmajatin567/ai-engineer-assesment-sutra-ai.git
cd ai-engineer-assesment-sutra-ai
```

- Setup virtual environment, activate, and install requirements: 
```
python -m venv venv
source venv/bin/activate # for activating virtual env. Use venv\Scripts\activate for windows
pip install -r requirements.txt
```

- Add a .env and setup your `ANTHROPIC_API_KEY` for claude_agent_sdk and `TAVILY_API_KEY` for Tavily Web Search

- Run chromadb server locally on terminal:
```
chroma run --path ./chromad_db
```

- Open a new terminal inside the git directory, activate virtual environment and run the following:
```
python embed_documnts.py # embed the current documents
python app/main.py # run the agent
```

- Type in your query and see the agent answer. To check agent event trace in terminal, uncomment **line 36** in `main.py`

## Architecture

The flow is a single agent loop driven by 4 tools : `similarity_search`, `csv_schema`, `operate_on_csv`, and `web_search`

1. `app/main.py` - runs the agent in terminal. Each query is passed to the agent runtime along with the running conversation transcript.
2. `ClaudeAgentSDKRuntime` (`app/base/agent_runtime/agent_runtime.py`) - calls the Claude Agent SDK `query()` with the system prompt, `max_turns`, and an MCP server. The model plans, calls tools, and streams back thoughts, tool calls, tool results, and a final answer, which are collected into an event trace.
3. `app/mcp_server/server.py` - FastMCP stdio server exposing the four tools
4. Document retrieval goes to ChromaDB (`app/base/knowledge/knowledge.py`); - structured questions go to the pandas-backed CSV tools; external questions go to Tavily web searc tool (External tool implementation).
5. After each answer, `main.py` prints the trace (commented right now), records a Helpful / Not Helpful rating, and writes the full run (query, events, final answer, feedback) to `app/logs/` as JSON files.

Retrieval data is prepared offline by `app/scripts/embed_documents.py`, which parses the source PDFs and populates the ChromaDB collections.

**Abstraction** The codebase is structured around config-driven factories with abstract base classes under `app/base/`, so providers can be swapped without touching call sites:

- `AgentRuntimeBase` + `AgentRuntimeClientFactory` — runtime providers (currently `claude_agent_sdk`) , planning to implement `deepagents`.
- `KnowledgeBase` + `KnowledgeBankClientFactory` — vector store providers (currently `chromadb`).
- `LLMBase` + `LLMClientFactory` — direct LLM providers (currently `anthropic`). This is a placeholder for now and is not in use. 

Each factory reads `DEFAULT_PROVIDER` and `PROVIDERS` from `app/config/config.yaml` and maps the name to a class. Adding a new provider means adding a class and a config block — no changes elsewhere. The `LLM` abstraction is prepared for direct-generation use cases; the active answer path uses the agent-SDK runtime.

## Chunking Strategy

Documents are indexed two ways from the same PDFs:

- **Section chunks** : PDFs are split on detected headings (numbered sections and Step patterns) by `parse_sections`, preserving `document_name`, `section_name`, and `page_number` metadata. One chunk ≈ one logical section.

- **Character chunks** : `RecursiveCharacterTextSplitter` with **chunk size 200 characters** and **overlap 20 characters** (10%).

**Reason:** the two granularities serve different questions. Section chunks keep a whole policy/process together for questions that require full section knowledge. Small character chunks give tight, precise matches for narrow fact lookups. The 10% overlap keeps a fact from being lost on boundary chunk fetches. A small chunk size was chosen to keep retrieved context focused and citations precise for a small model — at the cost of surrounding context. 

## Retrieval

- **Embedding model:** ChromaDB's default embedding function, `all-MiniLM-L6-v2`. No embedding model is set explicitly, so the collection default applies.
- **Top-k:** `5` (`TOP_K` in config), with a cosine `SIMILARITY_THRESHOLD` of `0.3`; collections use `hnsw:space: cosine` and distances are converted to similarity (1 - distance).

**Reason:** the default embedder is free and can be used locally — adequate for a small internal corpus with no external API dependency. Top-k 5 balances recall against feeding too much noisy context to `claude-haiku-4-5`. The 0.3 threshold drops weak matches so the agent can honestly report "not enough information" rather than answer from irrelevant passages.

## Structured Data

The CSV is handled as **code generation over a dataframe**, not text-to-SQL (which is usually common in current data extraction based agents):

- `csv_schema()` returns row count, column names, and dtypes so the model knows the exact schema. The agent reads the columns to prepare precide code with correct column names. 
- `operate_on_csv(code)` loads a fresh copy of the CSV into a dataframe `df`, executes the model-generated Python, and returns the value the code assigns to `result` variable.

The dataset is strictly read-only: every call gets a fresh `df`, the model is instructed (via `csv_skill.md` and the system prompt) to only read/aggregate, and there is no write path back to the file. This lets the model express arbitrary aggregations (group-by, filter, max/min) in a couple of iterations without a custom query language.

## Tool Calling

**Selection logic.** The system prompt defines routing rules and the model chooses the tool: vector store for policy/process questions (section index for whole-section answers, chunk index for narrow facts), CSV tools for numeric analyitical questions, and web search only for information external to ACME. `allowed_tools` restricts auto-approved tools to the four `mcp__local__*` tools.

**Failure handling.**
- `similarity_search` returns an explicit "no sufficiently relevant passages" message when everything falls below the threshold; the system prompt then requires the agent to say it lacks the information rather than guess.
- `operate_on_csv` returns an error string if the generated code produces no `result` variable, letting the model correct and retry within its turn budget.
- `web_search` returns "No web results found." when empty.
- The runtime wraps the SDK stream in `try/except` so a mid-run error (including hitting `max_turns`) preserves the partial trace and appends a `[runtime error]` event instead of losing everything. `main.py` also guards the whole call.

## Feedback Loop

After every answer the user is asked **Helpful / Not Helpful**, and the rating is written alongside the full event trace to `app/logs/query_*.json`.

**Why this is not RLHF: ** RLHF trains a reward model from preference data and then updates the base model's weights with reinforcement learning. Here nothing of the sort happens: the model is frozen, there is no reward model and no gradient updates. It is a single binary signal logged at inference time — not training.

**How feedback could be used later.** The logs pair each query with its tool trace and outcome, so they can be used for an offline evaluation set, get failed cases/tool calls as context and can drive prompt and top-k/threshold tuning.

## Limitations
1. **Retrieval quality is basic.** A 200-character chunk size fragments context and the default MiniLM embeddings are lightweight, but sufficient for the current AI-generated sample documents. For large corpus, PageIndex - which is an agentic workflow with tree like navigation of documents, can be used. 
2. **Operational dependencies.** ChromaDB must already be running as a separate HTTP server and the collections must be pre-embedded; retrieval fails if either is missing. There is no auto-start or health check.
3. **Short horizon and shallow memory.** `max_turns` is 8, which can cut off genuinely multi-step questions. With introduction to sub-agents, multi-turn context collection can also be enhanced unlike current single list summary.

## Future Improvements

With another day:

- **Introduce New Runtime** — already in progress, requires more agent harness setup effort compared to claude_agent_sdk. Easily configurable via config.yaml and base classes.
- **Improve retrieval** — make the embedding model configurable and try a stronger one, use larger chunks for the chunk index, and tune chunk size, overlap, top-k, and threshold against a real eval set.
- **Introduce Sub-Agents** - due to small scale of the application, the current approach seems sufficient. But for different/conflicting use case documents (like documents being related to corporate, csv being related to pharmaceutical brand data), a multi-node system with subagents can be introduced. 
