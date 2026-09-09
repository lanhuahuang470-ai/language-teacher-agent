# Python 项目编码风格与代码拆分指南

> 基于「多Agent智能会议助手系统」Python 代码库总结，可直接用于指导新项目。

---

## 一、项目分层架构

```
python/
├── src/
│   ├── agents/              # Agent 层：每个 Agent 一个文件，职责单一
│   ├── graph/               # 编排层：LangGraph 状态图定义
│   ├── integrations/        # 集成层：每个外部服务一个 Client 文件
│   ├── models/              # 数据层：Pydantic schemas 统一定义
│   ├── websocket/           # 传输层：FastAPI + WebSocket 服务
│   ├── tests/               # 测试层：与源码镜像，按模块组织
│   └── main.py              # 入口：仅负责启动，无业务逻辑
├── requirements.txt         # 按功能分组 + 版本约束
├── Dockerfile
└── docker-compose.yml
```

### 分层原则

| 层 | 职责 | 依赖方向 |
|---|---|---|
| `models/` | 全局共享数据结构（Pydantic models、Enum、TypedDict） | 被所有层引用，不依赖其他层 |
| `integrations/` | 外部服务封装（LLM API、Jira、飞书、邮件、向量库） | 仅依赖 `models/` |
| `agents/` | 业务逻辑节点，每个 Agent 实现 `async process(state) -> state` | 依赖 `integrations/` + `models/` |
| `graph/` | 编排 Agent 的执行拓扑（Pipeline / Fan-out / Fan-in） | 依赖 `agents/` + `integrations/` + `models/` |
| `websocket/` | HTTP/WebSocket 端点，调用 graph 层入口 | 依赖 `graph/` + `models/` |
| `main.py` | 启动入口，仅加载环境变量 + uvicorn.run | 依赖 `websocket/` |

**核心规则：依赖只能向下流动，禁止反向引用。**

---

## 二、代码拆分规则

### 2.1 一个模块一个文件

- 每个 Agent = 一个 `.py` 文件（`transcription_agent.py`、`summary_agent.py`…）
- 每个外部服务 Client = 一个 `.py` 文件（`minimax_client.py`、`jira_client.py`…）
- 文件名 = `<功能名>_agent.py` / `<服务名>_client.py`，全小写下划线

### 2.2 `__init__.py` 做聚合导出

每个包的 `__init__.py` 职责：导入子模块的公开符号，定义 `__all__`。

```python
from .transcription_agent import TranscriptionAgent
from .summary_agent import SummaryAgent

__all__ = ["TranscriptionAgent", "SummaryAgent"]
```

调用方只需 `from ..agents import TranscriptionAgent`，不需要知道文件路径。

### 2.3 文件大小控制

- 单文件控制在 **200~300 行**以内
- 超过则拆分为子模块（如 `integrations/` 下每个服务独立文件）
- `server.py`（WebSocket 路由）例外允许较大，但仍按 `# ====== 分隔` 做区块划分

### 2.4 Prompt 与代码分离

LLM Prompt 定义为模块级常量（大写 + 下划线），不混在方法体内：

```python
SUMMARY_SYSTEM_PROMPT = """你是一位专业的会议纪要助手..."""
SUMMARY_USER_PROMPT = """请根据以下会议转写文本...{transcript}..."""
```

用 `.format()` 注入变量，保持 Prompt 可独立审阅和修改。

---

## 三、编码风格规范

### 3.1 文件头：三引号 docstring 描述模块职责

每个 `.py` 文件开头必须有模块级 docstring，说明「这个文件做什么」：

```python
"""
Transcription Agent（转写Agent）
- 接收音频数据，使用 WhisperX 进行语音转文字
- 使用 pyannote-audio 进行说话人识别
- 输出带说话人标签和时间戳的转写文本
"""
```

### 3.2 类设计

每个类包含三层文档：

```python
class TranscriptionAgent:
    """
    转写Agent - Pipeline的第一个节点

    架构说明:        # 1. 这个类的架构角色和数据流
    面试考点:        # 2. 设计决策的 WHY（可选）
    """

    def __init__(self, config: TranscriptionConfig | None = None):
        # 构造参数全部可选，None 时走默认值/环境变量
        self.config = config or TranscriptionConfig()
        self._model = None        # 私有属性前缀 _
        self._initialized = False

    async def process(self, state: dict) -> dict:
        """
        LangGraph 节点函数 —— 执行语音转写    # 3. 方法文档：一句话说明做什么

        Args:                                     # 参数说明
            state: MeetingState 字典
        Returns:                                  # 返回值说明
            更新后的 state
        """
```

