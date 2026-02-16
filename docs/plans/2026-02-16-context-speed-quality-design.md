# 设计文档：修复文字覆盖 + 上下文续写 + 提速提质

日期：2026-02-16

## 问题描述

1. **文字被覆盖**：在输入框中已有文字的情况下，按 Alt+Space 录音再停止后，原有文字被新转录的文字完全替换。
2. **缺乏上下文理解**：在已有文字后面续写时，LLM 不知道前面写了什么，无法生成连贯的续写内容。
3. **速度和质量**：当前管线耗时 5-15 秒，且 Qwen2.5-7B 模型的改写质量不够理想。

---

## 修复 1：文字被覆盖 Bug

### 根因分析

录音开始时 `ShowWaveformIndicator()` 创建的 GUI 窗口抢走了目标窗口的焦点。录音结束后 `InsertText()` 调用 `WinActivate()` 重新激活目标窗口，但很多 Windows 控件在重新获得焦点时会自动全选文字。此时 `Ctrl+V` 粘贴就把全部内容替换了。

### 解决方案

**AHK 端改动（`desktop/hotkey_agent.ahk`）：**

1. **波形窗口不抢焦点**：创建波形 GUI 时添加 `+E0x08000000`（WS_EX_NOACTIVATE）扩展样式，确保波形窗口永远不会从目标窗口抢走焦点。

2. **粘贴前恢复光标**：在 `InsertText()` 中，`WinActivate` 之后、`Ctrl+V` 之前，发送 `{End}` 键将光标移到末尾并取消任何选中状态。这是一个保险措施，防止因焦点切换导致的意外全选。

**涉及文件**：`desktop/hotkey_agent.ahk`
- `ShowWaveformIndicator()` 函数：添加窗口样式
- `InsertText()` 函数：粘贴前加 `Send("{End}")`

---

## 修复 2：上下文续写

### 当前行为

- `StartRecordingSession()` 调用 `GetSelectedTextSafe()` 获取选中的文字
- 如果没有选中任何文字，`selected_text` 为空
- 后端 `build_prompt()` 只在有 `selected_text` 时才传入上下文
- 结果：续写模式下 LLM 完全不知道前面写了什么

### 解决方案

**AHK 端改动（`desktop/hotkey_agent.ahk`）：**

在 `StartRecordingSession()` 中，增加获取输入框全部文字的逻辑：

```
GetFullTextSafe() {
    ; 保存剪贴板
    clipSaved := ClipboardAll()
    fullText := ""
    try {
        A_Clipboard := ""
        Send("^a")      ; 全选
        Sleep(50)
        Send("^c")      ; 复制
        if (ClipWait(0.3))
            fullText := A_Clipboard
        Send("{End}")    ; 取消选中，光标移到末尾
    } finally {
        A_Clipboard := clipSaved
    }
    return fullText
}
```

修改 `StartRecordingSession()`：
- 先调用 `GetSelectedTextSafe()` 获取选中文字
- 如果没有选中文字，再调用 `GetFullTextSafe()` 获取全部文字
- 将 `selected_text` 和 `existing_text` 分别传给 API

**API 改动：**

1. **`schemas.py`** — `StartSessionRequest` 增加 `existing_text` 字段：
   ```python
   class StartSessionRequest(BaseModel):
       selected_text: str | None = None
       existing_text: str | None = None
   ```

2. **`session_store.py`** — `Session` 增加 `existing_text` 字段：
   ```python
   @dataclass
   class Session:
       session_id: str
       selected_text: str | None = None
       existing_text: str | None = None
   ```

3. **`main.py`** — `start_record()` 传递 `existing_text`：
   ```python
   session_id = store.create(
       selected_text=payload.selected_text,
       existing_text=payload.existing_text,
   )
   ```

4. **`rewrite.py`** — `build_prompt()` 增加三种模式：

   - **选中文字模式**（有 `selected_text`）：保持现有逻辑，LLM 根据语音指令改写选中内容
   - **续写模式**（有 `existing_text`，无 `selected_text`）：新增模式，prompt 告诉 LLM 用户已有的文字，要求生成自然衔接的续写
   - **独立模式**（都没有）：保持现有逻辑，LLM 独立整理语音内容

   续写模式的 prompt 结构：
   ```
   [System] You are a language organizer...

   The user has already written the following text:
   ---
   {existing_text}
   ---

   The user then spoke the following to continue:
   {voice_text}

   Requirements:
   - Output ONLY the new continuation text (do NOT repeat the existing text)
   - The continuation must flow naturally from the existing text in style and tone
   - Remove filler words and organize the spoken content
   - Keep the same language as the input
   - Do not add facts
   ```

