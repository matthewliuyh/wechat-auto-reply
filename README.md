

# WeChat Auto Reply

微信 PC 端 AI 自动回复工具 —— 零侵入式实现，通过截图 + OCR 识别聊天内容，调用大模型生成回复，自动发送到微信。

## 功能特性

- **零侵入** — 不注入、不Hook微信进程，纯截图 + 键鼠模拟
- **双模式** — 手动模式（人工确认后发送）+ 全托管自动模式（无人值守）
- **多模型** — 支持所有 OpenAI 兼容 API（DeepSeek、智谱、豆包等）
- **多显示器** — 支持多屏幕环境，可切换监控显示器
- **区域裁剪** — 可配置截图区域，只识别聊天内容区
- **OCR 识别** — 基于 RapidOCR，分段识别 + 去重合并，提高准确率
- **消息指纹** — 自动模式通过 MD5 指纹检测新消息，避免重复回复
- **回复记忆** — 学习用户选用的回复风格，逐步个性化
- **聊天记录** — 自动保存确认发送的干净记录，按天分文件
- **历史查看** — 微信气泡风格的历史记录浏览器，日历选择日期

## 界面预览

- 主界面：手动/自动双模式切换，一键识别、生成、发送
- 历史记录：仿微信对话气泡，对方白泡左对齐，我方绿泡右对齐
- 区域设置：可视化配置微信截图区域
- 设置面板：API 配置 + 连接测试

## 快速开始

### 环境要求

- Windows 10/11
- Python 3.8+
- 微信 PC 端（已登录）

### 安装

```bash
git clone https://github.com/yourname/wechat-auto-reply.git
cd wechat-auto-reply
pip install -r requirements.txt
```

### 配置

首次运行前，复制配置模板并填入你的 API 信息：

```bash
cp config.example.json config.json
```

编辑 `config.json`：

```json
{
  "api_url": "https://api.deepseek.com/v1/chat/completions",
  "api_key": "your-api-key-here",
  "model": "deepseek-chat",
  "max_tokens": 150,
  "temperature": 0.7,
  "num_candidates": 3
}
```

支持的 API 地址示例：

| 模型 | api_url | model |
|------|---------|-------|
| DeepSeek | `https://api.deepseek.com/v1/chat/completions` | `deepseek-chat` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | `glm-4-flash` |
| 豆包 | `https://ark.cn-beijing.volces.com/api/v3/chat/completions` | `doubao-seed-2-1-turbo` |
| 其他 OpenAI 兼容 | 对应地址 | 对应模型名 |

### 运行

```bash
python main.py
```

## 使用说明

### 手动模式

1. 打开微信 PC 端，进入聊天窗口
2. 点击 **识别聊天** — 截图并 OCR 识别聊天内容
3. 点击 **生成回复** — 调用大模型生成 3 条候选
4. 选择一条候选或手动输入，点击 **发送**

### 自动模式

1. 在设置中配置好 API 和区域
2. 切换到 **自动模式**
3. 点击 **启动自动** — 程序开始循环检测新消息，自动生成并发送回复
4. 可随时暂停/恢复/停止

### 区域设置

首次使用需配置微信窗口截图区域，确保只截取聊天内容区：

1. 点击 **区域设置**
2. 输入截图区域比例值（left / top / right / bottom）
3. 点击 **预览** 确认截取范围
4. 保存配置

> 如果你是 200% DPI 缩放，程序会自动处理坐标转换。

### 历史记录

- 点击 **历史记录** 查看已发送的聊天记录
- 顶部箭头切换日期，点击日期可弹出日历选择
- 微信气泡风格展示，对方白泡左侧 + 我方绿泡右侧

## 项目结构

```
wechat-auto-reply/
├── main.py            # GUI 主界面（手动 + 自动双模式）
├── capture.py         # 微信窗口截图 + 区域设置
├── ocr_engine.py      # OCR 识别（RapidOCR 分段 + 去重）
├── parser.py          # 消息解析（区分对方/我方）
├── generator.py       # LLM 回复生成 + 连接测试
├── sender.py          # 消息发送（剪贴板 + 键鼠模拟）
├── memory.py          # 回复记忆（学习用户风格）
├── auto_engine.py     # 全托管自动模式引擎
├── chat_log.py        # 聊天记录保存与读取
├── config.json        # API 配置（需自行创建）
├── region_config.json # 截图区域比例配置
├── requirements.txt   # Python 依赖
└── chat_logs/         # 聊天记录目录（按天 .md 文件）
```

## 常见问题

**Q: 提示"未检测到微信"？**
A: 确保微信 PC 端已打开且未最小化到托盘。程序通过窗口类名匹配查找微信。

**Q: OCR 识别不全？**
A: 检查区域设置是否覆盖了完整的聊天区域。使用区域设置中的预览功能确认。

**Q: 高 DPI 下截图区域偏移？**
A: 程序已自动处理 DPI 感知（`SetProcessDpiAwareness(2)`），如果仍有问题请检查系统缩放设置。

**Q: 自动模式重复回复？**
A: 消息指纹基于对方消息文本的 MD5，自己发送的回复不会触发重复检测。

## 许可证

MIT License

> AI生成