### 3.3 类型标注

- 全量使用 Python 3.10+ 类型标注
- 可选参数用 `| None = None`（不用 `Optional[T]`）
- 文件头加 `from __future__ import annotations` 延迟注解求值
- 容器类型用小写泛型：`list[str]`、`dict[str, Any]`（不用 `List`/`Dict`）

### 3.4 命名规范

| 类型 | 规范 | 示例 |
|---|---|---|
| 类 | PascalCase | `TranscriptionAgent`、`MiniMaxClient` |
| 函数/方法 | snake_case | `async def process()`、`def _lazy_init()` |
| 常量 | UPPER_SNAKE | `SUMMARY_SYSTEM_PROMPT`、`BASE_URL` |
| 私有方法 | 前缀 `_` | `def _transcribe()`、`def _generate_demo_transcript()` |
| 私有属性 | 前缀 `_` | `self._model`、`self._enabled` |
| 静态方法 | `@staticmethod` | 无需 self/cls 的纯函数 |

### 3.5 异步优先

- 所有 I/O 操作（LLM 调用、API 请求、WebSocket）一律 `async def`
- 同步库（如 `jira` SDK）通过 `_get_client()` 懒加载，在 async 方法中直接调用
- `httpx.AsyncClient` 替代 `requests`

### 3.6 错误处理模式

每个 Agent 的 `process()` 遵循统一模式：

```python
async def process(self, state: dict) -> dict:
    try:
        # 正常业务逻辑
        result = await self._do_work(...)
        state["key"] = result
    except Exception as e:
        logger.error(f"[AgentName] Error: {e}")
        state["errors"] = state.get("errors", []) + [f"AgentName: {str(e)}"]
        state["key"] = self._fallback()    # 降级方案
    return state
```

**关键原则：**
- Agent 内部 catch 所有异常，错误写入 `state["errors"]`，**不抛出到 Graph 层**
- 一个 Agent 失败不阻塞其他并行 Agent
- 每个失败都有降级方案（fallback），Pipeline 不中断

### 3.7 日志规范

使用 `loguru.logger`，不用标准 `logging`：

```python
logger.info(f"[TranscriptionAgent] Processing meeting: {meeting_id}")
logger.warning("No audio data provided, using demo transcript")
logger.error(f"[TranscriptionAgent] Error: {e}")
```

- 日志前缀 `[AgentName]` 标识来源
- `info`：正常流程里程碑
- `warning`：降级、缺失数据、跳过
- `error`：异常但不中断

### 3.8 配置注入模式

所有 Client/Agent 的构造函数参数全部可选：

```python
class MiniMaxClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "abab6.5s-chat",
    ):
        self.api_key = api_key or os.getenv("MINIMAX_API_KEY", "")
```

**优先级：显式传参 > 环境变量 > 默认值**

这样设计的好处：
1. 生产环境通过环境变量配置
2. 测试时直接传 mock 对象
3. Graph 层统一注入共享实例

### 3.9 懒加载模式

大模型、外部 SDK 连接延迟到首次使用时初始化：

```python
def _lazy_init(self):
    if self._initialized:
        return
    import whisperx  # 延迟导入，避免未安装时启动崩溃
    self._model = whisperx.load_model(...)
    self._initialized = True
```

### 3.10 重试机制

外部 API 调用统一使用 `tenacity` 装饰器：

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def chat(self, ...):
    ...
```

---

## 四、数据模型规范（models/schemas.py）

### 4.1 统一 Schema 文件

所有 Pydantic model、Enum、TypedDict 集中在 `models/schemas.py`，通过 `models/__init__.py` 聚合导出。

### 4.2 Pydantic v2 用法

```python
class TranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="ignore")  # 忽略未知字段

    speaker: str = "Unknown"          # 字段都有默认值
    text: str = ""
    start: float = 0.0
    confidence: float = 0.0
```

- `model_config = ConfigDict(extra="ignore")`：防止外部 API 返回多余字段导致解析失败
- 列表字段用 `Field(default_factory=list)`，不用 `[]`（避免可变默认值陷阱）
- Enum 继承 `str, Enum` 确保可 JSON 序列化

### 4.3 TypedDict 对齐 Graph 状态

LangGraph 的共享状态用 `TypedDict` 定义，与 Pydantic model 分开：

```python
class MeetingState(TypedDict, total=False):
    meeting_id: str
    transcript: Any
    summary: Any
    errors: list[str]
