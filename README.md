# Dot Service

Dot Service 是一个面向 **MindReset Dot. Quote/0** 墨水屏设备的自托管控制服务，提供浏览器界面和 REST API，用来查看设备状态、发送文字和上传图片。

![界面预览](docs/asset/img.png)

## 功能

- Web 控制台：查看设备状态、发送文字/图片、管理配置
- REST API：基于 FastAPI，自动生成 Swagger 文档
- 文字发送：`POST /text`
- 文字转图片：`POST /text-to-image`，适合自定义字号和版式
- 图片发送：`POST /image` / `POST /image/upload`
- 上传图片时会自动缩放到 `296x152`
- 飞书消息通知桥：通过 `lark-cli` 定时轮询飞书群聊/私聊，按关键词或 @ 过滤后推送到 Dot

## 快速开始

### 1. 安装

```bash
git clone git@github.com:Ebispongebob/dot-service.git
cd dot-service
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. 配置

在 `.env` 中至少填写：

```ini
DOT_API_KEY=dot_app_xxxxxxxxxxxx
DOT_DEFAULT_DEVICE_ID=
DOT_API_BASE_URL=https://dot.mindreset.tech
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8000
```

也可以在 `/ui/settings` 页面保存配置。页面保存的数据会写入仓库根目录的 `ui_settings.json`，不要提交到 Git。

### 飞书通知桥配置（可选）
1. 安装并初始化 `lark-cli`。
2. 按需授权消息读取权限，例如用户身份：

```bash
lark-cli auth login --scope "im:message:readonly im:chat:read"
```

3. 在 `.env` 中启用并配置消息来源：

```ini
LARK_NOTIFY_ENABLED=true
LARK_NOTIFY_IDENTITY=user
LARK_NOTIFY_MONITOR_ALL=true
# 监听全部群聊时不需要填 LARK_NOTIFY_CHAT_IDS
# 也可以额外指定：LARK_NOTIFY_CHAT_IDS=oc_xxx
LARK_NOTIFY_KEYWORDS=@我,紧急,P0
```

或者直接在 Web UI (`/ui/lark`) 页面操作：开启「监听全部群聊」开关即可。

启动服务后可通过以下接口检查和调试：

- `GET /lark/notify/status`：查看轮询桥状态
- `POST /lark/notify/poll?notify=false`：手动轮询但不推送
- `POST /lark/notify/test`：发送一条测试 Dot 通知

### 3. 启动

```bash
python run.py
# 或
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

启动后访问：

- 控制台：`http://localhost:8000/`
- API 文档：`http://localhost:8000/docs`

## 常用接口

- `GET /health`
- `GET /devices`
- `GET /devices/{device_id}/status`
- `GET /lark/notify/status`
- `POST /lark/notify/poll`
- `POST /lark/notify/test`
- `POST /text`
- `POST /text-to-image`
- `POST /image`
- `POST /image/upload`

## 说明

- `python run.py` 是本地开发入口，默认启用热重载
- 设备 ID 优先级：请求参数 `device_id` > `ui_settings.json` > `.env` 中的 `DOT_DEFAULT_DEVICE_ID`
- `POST /text` 使用设备/云端的文字排版能力
- `POST /text-to-image` 会先在服务端把文字渲染成图片，再通过图片接口发送
- 修改 `.env` 后需要重启服务，运行中的进程不会自动重新读取配置
- 飞书通知桥依赖本机 `lark-cli`；使用 `bot` 身份时机器人需要在目标群内，使用 `user` 身份时需要用户授权

## 代码结构

- `app/main.py`：FastAPI 应用、UI 路由、API 路由
- `app/dot_client.py`：Dot Cloud API 封装
- `app/image_utils.py`：图片缩放、Base64 转换、文字渲染
- `app/lark_bridge.py`：飞书消息轮询和 Dot 通知桥
- `run.py`：本地开发启动入口

## 贡献

欢迎提交 Issue 或 Pull Request。
