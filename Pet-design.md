# HaChiCat — Desktop Pet Agent 设计文档

> **核心理念**：一个平时安静陪伴的可爱桌宠，在用户需要时（快捷键 / 点击）化身 Agent，帮助完成电脑上的小任务。**不是聊天机器人。**

---

## 目录

1. [愿景与目标](#1-愿景与目标)
2. [核心设计原则](#2-核心设计原则)
3. [系统架构总览](#3-系统架构总览)
4. [桌宠视觉系统](#4-桌宠视觉系统)
5. [输入与触发系统](#5-输入与触发系统)
6. [Agent 核心](#6-agent-核心)
7. [工具系统](#7-工具系统)
8. [记忆与存储](#8-记忆与存储)
9. [技术选型](#9-技术选型)
10. [项目结构](#10-项目结构)
11. [参考实现分析](#11-参考实现分析)
12. [开发路线图](#12-开发路线图)

---

## 1. 愿景与目标

### 1.1 产品定位

HaChiCat 是一个 **"桌面宠物 + 快捷工具执行器"** 的结合体：

```
┌──────────────────────────────────────────────────┐
│                    Acc ompet                       │
│                                                    │
│   90% 时间：可爱桌宠，在桌面自由活动                 │
│     - 走动、睡觉、玩耍、跟随鼠标                    │
│     - 不主动说话、不打扰用户                        │
│                                                    │
│   10% 时间：Agent 模式，执行任务                    │
│     - 用户按快捷键触发                              │
│     - 点击桌宠触发                                  │
│     - 自动检测剪贴板意图（可选）                     │
│                                                    │
└──────────────────────────────────────────────────┘
```

### 1.2 核心用例

| 触发方式 | 场景 | 行为 |
|----------|------|------|
| 选中文字 → `Ctrl+Shift+T` | 用户在看网页时发现一个待办事项 | 提取选中文字，添加到 TODO 列表 |
| 复制链接 → `Ctrl+Shift+W` | 用户复制了一个网址 | 在浏览器中打开该链接 |
| `Ctrl+Shift+M` | 用户想听歌 | 打开音乐播放器并开始播放 |
| 点击桌宠 → 选择「记个提醒」 | 用户突然想起一件事 | 弹出输入框，保存提醒 |
| 自动检测剪贴板 | 用户复制了一段「明天下午3点开会」 | 桌宠弹出气泡：「需要我帮你记一个提醒吗？」 |
| `Ctrl+Shift+Q` | 用户想快速搜索 | 弹出搜索框，输入关键词后打开浏览器搜索 |

### 1.3 明确不做什么

- ❌ 不主动发起文字对话
- ❌ 不做长文本闲聊
- ❌ 不做复杂多轮对话
- ❌ 不监控用户隐私数据（剪贴板检测需可选开启）
- ✅ 只做简短气泡提示（如「已添加待办 ✓」）
- ✅ 只做单轮意图识别 + 工具执行
- ✅ 所有数据本地存储

---

## 2. 核心设计原则

### 原则 1：Pet First, Agent Second
> 桌宠的动画质量、可爱程度、交互体验是产品的核心价值。Agent 功能是加分项，不能破坏宠物的存在感。

- 桌宠始终在桌面可见
- 动画流畅（60fps）、过渡自然
- 物理行为合理（重力、碰撞、拖拽）
- 有情绪反馈（任务成功开心、失败沮丧）

### 原则 2：Silent by Default
> 桌宠默认不主动打扰用户。只在用户明确触发时才执行任务。

- Agent 模式是「召唤」而非「对话」
- 气泡提示简洁、自动消失
- 用户可配置「主动程度」（静默 / 偶尔提醒 / 主动建议）

### 原则 3：Modular Tools
> 工具系统高度模块化，添加新功能不需要改动核心代码。

- 每个工具是独立模块
- 统一的工具注册接口
- 支持用户自定义工具

### 原则 4：Local First, Cloud Optional
> 核心功能完全本地运行。LLM 用于智能意图识别，但可选/可替换。

- 基础工具执行不需要 LLM
- 意图识别支持规则匹配 + LLM 双模式
- LLM 后端可切换（Ollama 本地 / Claude API / OpenAI API）

### 原则 5：Graceful Degradation
> 任何组件故障不影响其他部分。LLM 不可用时退化为规则匹配。网络断开时所有本地功能正常。

---

## 3. 系统架构总览

### 3.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Pet Visual Layer (桌宠视觉层)               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ Sprite   │  │ Physics  │  │ Emotion  │  │ Bubble UI    │ │
│  │ Animator │  │ Engine   │  │ System   │  │ (气泡提示)    │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                     Input Layer (输入层)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ Global   │  │ Click    │  │Clipboard │  │ Text Select  │ │
│  │ Hotkeys  │  │ Handler  │  │ Monitor  │  │ Detector     │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                     Agent Core (智能核心)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ Intent   │  │ Task     │  │ Tool     │  │ Permission   │ │
│  │ Classifier│  │ Planner  │  │ Dispatcher│  │ Manager      │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                     Tool Layer (工具层)                        │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────┐ │
│  │ TODO │ │Music │ │Browser│ │File  │ │Timer │ │ Custom   │ │
│  │ Mgr  │ │Ctrl  │ │Opener│ │Ops   │ │      │ │ Tools    │ │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────────┘ │
├─────────────────────────────────────────────────────────────┤
│                     Memory Layer (记忆层)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ SQLite   │  │ Config   │  │ Usage    │  │ Preference   │ │
│  │ Store    │  │ Manager  │  │ History   │  │ Store        │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 进程架构

考虑到桌面宠物的特殊性（需要始终置顶、透明窗口），以及 Agent 逻辑的相对独立性，采用**单进程多线程**架构：

```
Main Process (Python)
├── UI Thread (PySide6 主事件循环)
│   ├── PetWindow (透明置顶窗口，QOpenGLWidget)
│   ├── BubbleWidget (气泡提示)
│   └── SystemTray (系统托盘)
│
├── Input Thread (pynput.Listener)
│   ├── Global Hotkey Dispatcher
│   └── Clipboard Poller (定时检测剪贴板变化)
│
├── Agent Thread (Agent Core)
│   ├── Intent Classifier (规则 + LLM)
│   ├── Tool Dispatcher
│   └── Task Executor
│
└── Worker Threads (ThreadPoolExecutor)
    ├── LLM API Call Worker
    ├── Tool Execution Worker
    └── Background Task Worker
```

**为什么不用多进程**：
- 桌宠 UI 和 Agent 逻辑共享状态频繁（动画状态、气泡消息）
- Python 多进程通信开销大
- 对于本项目的规模，线程模型足够。GIL 不是瓶颈（主要是 I/O 密集型：API 调用、文件读写）

**跨线程通信方式**：
- `Qt Signals/Slots`：UI 线程安全更新
- `queue.Queue`：Input → Agent 的任务投递
- `threading.Event`：线程间通知

### 3.3 数据流

```
用户操作 (快捷键/点击/剪贴板)
       │
       ▼
  Input Layer ──────────────────────────────┐
       │                                     │
       │  (raw_input, trigger_type)          │
       ▼                                     │
  Agent Core                                │
       │                                     │
       ├── 规则匹配命中? ──→ 直接执行 Tool     │
       │                                     │
       ├── 需要 LLM? ──→ LLM API Call        │
       │       │               │             │
       │       │   (intent, params)          │
       │       ▼               │             │
       │   解析 Intent         │             │
       │       │               │             │
       └───────┴───────────────┘             │
               │                             │
               ▼                             │
         Tool Dispatcher                     │
               │                             │
               ▼                             │
          Tool.execute()                     │
               │                             │
       ┌───────┴────────┐                   │
       ▼                ▼                    │
  执行成功          执行失败                   │
       │                │                    │
       ▼                ▼                    │
  Pet Visual:       Pet Visual:             │
  开心动画          沮丧动画                  │
  + 气泡「完成」    + 气泡「失败原因」         │
                                              │
  结果写入 Memory Layer ◄─────────────────────┘
```

---

## 4. 桌宠视觉系统

### 4.1 窗口设计

```
┌──────────────────────────────────────┐
│          Desktop Screen              │
│                                      │
│         ┌──────────┐                │
│         │ ┌──────┐ │  ← 气泡 (QWidget)│
│         │ │ 已添加│ │                │
│         │ │ 待办✓ │ │                │
│         │ └──────┘ │                │
│         │  / \__   │                │
│         │  (· .·)  │ ← 宠物本体      │
│         │  (     ) │   (透明窗口)     │
│         │  ‾‾‾‾‾‾  │                │
│         └──────────┘                │
│                                      │
│   窗口属性:                           │
│   - FramelessWindowHint (无边框)      │
│   - WindowStaysOnTopHint (置顶)       │
│   - WA_TranslucentBackground (透明)   │
│   - Tool (不在任务栏显示)              │
└──────────────────────────────────────┘
```

### 4.2 动画系统

采用**精灵图 (Sprite Sheet) + 状态机**方案，不使用 Live2D（保持简单，降低复杂度）。

```
PetState 状态机:

           ┌──────────────┐
           │    IDLE      │ ← 默认状态，随机眨眼/耳朵动
           └──┬───┬───┬──┘
              │   │   │
    ┌─────────┘   │   └─────────┐
    ▼             ▼             ▼
┌────────┐  ┌──────────┐  ┌──────────┐
│WALKING │  │ SLEEPING │  │ DRAGGING │ ← 用户拖拽
│(走动)  │  │ (睡觉)    │  │ (被拖拽)  │
└───┬────┘  └────┬─────┘  └────┬─────┘
    │            │              │
    └────────────┴──────────────┘
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
┌────────┐  ┌──────────┐  ┌──────────┐
│WORKING │  │  HAPPY   │  │   SAD    │ ← 任务结果反馈
│(工作中)│  │ (开心)    │  │ (沮丧)    │
└────────┘  └──────────┘  └──────────┘

状态转换条件:
  IDLE → WALKING:    定时器触发随机走动
  IDLE → SLEEPING:   连续 N 分钟无交互
  IDLE → DRAGGING:   用户鼠标按下并拖拽
  IDLE → WORKING:    Agent 开始执行任务
  WORKING → HAPPY:   任务成功
  WORKING → SAD:     任务失败
  HAPPY/SAD → IDLE:  动画播放完毕
  ANY → IDLE:        用户交互打断
```

### 4.3 精灵图规范

```
sprite_sheet.png (建议 512×512 或 1024×1024)

每个动画状态占用一行，每帧等宽：

Row 0: IDLE        [frame0][frame1][frame2][frame3]  (4帧, 循环)
Row 1: WALKING     [frame0][frame1][frame2][frame3]  (4帧, 循环)
Row 2: SLEEPING    [frame0][frame1][frame2]          (3帧, 循环)
Row 3: DRAGGING    [frame0][frame1]                   (2帧, 循环)
Row 4: WORKING     [frame0][frame1][frame2][frame3]  (4帧, 循环)
Row 5: HAPPY       [frame0][frame1][frame2][frame3]  (4帧, 播放1次)
Row 6: SAD         [frame0][frame1]                   (2帧, 播放1次)
Row 7: CLICK_REACT [frame0][frame1]                   (2帧, 播放1次)

帧尺寸: 128×128 px (可根据实际精灵图调整)
```

### 4.4 物理行为

```
- 重力: 宠物默认在屏幕底部"地面"上
- 贴边: 碰到屏幕边缘时转向
- 攀爬: 可沿屏幕边缘上下移动（类似 Shimeji）
- 拖拽: 鼠标可拖拽宠物到任意位置，松手后缓缓下落
- 鼠标跟随: IDLE 状态下眼球追踪鼠标位置
- 碰撞: 碰到其他窗口边缘时转向（可选）
```

### 4.5 气泡 UI

```
气泡类型:
  - Info:    「已添加待办 ✓」       (绿色, 2秒消失)
  - Warning: 「需要确认打开浏览器?」  (黄色, 等待用户点击)
  - Error:   「执行失败: 音乐软件未找到」(红色, 3秒消失)
  - Action:  [确认] [取消]           (带按钮, 等待交互)

气泡动画: 淡入 + 上浮 + 淡出
```

---

## 5. 输入与触发系统

### 5.1 全局快捷键

采用**可配置的快捷键注册表**，用户可自定义。

默认快捷键方案：

| 快捷键 | 功能 | 说明 |
|--------|------|------|
| `Ctrl+Shift+T` | 添加 TODO | 选中文字→提取为待办；无选中→弹出输入框 |
| `Ctrl+Shift+M` | 音乐控制 | 打开/切换/暂停音乐 |
| `Ctrl+Shift+W` | 打开网页 | 剪贴板有 URL→直接打开；否则→弹出输入框 |
| `Ctrl+Shift+S` | 快速搜索 | 弹出搜索框，输入关键词后浏览器搜索 |
| `Ctrl+Shift+R` | 快速提醒 | 弹出时间输入框，设置定时提醒 |
| `Ctrl+Shift+A` | 通用 Agent | 打开 Agent 输入框，自由输入指令 |
| `Ctrl+Shift+P` | 显示/隐藏桌宠 | 临时隐藏宠物 |

### 5.2 点击交互

点击桌宠本体弹出**快捷操作菜单**（圆形浮动菜单）：

```
         [🎵 听歌]
    [🔍 搜索]   [📋 待办]
         [🐱 摸头]
    [⏰ 提醒]   [🌐 打开]
         [⚙️ 设置]

  - 摸头: 纯交互, 宠物发出爱心/开心反应
  - 其他: 触发对应工具
```

菜单出现方式：
- 单击桌宠：弹出快捷菜单（4-6 个最常用工具）
- 双击桌宠：直接触发「通用 Agent」输入框
- 右键点击：系统菜单（设置、退出、隐藏等）

### 5.3 剪贴板监听

```
工作流程:
  1. 定时 (每 500ms) 检测剪贴板内容变化
  2. 内容变化时，送入 Intent Classifier
  3. 匹配到高置信度意图时 → 气泡提示建议
     例: 复制了 "https://..." → 气泡 "需要我打开这个网页吗? [打开] [忽略]"
  4. 用户可选择开启/关闭/仅特定类型

隐私保护:
  - 此功能默认关闭，需要用户主动开启
  - 不记录剪贴板历史
  - 仅做实时意图检测，检测完即丢弃
```

### 5.4 文本选择检测（进阶功能）

```
方案: 通过 UI Automation (Windows) 或辅助功能 API 检测文本选择事件
难度: 较高，不同应用兼容性差
替代方案: 用户选中文本后按快捷键触发 (最可靠)
```

**MVP 阶段建议使用快捷键方案**，文本选择自动检测作为远期功能。

---

## 6. Agent 核心

### 6.1 意图分类器 (Intent Classifier)

采用**两级分类**策略：

```
Level 1: 规则匹配 (Rule-based)
  - 零延迟，100% 离线
  - 覆盖 80% 的常见意图
  - 正则 + 关键词 + 模式匹配

Level 2: LLM 分类 (Fallback)
  - 仅在规则无法匹配时调用
  - 使用轻量 Prompt，输出结构化 JSON
  - 可配置本地模型 (Ollama) 或云端 API
```

**规则匹配示例**：

```python
INTENT_RULES = [
    {
        "pattern": r"^(https?://|www\.)\S+$",
        "intent": "open_website",
        "confidence": 0.95,
        "extract_params": lambda m: {"url": m.group(0)}
    },
    {
        "pattern": r"^(明天|今天|下周|(\d+)分钟后?|(\d+)小时后?)(.*?)(做|开会|完成|提交)",
        "intent": "add_reminder",
        "confidence": 0.85,
        "extract_params": "llm",  # 需要 LLM 提取结构化参数
    },
    {
        "pattern": r"^(TODO|待办|任务|记得)[:：\s]*(.+)",
        "intent": "add_todo",
        "confidence": 0.90,
        "extract_params": lambda m: {"title": m.group(2)}
    },
    {
        "pattern": r"^(搜索|查找|搜索一下|帮我搜)[:：\s]*(.+)",
        "intent": "search",
        "confidence": 0.90,
        "extract_params": lambda m: {"query": m.group(2)}
    },
    # ... 更多规则
]
```

**LLM 分类 Prompt**：

```
System: 你是一个桌面助手，负责判断用户想要执行什么操作。
用户通过快捷键或剪贴板输入了一段内容。请输出 JSON 格式的判断结果。

Available intents: add_todo, add_reminder, open_website, search, play_music, 
                    open_app, file_operation, none

Input: "{user_input}"
Output (JSON only):
{
    "intent": "add_todo",
    "confidence": 0.92,
    "params": {
        "title": "完成周报",
        "due_date": "2026-06-25",
        "priority": "medium"
    },
    "needs_confirmation": false,
    "reasoning": "用户明确提到了待办事项"
}
```

### 6.2 任务规划器 (Task Planner)

对于大多数场景，意图识别后直接执行工具即可。但为将来扩展考虑，保留简单的规划能力：

```
简单任务 (单步): Intent → Tool.execute() → Result
  例: 打开网站 → webbrowser.open(url)

复合任务 (多步): Intent → Plan → Step1 → Step2 → ... → Result
  例: "帮我下载这个网页的图片" →
     Step1: 打开浏览器访问 URL
     Step2: 截图或解析页面
     Step3: 下载图片到指定目录

MVP 阶段只实现单步任务。
复合任务作为 V2 功能保留架构扩展点。
```

### 6.3 工具调度器 (Tool Dispatcher)

```python
class ToolDispatcher:
    """工具调度器 - 负责工具注册、查找和执行"""
    
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool) -> None:
        """注册工具"""
    
    def dispatch(self, intent: Intent) -> ToolResult:
        """根据意图调度工具执行"""
    
    def list_tools(self) -> list[ToolMeta]:
        """列出所有已注册工具"""
    
    def get_tool_schema(self, name: str) -> dict:
        """获取工具的 JSON Schema (用于 LLM Function Calling)"""
```

### 6.4 权限管理器 (Permission Manager)

```
权限级别:
  Level 0 - SAFE:   不需要确认 (如: 查看 TODO 列表、显示时间)
  Level 1 - NOTIFY: 气泡通知 (如: 添加 TODO、打开网页)
  Level 2 - CONFIRM: 弹窗确认 (如: 删除文件、修改系统设置)
  Level 3 - BLOCK:   默认禁止 (如: 执行任意命令)

用户可自定义每个工具的权限级别。
同一工具不同操作可有不同级别（如：查看 TODO = SAFE, 删除 TODO = CONFIRM）
```

---

## 7. 工具系统

### 7.1 工具基类设计

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from enum import Enum

class PermissionLevel(Enum):
    SAFE = 0
    NOTIFY = 1
    CONFIRM = 2
    BLOCK = 3

@dataclass
class ToolMeta:
    """工具元数据"""
    name: str                          # 唯一标识, e.g. "todo_manager"
    display_name: str                  # 显示名称, e.g. "📋 待办管理"
    description: str                   # 功能描述
    version: str = "1.0.0"
    author: str = ""
    icon: str = "📋"                   # emoji 或图标路径
    permission: PermissionLevel = PermissionLevel.NOTIFY

@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    message: str                       # 气泡显示的消息
    data: Any = None                   # 结构化返回数据
    error: str | None = None
    pet_reaction: str = "happy"        # pet reaction: happy/sad/working

class BaseTool(ABC):
    """工具基类 - 所有工具必须继承此类"""
    
    @abstractmethod
    def meta(self) -> ToolMeta:
        """返回工具元数据"""
        ...
    
    @abstractmethod
    def schema(self) -> dict:
        """返回工具的 JSON Schema (用于 LLM Function Calling)"""
        ...
    
    @abstractmethod
    async def execute(self, params: dict) -> ToolResult:
        """执行工具"""
        ...
    
    def can_handle(self, intent: str, params: dict) -> bool:
        """判断此工具是否能处理该意图 (可选覆盖)"""
        return False
```

### 7.2 MVP 内置工具

#### Tool 1: TODO Manager `todo_manager`

```
功能:
  - 添加待办 (支持优先级、截止日期)
  - 查看待办列表 (今日/全部)
  - 完成待办
  - 删除待办

触发:
  - Ctrl+Shift+T: 添加 (从选中文字或剪贴板)
  - 点击桌宠菜单 → 📋 待办 → 查看列表

存储: SQLite 表 todos
  - id, title, description, priority, due_date, status, created_at, completed_at
```

#### Tool 2: Music Controller `music_controller`

```
功能:
  - 打开默认音乐播放器 (检测系统中已安装的)
  - 播放/暂停
  - 下一首/上一首
  - 音量调节

触发:
  - Ctrl+Shift+M: 打开/控制音乐

实现:
  - Windows: pyautogui 模拟媒体键 (play/pause/next/prev/vol)
  - 或通过 pygetwindow 激活特定音乐软件窗口
  - 支持的播放器: Spotify, Netease CloudMusic, QQ Music, Foobar2000 等
```

#### Tool 3: Browser Opener `browser_opener`

```
功能:
  - 打开 URL
  - 搜索关键词
  - 打开常用网站 (可配置)

触发:
  - Ctrl+Shift+W: 打开剪贴板中的 URL / 弹出输入框
  - Ctrl+Shift+S: 搜索

实现:
  - Python webbrowser 标准库
  - 检测默认浏览器
  - 支持搜索引擎配置 (Google/Bing/Baidu)
```

#### Tool 4: Quick Reminder `quick_reminder`

```
功能:
  - 快速设置定时提醒
  - 支持自然语言时间: "3分钟后" "下午2点" "明天9点"

触发:
  - Ctrl+Shift+R: 设置提醒
  - 点击桌宠菜单 → ⏰ 提醒

实现:
  - 使用 schedule 库或 threading.Timer
  - 时间到 → 桌宠弹气泡 + 系统通知
```

#### Tool 5: App Launcher `app_launcher`

```
功能:
  - 快速启动电脑上的应用程序
  - 搜索并打开文件

触发:
  - Ctrl+Shift+A → 输入应用名 → 启动
```

#### Tool 6: Clipboard Processor `clipboard_processor`

```
功能:
  - 处理剪贴板内容
  - URL 提取 → 可选打开
  - 电话号码 → 可选拨打 (通过 VoIP 或手机联动)
  - 文本摘要 → 可选复制摘要
  - 翻译 → 可选复制翻译结果

触发:
  - 自动检测 (可选开启)
  - 快捷键手动触发
```

### 7.3 工具扩展机制

添加新工具的步骤：

```python
# 1. 创建工具文件 tools/my_tool.py
from core.tool_base import BaseTool, ToolMeta, ToolResult, PermissionLevel

class MyTool(BaseTool):
    def meta(self) -> ToolMeta:
        return ToolMeta(
            name="my_tool",
            display_name="🔧 我的工具",
            description="这是一个自定义工具",
            permission=PermissionLevel.NOTIFY,
        )
    
    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "my_tool",
                "description": "工具描述",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "参数1"}
                    },
                    "required": ["param1"]
                }
            }
        }
    
    async def execute(self, params: dict) -> ToolResult:
        # 执行逻辑
        return ToolResult(success=True, message="执行成功！")

# 2. 注册工具 (在 tools/__init__.py 中)
from tools.my_tool import MyTool
TOOL_REGISTRY.append(MyTool())
```

---

## 8. 记忆与存储

### 8.1 数据分层

```
Layer 1: 业务数据 (SQLite)
  ├── todos           # 待办事项
  ├── reminders       # 提醒记录
  ├── tool_history    # 工具执行历史
  └── pet_stats       # 宠物状态统计

Layer 2: 配置数据 (JSON/YAML)
  ├── settings.json   # 用户设置
  │   ├── hotkeys     # 快捷键配置
  │   ├── tools       # 工具开关/配置
  │   ├── llm         # LLM 配置
  │   └── pet         # 宠物外观/行为配置
  └── pet_state.json  # 宠物运行时状态 (位置、心情等)

Layer 3: 缓存 (临时文件)
  └── .cache/         # 精灵图缓存、LLM 响应缓存等
```

### 8.2 SQLite 数据库设计

```sql
-- 待办事项
CREATE TABLE todos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    priority    INTEGER DEFAULT 0,     -- 0=低, 1=中, 2=高
    status      TEXT DEFAULT 'pending', -- pending/done/deleted
    due_date    TEXT,                   -- ISO 8601
    source      TEXT,                   -- 来源: clipboard/hotkey/manual
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    tags        TEXT DEFAULT '[]'       -- JSON array
);

-- 提醒
CREATE TABLE reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    trigger_at  TEXT NOT NULL,          -- ISO 8601
    status      TEXT DEFAULT 'pending', -- pending/triggered/dismissed
    repeat_rule TEXT,                   -- cron-like or null
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 工具执行历史
CREATE TABLE tool_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name   TEXT NOT NULL,
    intent      TEXT,
    params      TEXT,                   -- JSON
    success     INTEGER,
    message     TEXT,
    executed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 宠物状态统计
CREATE TABLE pet_stats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_type   TEXT NOT NULL,          -- 'task_completed', 'music_played', etc.
    value       INTEGER DEFAULT 1,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 8.3 配置文件设计

```json
// settings.json
{
  "hotkeys": {
    "add_todo": "ctrl+shift+t",
    "music_control": "ctrl+shift+m",
    "open_website": "ctrl+shift+w",
    "quick_search": "ctrl+shift+s",
    "quick_reminder": "ctrl+shift+r",
    "general_agent": "ctrl+shift+a",
    "toggle_pet": "ctrl+shift+p"
  },
  "llm": {
    "provider": "ollama",         // ollama | anthropic | openai | custom
    "model": "llama3.2:3b",       // or claude-haiku-4-5, gpt-4o-mini
    "api_base": "http://localhost:11434/v1",
    "api_key": "",
    "enabled": true,
    "max_tokens": 256,
    "temperature": 0.1
  },
  "tools": {
    "todo_manager": {"enabled": true},
    "music_controller": {"enabled": true, "preferred_app": "spotify"},
    "browser_opener": {"enabled": true, "default_search_engine": "google"},
    "quick_reminder": {"enabled": true},
    "app_launcher": {"enabled": true},
    "clipboard_processor": {"enabled": false}  // 默认关闭
  },
  "pet": {
    "name": "小樱",
    "skin": "default",
    "size": 1.0,                    // 缩放比例
    "opacity": 1.0,                 // 不透明度
    "auto_walk": true,              // 自动走动
    "auto_sleep": true,             // 自动睡觉 (闲置 > 5min)
    "sleep_timeout_seconds": 300,
    "reaction_speed": "normal",     // slow/normal/fast
    "bubble_duration_seconds": 3,
    "start_position": "bottom_right" // top_left/top_right/bottom_left/bottom_right/last
  },
  "privacy": {
    "clipboard_monitor": false,     // 默认关闭
    "history_retention_days": 30,
    "telemetry": false
  }
}
```

---

## 9. 技术选型

### 9.1 最终选择：Python + PySide6

| 维度 | 选择 | 理由 |
|------|------|------|
| **语言** | Python 3.11+ | 桌面自动化生态最丰富 (pyautogui, pynput, pyperclip)；AI/LLM 库完善；开发效率高 |
| **GUI 框架** | PySide6 (Qt 6) | 原生 Windows 透明窗口支持；GPU 渲染 (QOpenGLWidget)；成熟稳定；DyberPet & Sakura 已验证可行 |
| **全局热键** | pynput | 纯 Python 实现，跨平台，支持组合键 |
| **剪贴板** | pyperclip + win32clipboard | pyperclip 跨平台，win32clipboard 提供高级功能 |
| **桌面自动化** | pyautogui | 模拟键盘/鼠标/截图；跨平台 |
| **LLM 调用** | httpx + openai SDK | httpx 用于通用 HTTP 调用 (Ollama)；openai SDK 兼容多提供商 |
| **数据库** | sqlite3 (内置) + aiosqlite | 零配置、零依赖、Python 内置 |
| **配置管理** | Pydantic + JSON | 类型安全、自动校验 |
| **异步支持** | asyncio + qasync | 不阻塞 UI 线程的前提下执行 API 调用 |
| **打包分发** | Nuitka 或 PyInstaller | 打包为独立 exe |

### 9.2 为什么不用 Electron？

- 内存占用大（>200MB baseline vs Python ~50MB）
- 桌面自动化生态不如 Python
- 透明窗口 + 精灵动画在 Python/Qt 中同样可以实现
- 本项目的核心竞争力在 Agent 能力，Python 是最佳选择

### 9.3 动画渲染方案

```
方案: QOpenGLWidget + 精灵图纹理
  - 精灵图加载为 OpenGL 纹理
  - 每帧切换纹理坐标 (UV offset)
  - GPU 渲染，CPU 占用极低
  - 平滑的帧间过渡

备选方案: QLabel + QMovie (GIF/APNG)
  - 更简单的实现
  - 适合 MVP 快速验证
  - 缺点是难以做复杂的动画混合

推荐: MVP 先用 QLabel + 序列帧 QTimer，后期优化为 OpenGL
```

### 9.4 依赖清单

```txt
# requirements.txt

# GUI 核心
PySide6>=6.7.0

# 异步支持
qasync>=0.27.0

# 输入监听
pynput>=1.7.6

# 剪贴板
pyperclip>=1.8.2
pywin32>=306              # Windows 特定功能

# 桌面自动化
pyautogui>=0.9.54

# LLM API
httpx>=0.27.0
openai>=1.30.0            # 兼容 OpenAI / Ollama / 等多种后端

# 数据
aiosqlite>=0.20.0
pydantic>=2.7.0

# 工具库
schedule>=1.2.0           # 定时任务 (提醒功能)

# 系统托盘
pystray>=0.19.0

# 打包
pyinstaller>=6.0.0        # 开发依赖
```

---

## 10. 项目结构

```
HaChiCat/
├── Pet-design.md                  # 本设计文档
├── README.md                      # 项目说明
├── requirements.txt               # 依赖清单
├── pyproject.toml                 # 项目配置
├── run.py                         # 入口文件
│
├── src/                           # 主代码
│   ├── __init__.py
│   ├── main.py                    # 应用启动、初始化
│   │
│   ├── pet/                       # 桌宠视觉层
│   │   ├── __init__.py
│   │   ├── pet_window.py          # 主窗口 (透明、置顶、无边框)
│   │   ├── pet_widget.py          # 宠物渲染 Widget
│   │   ├── animator.py            # 精灵图动画引擎
│   │   ├── state_machine.py       # 宠物状态机
│   │   ├── physics.py             # 物理引擎 (重力、拖拽、碰撞)
│   │   ├── bubble.py              # 气泡提示 UI
│   │   ├── menu.py                # 快捷操作菜单
│   │   └── tray.py                # 系统托盘
│   │
│   ├── input/                     # 输入层
│   │   ├── __init__.py
│   │   ├── hotkey_manager.py      # 全局热键注册/管理
│   │   ├── click_handler.py       # 点击事件处理
│   │   └── clipboard_monitor.py   # 剪贴板变化检测
│   │
│   ├── agent/                     # Agent 核心
│   │   ├── __init__.py
│   │   ├── intent_classifier.py   # 意图分类 (规则 + LLM)
│   │   ├── rule_engine.py         # 规则匹配引擎
│   │   ├── llm_client.py          # LLM API 客户端封装
│   │   ├── tool_dispatcher.py     # 工具调度器
│   │   ├── permission_manager.py  # 权限管理
│   │   └── task_planner.py        # 任务规划器 (V2)
│   │
│   ├── tools/                     # 工具系统
│   │   ├── __init__.py            # 工具注册表
│   │   ├── base_tool.py           # 工具基类
│   │   ├── todo_manager.py        # 待办管理
│   │   ├── music_controller.py    # 音乐控制
│   │   ├── browser_opener.py      # 浏览器操作
│   │   ├── quick_reminder.py      # 快速提醒
│   │   ├── app_launcher.py        # 应用启动器
│   │   └── clipboard_processor.py # 剪贴板处理
│   │
│   ├── memory/                    # 记忆/存储层
│   │   ├── __init__.py
│   │   ├── database.py            # SQLite 连接管理
│   │   ├── config.py              # 配置读写
│   │   └── models.py              # 数据模型 (Pydantic)
│   │
│   └── utils/                     # 工具函数
│       ├── __init__.py
│       ├── logger.py              # 日志配置
│       └── helpers.py             # 通用辅助函数
│
├── assets/                        # 资源文件
│   ├── sprites/                   # 精灵图
│   │   ├── default/               # 默认宠物
│   │   │   ├── sprite_sheet.png
│   │   │   ├── sprite_config.json # 帧尺寸、帧数等配置
│   │   │   └── preview.png
│   │   └── custom/                # 自定义宠物 (用户可添加)
│   │       └── .gitkeep
│   ├── sounds/                    # 音效 (可选)
│   │   ├── click.wav
│   │   ├── success.wav
│   │   └── error.wav
│   └── icons/                     # 图标
│       └── app_icon.ico
│
├── config/                        # 默认配置
│   ├── default_settings.json
│   └── intent_rules.yaml          # 意图规则配置
│
├── data/                          # 用户数据 (运行时生成, gitignore)
│   ├── settings.json
│   ├── pet_state.json
│   └── hachicat.db
│
├── docs/                          # 文档
│   ├── architecture.md
│   ├── tool-development.md        # 工具开发指南
│   └── changelog.md
│
└── tests/                         # 测试
    ├── __init__.py
    ├── test_intent_classifier.py
    ├── test_tool_dispatcher.py
    ├── test_todo_manager.py
    └── test_config.py
```

---

## 11. 参考实现分析

### 11.1 各项目值得借鉴的点

| 项目 | 最值得借鉴 | 不适合我们的 |
|------|-----------|-------------|
| **Sakura** (Rvosy) | 工具注册机制、MCP 扩展、屏幕感知的 modular 设计 | 对话为主、角色复杂度过高 |
| **DyberPet** (ChaozhongLiu) | PySide6 桌宠渲染、动画系统、物品/商店系统 | 养育系统过重、LLM 未成熟 |
| **OpenPet** (X-T-E-R) | 三种控制协议 (CLI/MCP/HTTP)、宠物导入标准 | 纯渲染运行时，无 Agent 能力 |
| **KillClawd** (ninjahawk) | 轻量、有性格但不多话、本地 LLM 运行 | 代码组织较随意、无工具系统 |
| **Clawd on Desk** (rullerzhou-afk) | 事件驱动状态机、权限气泡 UI、多会话管理 | 聚焦 Coding Agent，与我们的场景不同 |
| **Agentic-Desktop-Pet** (jihe520) | 知识图谱记忆、情感引擎、RPG 系统 | 整体过于复杂，MVP 不需要 |

### 11.2 架构决策借鉴表

| 设计决策 | 我们的选择 | 参考来源 | 理由 |
|----------|-----------|----------|------|
| 透明窗口实现 | Qt WA_TranslucentBackground | DyberPet | Windows 原生支持最好 |
| 动画方案 | 精灵图 + 状态机 | DyberPet + KillClawd | 简单可控，无需 Live2D SDK |
| 工具扩展机制 | 基类继承 + 注册表 | Sakura | 最 Pythonic 的方式 |
| LLM 集成 | 可选、可替换、两级分类 | KillClawd (Ollama 本地) | 满足隐私和离线需求 |
| 配置格式 | JSON + Pydantic 校验 | 综合 | 用户可手动编辑 |
| 进程模型 | 单进程多线程 | 综合 | 对 MVP 最实用 |
| 权限控制 | 分级权限 + 用户可配 | Sakura + Clawd | 安全性 |
| 剪贴板监听 | 默认关闭、可选开启 | — | 隐私优先 |

---

## 12. 开发路线图

### Phase 0: 基础框架搭建 (预计 1-2 周)

```
目标: 让一个静态精灵图显示在桌面上

□ 项目骨架搭建 (目录结构、依赖安装)
□ PetWindow: 透明置顶无边框窗口
□ PetWidget: 精灵图加载和渲染 (Static 模式)
□ SystemTray: 系统托盘图标和退出菜单
□ 配置文件加载 (Pydantic)
□ 日志系统

交付物: 一只可以显示在桌面上的静态宠物，右键托盘可退出
```

### Phase 1: 桌宠基础动画 (预计 2-3 周)

```
目标: 宠物活起来，有基本行为

□ Animator: 精灵图动画引擎 (帧切换、循环/单次)
□ StateMachine: 状态机 (IDLE/WALKING/SLEEPING/DRAGGING)
□ Physics: 基础物理 (拖拽、边界检测)
□ Bubble: 气泡提示 UI
□ 默认精灵图素材 (至少 IDLE/WALKING/SLEEPING 三状态)
□ 宠物位置记忆 (启动时恢复上次位置)

交付物: 一只会动、可拖拽、有情绪的桌宠
```

### Phase 2: 输入系统 (预计 1-2 周)

```
目标: 用户可以通过快捷键和点击与宠物交互

□ HotkeyManager: 全局热键注册 (pynput)
□ ClickHandler: 点击宠物弹出快捷菜单
□ ClipboardMonitor: 剪贴板变化检测 (默认关闭)
□ 快捷键配置读写

交付物: Ctrl+Shift+热键 触发动作，点击宠物弹出菜单
```

### Phase 3: Agent 核心 (预计 2-3 周)

```
目标: 桌宠能理解用户意图并执行任务

□ IntentClassifier: 规则匹配引擎
□ RuleEngine: YAML 配置的意图规则
□ LLMClient: LLM API 封装 (Ollama + Claude API)
□ ToolDispatcher: 工具注册和调度
□ PermissionManager: 权限分级管理

交付物: 输入文字 → 意图识别 → 工具调度 (规则模式可用)
```

### Phase 4: 首批工具 (预计 2-3 周)

```
目标: 实现核心工具集

□ BaseTool 基类完善
□ TODO Manager (添加/查看/完成/删除)
□ Browser Opener (打开 URL / 搜索)
□ Quick Reminder (定时提醒)
□ Music Controller (媒体键控制)
□ 工具注册表

交付物: MVP 可用 — 通过热键管理待办、打开网页、设置提醒、控制音乐
```

### Phase 5: 打磨与发布 (预计 2-3 周)

```
目标: 完善体验，打包发布

□ LLM 意图分类集成 (提升模糊意图识别率)
□ 宠物情绪对任务结果的反应动画
□ 气泡 UI 完善 (确认/取消按钮)
□ 设置界面 (简单配置页)
□ PyInstaller 打包 Windows exe
□ 使用文档

交付物: 可分发使用的 v1.0.0
```

### Phase 6+: 后续迭代方向

```
□ 多语言支持 (i18n)
□ 更多皮肤/主题
□ 插件市场 (用户贡献工具)
□ 复合任务支持 (多步规划)
□ 语音输入 (Whisper STT)
□ Live2D 模型支持 (可选)
□ macOS/Linux 跨平台支持
□ 移动端伴侣 (手机通知同步)
□ 社区分享的意图规则和工具
```

---

## 附录 A: 与聊天机器人的关键差异

| 维度 | 聊天机器人桌宠 | Acc ompet |
|------|---------------|-----------|
| 主动性 | 经常主动聊天 | 默认安静，仅气泡提示 |
| 输入方式 | 文字对话 | 快捷键 / 点击 / 剪贴板 |
| 交互模式 | 持续对话 | 单次任务 → 结果反馈 |
| UI 重心 | 对话框 | 宠物动画 + 气泡 |
| LLM 使用 | 每轮对话都调用 | 仅在意图识别需要时调用 |
| 记忆用途 | 对话历史 | 业务数据 (TODO/提醒/偏好) |
| 用户体验 | "和助手聊天" | "宠物帮我做事" |

## 附录 B: 命名含义

**HaChiCat** = Accomplice (伙伴/同谋) + Pet (宠物)
暗示这位桌面伙伴既可爱又能干，是用户数字生活的小帮手。

---

## 附录 C: 宠物动画系统方案调研

### C.1 当前状态

- 现有素材：`img/catpet.png` (1024×1024, ~1.6MB)
- 现有素材：`img/oUB9AUQTBiCAHZiAE0iB6HvtIAoCQglKgBce0Y.gif` (~4.8MB, 可能是动画GIF)
- 当前实现：静态单张精灵图，无帧动画

### C.2 四种主流桌宠动画方案

#### 方案 A: 序列帧精灵图 (DyberPet / OpenPet)
```
catpet_spritesheet.png (如 1024×1024, 4列×4行 = 16帧, 256×256/帧)
+ sprite_config.json 定义每行动画
```
- ✅ 全部动画在一张图上，加载一次，GPU纹理切换零开销
- ✅ 社区标准格式（Codex Pets 兼容）
- ✅ 每帧时长可独立配置
- ❌ 需要美术资源或工具切图
- 实现难度：⭐ 低（当前 FrameAnimator 已支持）

#### 方案 B: 单个 GIF 文件 (KillClawd)
```
每个状态一个 .gif 文件 (idle.gif, walk.gif, sleep.gif...)
QMovie 驱动播放
```
- ✅ 零配置，拖动即用
- ✅ QMovie 自动循环
- ❌ GIF 不支持透明度半像素（边缘锯齿）
- ❌ 无法精确控制帧时长
- ❌ 大 GIF 内存占用高
- 实现难度：⭐⭐ 中（需切换 QMovie 状态）

#### 方案 C: 多张独立 PNG (原始 Shimeji)
```
每个动作帧一个 PNG: idle_0.png, idle_1.png, walk_0.png...
```
- ✅ 最灵活，每帧独立
- ❌ 文件数量多，加载慢
- ❌ 内存占用最高
- 实现难度：⭐⭐ 中

#### 方案 D: Live2D / Spine 骨骼动画 (Sakura / open-yachiyo)
```
.model3.json + 纹理图集
Cubism SDK 驱动
```
- ✅ 最流畅，可做丰富表情/物理
- ✅ 业界最高品质
- ❌ SDK 复杂，打包体积大
- ❌ 需要专门工具制作模型
- ❌ 过度设计（我们的定位不是聊天机器人）
- 实现难度：⭐⭐⭐⭐⭐ 极高

### C.3 推荐方案：方案 A（序列帧精灵图）

理由：
1. 我们已有 FrameAnimator 和 sprite_config.json，只需换图和配置
2. Codex Pets 社区有大量现成精灵图可直接下载使用
3. 兼容 OpenPet 的 `.pet` 导入标准
4. GPU 渲染，缩放流畅，内存占用低

### C.4 实施计划

#### Step 1: 获取/制作精灵图素材
- 从 Codex Pets 社区下载现成宠物包
  - [Petdex](https://petdex.pages.dev/)
  - [Codex Pets](https://codex-pets.net/)
- 或者用现有 GIF 提取帧拼接成精灵图
- 至少需要：idle (4帧) + walk (4帧) + drag (2帧) + happy (4帧)

#### Step 2: 配置动画
- 更新 sprite_config.json：定义每行的帧数、时长、循环模式
- 测试动画播放流畅度（目标 10+ fps）

#### Step 3: 交互动画
- 点击宠物 → 播放短动画 (弹跳/表情变化)
- 任务成功 → 开心动画
- 任务失败 → 沮丧动画
- 拖拽中 → 拎起动画
- 闲置 → 呼吸/眨眼动画

#### Step 4: GIF 导入支持（可选）
- 用户可拖入 GIF 自动转换为精灵图
- 工具脚本：`python tools/gif2sprites.py input.gif`

#### Step 5: 宠物商店集成（远期）
- 集成 Petdex API 浏览和下载宠物
- 一键切换皮肤

### C.5 参考项目

| 项目 | 动画方案 | 关键文件 |
|------|---------|---------|
| DyberPet | PNG序列帧 | `res/role/PETNAME/action/*.png` + `act_conf.json` |
| OpenPet | 精灵图WebP | `spritesheet.webp` + `pet.json` (1536×1872, 8×9格) |
| KillClawd | GIF 文件 | `assets/*.gif` (17个独立GIF) |
| Clawd on Desk | PNG精灵图 | Codex Pet 标准格式 |
| Sakura | Live2D | `.model3.json` + Cubism SDK |