```

`total=False` 允许部分字段缺失，适配 Pipeline 各阶段逐步填充状态。

### 4.4 工厂函数创建初始状态

```python
def create_initial_state(meeting_id, audio_data=b"", ...) -> dict:
    return {"meeting_id": meeting_id, "errors": [], ...}
```

不在调用方手写 dict，统一通过工厂函数保证字段完整性。

---

## 五、Agent 设计规范

### 5.1 统一接口

每个 Agent 必须实现 `async process(state: dict) -> dict`，作为 LangGraph 节点函数。

### 5.2 内部方法分层

```
process()           # 公开接口：读 state → 调内部方法 → 写 state → return state
├── _extract_xxx()  # 私有：调用 LLM / 外部服务
├── _compute_xxx()  # 私有：规则引擎 / 确定性计算
└── _format_xxx()   # 私有：格式化输出
```

### 5.3 规则 vs LLM 分工

- **确定性计算**（统计、计数、排序）→ `@staticmethod` 纯函数，不依赖 LLM
- **语义理解**（情绪、关键词、摘要）→ LLM 调用

```python
# 规则引擎 — 不用 LLM
@staticmethod
def _compute_speaker_stats(transcript) -> list[SpeakerStats]:
    ...

# LLM 分析 — 调 MiniMax
async def _analyze_with_llm(self, text, stats) -> dict:
    ...
```

### 5.4 Prompt 工程规范

1. **System Prompt**：定义角色 + 规则 + 输出格式约束
2. **User Prompt**：注入上下文数据 + 输出格式模板（用 `{{ }}` 转义 JSON 花括号）
3. **强制 JSON 输出**：`response_format={"type": "json_object"}`
4. **解析降级**：`json.loads` 失败时，截取 `{...}` 部分重试

---

## 六、Graph 编排规范

### 6.1 依赖注入

Graph 构建函数接收所有 Client 实例，None 时自动创建默认值：

```python
def build_meeting_graph(
    llm_client: MiniMaxClient | None = None,
    jira_client: JiraClient | None = None,
    ...
) -> StateGraph:
    llm = llm_client or MiniMaxClient()
    # 创建 Agent 时注入共享 Client
    summary_agent = SummaryAgent(llm)
    action_agent = ActionAgent(llm, jira, feishu)
```

**关键：同一个 `llm` 实例被多个 Agent 共享，避免重复创建连接池。**

### 6.2 三层 API

```python
build_meeting_graph()      # 构建图 → 返回 StateGraph
compile_meeting_graph()     # 编译 → 返回可执行图
run_meeting_pipeline()     # 对外入口 → 构建 + 编译 + 执行 → 返回最终 state
```

### 6.3 ASCII 图注释

Graph 文件顶部用 ASCII art 画编排拓扑，直观展示 Fan-out / Fan-in：

```
  START → Transcription → [Summary, Action, Insight] → Follow-up → END
```

---

## 七、集成层（integrations/）规范

### 7.1 Client 统一模式

每个外部服务 Client 遵循：

```python
class XxxClient:
    BASE_URL = "https://api.xxx.com/v1"

    def __init__(self, **kwargs):
        # 参数从 kwargs 或环境变量读取
        self._enabled = bool(...)

    @property
    def is_enabled(self) -> bool:          # 统一启用检查
        return self._enabled

    @retry(stop=..., wait=...)              # 统一重试
    async def do_something(self, ...) -> ...:
        if not self._enabled:
            logger.warning("Xxx not configured, skipping")
            return None / False / []
        ...

    async def close(self):                 # 统一关闭接口
        ...

    async def __aenter__(self):            # 支持异步上下文管理器
        return self
    async def __aexit__(self, *args):
        await self.close()
```

### 7.2 Token 自动刷新

涉及认证的 Client（如飞书）内部缓存 token + 过期时间：

```python
async def _get_tenant_token(self) -> str:
    if self._tenant_token and time.time() < self._token_expires_at:
        return self._tenant_token          # 缓存命中
    # 过期则重新获取
```

---

## 八、Web 服务规范

### 8.1 FastAPI 应用结构

```python
app = FastAPI(title="...", version="1.0.0")
app.add_middleware(CORSMiddleware, ...)     # 跨域

# 模块级变量（内存存储，生产换 Redis）
active_connections: dict[str, WebSocket] = {}
meeting_results: dict[str, dict] = {}

# 请求/响应模型
class MeetingStartRequest(BaseModel): ...

# 错误处理辅助函数
def _raise_not_found(meeting_id): ...
def _raise_bad_request(detail, error_code): ...

