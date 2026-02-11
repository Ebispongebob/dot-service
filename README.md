# Dot Service

Dot Service 是一个专为 **MindReset Dot. Quote/0** 墨水屏设备设计的自托管 Web 控制服务。

它提供了一个现代化的 Web 界面和增强的 REST API，让你可以轻松管理设备状态、发送文字排版、上传图片（支持多种抖动算法），并无缝集成到你的自动化工作流中。

![Dashboard Preview](https://via.placeholder.com/800x400?text=Dot+Service+Dashboard+Preview)

## ✨ 功能特性

- **📱 现代化 Web 控制台**：响应式设计，适配桌面与移动端，支持深色/浅色模式切换（基于系统）。
- **📊 设备概览**：实时查看设备在线状态、电池电量、WiFi 信号、固件版本及当前屏幕画面预览。
- **📝 强大的文字推送**：
  - 支持标题、正文、署名自动排版。
  - **两种渲染模式**：使用设备内置排版 API，或服务器端渲染（Text-to-Image）以获得完全的字体控制。
- **🖼️ 智能图片处理**：
  - 自动将任意图片缩放/裁剪至 296x152 分辨率。
  - **多重抖动算法**：内置 Floyd-Steinberg, Atkinson, Sierra 等多种抖动算法，优化灰度图片在黑白屏上的显示效果。
  - 支持实时预览抖动效果。
- **🚀 增强型 REST API**：
  - 基于 FastAPI 构建，高性能且易于扩展。
  - 自动生成 Swagger/OpenAPI 文档。
  - 封装了 Dot Cloud Auth V2 协议。

## 🛠️ 安装与运行

### 1. 环境要求
- Python 3.9 或更高版本
- 一个有效的 Dot Cloud API Key (在 Dot 开发者平台获取)

### 2. 获取代码
```bash
git clone https://github.com/yourusername/dot_service.git
cd dot_service
```

### 3. 安装依赖
建议使用虚拟环境：
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. 配置
复制示例配置文件并编辑：
```bash
cp .env.example .env
```
在 `.env` 文件中填入你的 API Key 和默认设备 ID：
```ini
DOT_API_KEY=dot_app_xxxxxxxxxxxx
DOT_DEFAULT_DEVICE_ID=xxxxxxxxxxxx
```
*注：你也可以在 Web 界面的“设置”页面动态修改这些配置。*

### 5. 启动服务
直接运行启动脚本：
```bash
python run.py
```
或者使用 Uvicorn：
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

服务启动后，访问 **http://localhost:8000** 即可进入控制台。

## 📖 使用指南

### Web 界面
- **设备概览** (`/`)：查看所有绑定的设备状态和屏幕截图。
- **发送文字** (`/ui/text`)：推送文字消息。支持“渲染为图片”模式，可自定义字号。
- **发送图片** (`/ui/image`)：拖拽上传图片，选择抖动算法（推荐照片使用“平滑扩散”，线条画使用“不处理”）。
- **设置** (`/ui/settings`)：管理 API Key 和默认设备，支持热重载配置。

### API 文档
服务启动后，访问 **http://localhost:8000/docs** 查看完整的 Swagger API 文档。你可以在此页面直接测试 API 接口。

#### 核心接口示例：
- `GET /devices` - 获取设备列表
- `POST /text` - 发送文字
- `POST /image` - 发送 Base64 图片
- `POST /image/upload` - 上传图片文件

## 📂 项目结构

```
dot_service/
├── app/
│   ├── static/          # CSS, JS 静态资源
│   ├── templates/       # Jinja2 HTML 模板
│   ├── config.py        # 配置加载
│   ├── dot_client.py    # Dot Cloud API 客户端封装
│   ├── image_utils.py   # 图片处理与文字渲染逻辑
│   ├── main.py          # FastAPI 应用入口与路由
│   └── models.py        # Pydantic 数据模型
├── .env.example         # 环境变量示例
├── run.py               # 启动脚本
└── requirements.txt     # 项目依赖
```

## 🤝 贡献
欢迎提交 Issue 或 Pull Request 来改进这个项目！

## 📄 许可证
[MIT License](LICENSE)