**关键设计决策**：
- 续写模式下 LLM **只输出新增部分**，不重复已有文字。这样 AHK 端直接在光标位置粘贴即可。
- `existing_text` 做截断保护：如果超过 2000 字符，只保留最后 2000 字符（取最近的上下文，避免 token 浪费）。

---

## 修复 3：提速 + 提质

### 当前性能

| 步骤 | 模型 | 耗时 |
|------|------|------|
| ASR | SenseVoiceSmall via SiliconFlow | 2-8s |
| LLM 改写 | Qwen2.5-7B-Instruct via SiliconFlow | 2-5s |
| **总计** | | **~5-15s** |

### 改动方案

#### 3a. LLM 升级

将 LLM 从 `Qwen/Qwen2.5-7B-Instruct` 切换为 `deepseek-ai/DeepSeek-V3`。

**理由**：
- DeepSeek-V3 在中文理解和改写任务上质量远超 Qwen-7B
- MoE 架构使得推理速度与小模型相当
- SiliconFlow 上可直接使用，无需更换 API 提供商
- 价格合理（性价比高）

**改动点**：
- `config.py`：`siliconflow_model` 默认值改为 `"deepseek-ai/DeepSeek-V3"`

#### 3b. Prompt 优化

**使用 system/user 角色分离**：

当前实现把所有内容塞进一条 `user` 消息。改为：
- `system` 消息：放置角色定义和输出规则（固定不变）
- `user` 消息：放置具体的语音内容和上下文

**改动点**：
- `rewrite.py` — `build_prompt()` 返回值从单个字符串改为 `list[dict]`（messages 数组）
- `providers/siliconflow.py` — `rewrite_with_siliconflow()` 接收 messages 数组而不是单个 prompt
- `providers/ollama.py` — 同步修改

**简化后处理**：
- DeepSeek-V3 能力更强，可以在 prompt 中明确要求输出格式，减少 `postprocess_rewrite_output()` 中的强制格式化逻辑
- 保留基本的空白字符清理和 emoji 移除
- 去掉 `detect_semantic_blocks()` 的预处理（不再在 prompt 中传递语义块分析），让更强的模型自行理解结构

#### 3c. ASR 保持不变

SenseVoiceSmall 在中英文 ASR 上已经足够好，且速度较快。ASR 不是质量问题的主要来源，改写质量才是。

### 预期效果

| 步骤 | 模型 | 预计耗时 |
|------|------|----------|
| ASR | SenseVoiceSmall（不变） | 2-8s |
| LLM 改写 | DeepSeek-V3 | 1-3s |
| **总计** | | **~3-10s** |

质量方面：DeepSeek-V3 + 优化后的 prompt + 上下文感知，预计改写效果会有明显提升。

---

## 改动文件汇总

| 文件 | 改动内容 |
|------|----------|
| `desktop/hotkey_agent.ahk` | 波形窗口不抢焦点；新增 `GetFullTextSafe()`；`InsertText()` 粘贴前发 `{End}`；`StartRecordingSession()` 传递 `existing_text` |
| `service/src/.../schemas.py` | `StartSessionRequest` 增加 `existing_text` 字段 |
| `service/src/.../session_store.py` | `Session` 增加 `existing_text` 字段 |
| `service/src/.../main.py` | `start_record()` 和 `stop_record()` 传递 `existing_text` |
| `service/src/.../rewrite.py` | `build_prompt()` 支持三种模式 + 返回 messages 数组 + 简化后处理 |
| `service/src/.../config.py` | 默认模型改为 DeepSeek-V3 |
| `service/src/.../providers/siliconflow.py` | 支持 messages 数组 + system/user 分离 |
| `service/src/.../providers/ollama.py` | 同步修改 |
| `service/tests/` | 相应测试更新 |

---

## 不做的事情

- 不引入流式响应（Streaming）——当前场景需要完整文字后一次性粘贴
- 不换 ASR 模型——SenseVoiceSmall 已够用
- 不引入本地 ASR——增加部署复杂度，收益有限
- 不做缓存——语音输入每次都不同，缓存无意义