# 端点按区块注释分隔
# ========== WebSocket 端点 ==========
# ========== REST API 端点 ==========
```

### 8.2 REST API 路径规范

```
GET  /                                     # 健康检查
POST /api/v1/meeting/start                 # 创建资源
POST /api/v1/meeting/{id}/upload           # 上传文件
POST /api/v1/meeting/{id}/demo             # 演示模式
GET  /api/v1/meeting/{id}/transcript       # 获取子资源
GET  /api/v1/meeting/{id}/summary
GET  /api/v1/meeting/{id}/report           # 获取完整报告
```

### 8.3 WebSocket 协议

JSON 控制消息 + 二进制音频帧：

```json
// 客户端 → 服务端
{"type": "start"}    // 开始录制
{"type": "stop"}     // 停止并触发处理
{"type": "demo"}     // 演示模式
{"type": "ping"}     // 心跳
<binary>             // 音频数据

// 服务端 → 客户端
{"type": "connected", ...}
{"type": "recording", "buffer_size": ..., "duration_s": ...}
{"type": "processing", "stage": "transcription", ...}
{"type": "transcript", "data": {...}}    // 分步推送结果
{"type": "completed", "processing_time_s": ...}
```

### 8.4 后台任务

大文件上传用 `BackgroundTasks` 异步处理，立即返回 202：

```python
@app.post("/api/v1/meeting/{id}/upload", status_code=202)
async def upload_audio(meeting_id, background_tasks: BackgroundTasks, file: UploadFile):
    # 校验格式 + 大小
    background_tasks.add_task(_process_upload_background, ...)
    return {"status": "processing", ...}
```

---

## 九、测试规范

### 9.1 测试文件组织

- 测试文件与源码包结构镜像：`src/tests/test_<模块名>.py`
- 文件名 = `test_` 前缀 + 被测模块名

### 9.2 测试类组织

按功能分组为测试类，类名 = `Test<功能描述>`：

```python
class TestChromaClientInit:
    """初始化和配置测试"""

class TestChromaClientStoreMeetingAsync:
    """异步存储会议数据测试"""
```

### 9.3 测试方法命名

`test_<被测行为>_<条件/场景>`：

```python
def test_store_meeting_returns_false_when_disabled(self, tmp_path):
def test_store_meeting_with_summary(self, tmp_path):
def test_store_transcript_with_segments(self, tmp_path):
```

### 9.4 Mock 策略

- 外部依赖（API、DB）用 `unittest.mock.patch` + `MagicMock`
- 环境变量用 `patch.dict(os.environ, {...})`
- 文件系统用 pytest fixture `tmp_path`
- 异步测试标记 `@pytest.mark.asyncio`

---

## 十、配置与部署规范

### 10.1 环境变量优先

所有配置通过 `os.getenv()` 读取，不在代码中硬编码：

```python
self.api_key = os.getenv("MINIMAX_API_KEY", "")
self.host = os.getenv("CHROMA_HOST", "")
```

### 10.2 requirements.txt 分组

用注释按功能分组，每个依赖带 `>=` 版本下限：

```txt
# === Agent Framework ===
langgraph>=0.2.0

# === LLM Providers ===
openai>=1.50.0

# === Testing ===
pytest>=8.3.0
```

### 10.3 Docker

- `Dockerfile`：`python:3.11-slim` 基础镜像，仅装系统依赖（ffmpeg）
- `docker-compose.yml`：应用 + PostgreSQL + Redis 三服务，`env_file` 加载 `.env`
- 源码通过 volume 挂载，支持热重载

---

## 十一、速查清单

写新文件 / 新模块时逐条检查：

- [ ] 文件头有三引号 docstring 说明职责
- [ ] `from __future__ import annotations`
- [ ] 全量类型标注（`list[str]` 不用 `List[str]`）
- [ ] 类有 docstring（架构说明 + 设计理由）
- [ ] 公开方法有 docstring（Args + Returns）
- [ ] 私有方法/属性加 `_` 前缀
- [ ] 构造函数参数全部可选（`| None = None`）
- [ ] 配置从环境变量读取，有默认值
- [ ] I/O 操作是 `async`
- [ ] 外部调用有 `@retry` 装饰
- [ ] Client 有 `is_enabled` 属性 + `close()` + `__aenter__/__aexit__`
- [ ] Agent 的 `process()` 有 try/except + 降级方案
- [ ] 日志带 `[AgentName]` 前缀
- [ ] `__init__.py` 导出公开符号 + `__all__`
- [ ] 单文件不超过 ~300 行
