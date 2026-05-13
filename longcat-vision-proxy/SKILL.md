---
name: longcat-vision-proxy
description: "本地代理转换层：让 LongCat-Flash-Omni-2603 通过标准 OpenAI 多模态格式支持图片识别"
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [longcat, vision, proxy, multimodal, auxiliary, china]
    related_skills: [hermes-agent]
---

# LongCat Vision Proxy

## Overview

LongCat-Flash-Omni-2603（美团出品）是一个 560B 参数的开源全模态模型，支持文本、图像、音频、视频理解和生成。但它使用**专有的消息格式**（`type: "input_image"`），与 Hermes Agent 的标准辅助视觉集成（`type: "image_url"`）不兼容。

本代理是一个 Python 标准库实现的中间层，跑在本地监听 `localhost:18765`，在标准格式和 LongCat Omni 格式之间做实时转换：

```
Hermes ──标准格式──→ localhost:18765 ──Omni格式──→ api.longcat.chat
                     (Python 代理)
```

## When to Use

**Use this when:**
- 你在中国大陆，需要免翻墙使用多模态视觉能力
- 你的 Hermes 辅助模型用不了图片识别
- 你想用 LongCat 每天 50 万免费 token 的 Omni 模型

**Don't use this when:**
- 你已经有支持标准 OpenAI 多模态格式的 API（如 GPT-4o）
- 你不需要图片识别，只用纯文本辅助模型
- 网络环境可以直接访问 OpenRouter / Google Gemini

## Setup

### 1. 代理脚本

脚本位置（二选一）：

- **工作目录：** `/mnt/c/Users/tdywh/Desktop/hermes/longcat_vision_proxy.py`
- **Skill 脚本：** `~/.hermes/skills/mlops/longcat-vision-proxy/scripts/longcat_vision_proxy.py`

不依赖任何第三方库，Python 标准库即可运行。

### 2. 启动代理

```bash
# 前台运行
python3 /mnt/c/Users/tdywh/Desktop/hermes/longcat_vision_proxy.py --port 18765

# 后台运行
nohup python3 /mnt/c/Users/tdywh/Desktop/hermes/longcat_vision_proxy.py \
  --port 18765 > /tmp/longcat_proxy.log 2>&1 &
```

启动后验证：
```bash
curl -s http://localhost:18765/health
# → {"status": "ok", "proxy": "longcat-vision"}
```

### 3. 配置 Hermes

```bash
hermes config set auxiliary.vision.provider custom
hermes config set auxiliary.vision.model LongCat-Flash-Omni-2603
hermes config set auxiliary.vision.base_url http://localhost:18765
```

### 4. 使用

`/reset` 启动新会话，然后用：

- `/image <文件路径>` — 发送本地图片
- `/paste` — 发送剪贴板截图

## How It Works

### 请求转换

代理收到 Hermes 发来的标准 OpenAI 请求：

```json
{
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "这是什么？"},
      {"type": "image_url", "image_url": {
        "url": "data:image/png;base64,iVBOR..."
      }}
    ]
  }]
}
```

转换为 LongCat Omni 格式：

```json
{
  "messages": [{
    "role": "user",
    "content": [
      {"type": "input_image", "input_image": {
        "type": "base64",
        "data": ["iVBOR..."]
      }},
      {"type": "text", "text": "这是什么？"}
    ]
  }]
}
```

### 响应清理

移除 Omni 专有字段（`session_id`, `lastOne`, `audio`, `delta`, `content`），返回标准格式响应。

## Configuration

### 代理参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--port` | 18765 | 监听端口 |
| 无 | — | API Key 硬编码在脚本 `LONGCAT_ENDPOINT` / `API_KEY` 中 |

### Hermes 配置

```yaml
# ~/.hermes/config.yaml
auxiliary:
  vision:
    provider: custom
    model: LongCat-Flash-Omni-2603
    base_url: http://localhost:18765
    api_key: ak_2LV4Sv0348dZ6vQ8363hE7EY0nU3I
    timeout: 120
```

## Pitfalls

### 1. base_url 路径错误
LongCat 的 OpenAI 兼容端点是 `https://api.longcat.chat/openai`，不是 `https://api.longcat.chat/v1`。后者返回 OpenResty 404 页面。

### 2. content 顺序 bug
LongCat Omni 处理 content 数组时，`input_image` **必须排在 `text` 前面**，否则模型认为图片是空白。代理已自动处理。

### 3. `session_id` 不可用
加上 `session_id` 参数会返回 400 Bad Request。代理已移除该字段。

### 4. 需先启动代理
代理没运行的话 Hermes 连不上 `localhost:18765`，图片识别会失败。

### 5. 需重启会话
`auxiliary.vision.*` 配置更改后必须 `/reset` 或重启 Hermes 才生效。

### 6. Hermes 发送标准格式
Hermes 的 `vision` 工具集始终使用标准 OpenAI 多模态格式（`type: "image_url"`），这是代理存在的根本原因。

## Verification

验证文本能力：
```bash
curl -s -X POST http://localhost:18765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"LongCat-Flash-Omni-2603","messages":[{"role":"user","content":"Say hi in Chinese"}],"max_tokens":30}'
# → 你好！
```

验证图片能力：
```bash
python3 -c "
import requests, json, base64
with open('test.png', 'rb') as f:
    b64 = base64.b64encode(f.read()).decode()
r = requests.post('http://localhost:18765/v1/chat/completions', json={
    'model': 'LongCat-Flash-Omni-2603',
    'messages': [{'role': 'user', 'content': [
        {'type': 'text', 'text': '描述这张图片'},
        {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{b64}'}}
    ]}],
    'max_tokens': 200
})
print(r.json()['choices'][0]['message']['content'])
"
```

## Files

| 文件 | 路径 |
|------|------|
| 代理脚本（主） | `/mnt/c/Users/tdywh/Desktop/hermes/longcat_vision_proxy.py` |
| 代理脚本（skill 副本） | `~/.hermes/skills/mlops/longcat-vision-proxy/scripts/longcat_vision_proxy.py` |
| Hermes 配置 | `~/.hermes/config.yaml` → `auxiliary.vision.*` |
