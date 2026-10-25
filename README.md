# 找鸡（AstrBot 插件）

发送「找鸡」并附带 / 引用一张图片，或直接发送图片链接，插件会调用
[SauceNAO](https://saucenao.com/) 搜索图片来源，并用文字消息返回结果。

## 效果

```
**已找到鸡**

平台：Pixiv
匹配：视觉匹配
名字：画师昵称
账号：@724886

⚠识图存在误差，请自行核对哦~
```

- `名字`：作者昵称。Pixiv 取画师昵称（`member_name`）；Twitter 取账号名；
- `账号`：作者账号。Twitter 显示 `@twitter_user_handle`（如 `@mamamia1008`）；
  Pixiv 显示 `@` + 画师数字用户 ID（`member_id`，如 `@724886`）；
- 引用图片触发时，「匹配」显示 `视觉匹配`；发送图片链接触发时显示 `图片直链`；
- 平台按 SauceNAO 索引 ID 映射：`5/6 → Pixiv`、`41 → X (Twitter)`、`9 → Danbooru`，
  其余使用清理后的 `index_name`（会自动去掉 `Index #41: ... - xxx.jpg` 这类前缀和文件名）。

## 安装

1. 将整个 `astrbot_plugin_findchicken` 目录放入 AstrBot 的 `data/plugins/` 下：

   ```
   AstrBot/data/plugins/astrbot_plugin_findchicken/
   ```

2. 在 AstrBot WebUI 的「插件」页面点击刷新 / 重载插件。
3. **配置 SauceNAO API Key**（必填）：注册 SauceNAO 账号后，在
   <https://saucenao.com/user.php?page=search-api> 页面获取 API Key，
   填入插件配置的 `api_key` 项。SauceNAO 已不允许匿名账号调用 API，
   没有 Key 时插件会提示配置。
4. 插件依赖 `aiohttp`，AstrBot 已内置；若你的环境缺失，可在插件目录执行
   `pip install -r requirements.txt`。

## 配置

在 WebUI 的插件配置中修改，配置项与默认值：

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `api_key` | string | 空 | **必填**。SauceNAO API Key：https://saucenao.com/user.php?page=search-api |
| `proxy` | string | 空 | 访问 SauceNAO 使用的 HTTP/HTTPS 代理，如 `http://127.0.0.1:7890` |
| `timeout_seconds` | int | 30 | 请求超时（5-120 秒） |
| `max_results` | int | 1 | 最多展示几条结果（1-5） |
| `similarity_threshold` | int | 30 | 最低相似度（%），低于该值的结果不展示 |
| `send_progress` | bool | true | 搜索前是否先发一条「正在找鸡」提示 |
| `show_similarity` | bool | false | 是否在「匹配」后显示相似度百分比 |
| `cooldown_seconds` | int | 10 | 同一用户的搜索冷却时间（秒），0 为不限制 |

> 国内服务器通常需要给 `proxy` 配置代理才能访问 `saucenao.com`。

## 使用

在 QQ 等平台（需 @机器人 或使用唤醒前缀，取决于 AstrBot 配置）：

1. **引用图片**：引用一张图片消息，然后发送 `找鸡`；
2. **附带图片**：发送图片的同时发送 `找鸡`；
3. **图片链接**：发送 `找鸡 https://example.com/image.jpg`。

没有检测到图片时会返回使用说明。

## 常见问题

- **提示「还没有配置 SauceNAO API Key」**：SauceNAO 已不允许匿名账号调用 API，
  请到插件配置填写 `api_key`。
- **提示「API Key 无效或未生效」**：确认 Key 复制完整、没有多余空格；免费账号
  额度约 150 次/天，额度用尽也会失败。
- **提示「被 Cloudflare 拦截」**：通常是服务器网络或出口 IP 问题，可配置 `proxy`
  后重试。
- **搜不到结果**：尝试调低 `similarity_threshold`，或换一张清晰度更高、
  没有被裁剪过的图片。

## 实现说明

- 搜索接口：`POST https://saucenao.com/search.php`，参数 `output_type=2&db=999`；
- 平台映射与索引表来自 SauceNAO 官方
  [index_details.txt](https://saucenao.com/tools/examples/api/index_details.txt)；
- 图片链接直接通过 `url` 参数提交；本地图片 / base64 图片通过 multipart 字段 `file` 上传；
- 引用图片优先使用 AstrBot 内置的 `extract_quoted_message_images`（4.25+），
  低版本回退到 `Reply.chain`、被引用消息文本中的链接和原始消息段；
- 针对 QQ 回复图片时会自动插入被回复者 `@` 的情况，额外注册了一个
  `aiocqhttp` 监听器兜底，避免「回复 + 找鸡」因指令匹配失败而无响应；
- 只依赖 AstrBot 插件 API 与 `aiohttp`，不写入任何持久化数据。

## 目录结构

```
astrbot_plugin_findchicken/
├── main.py                  # 插件入口、指令处理
├── metadata.yaml            # 插件元数据
├── _conf_schema.json        # WebUI 配置 schema
├── requirements.txt
├── findchicken/
│   ├── client.py            # SauceNAO 异步客户端
│   ├── models.py            # 响应解析与结果模型
│   ├── formatter.py         # 输出文案格式化
│   └── image_source.py      # 从消息事件提取图片
└── tests/                   # 离线单元测试（不访问网络）
```

## 测试

在插件目录运行：

```bash
python -m pytest tests -q
```

测试使用本地 stub 模拟 AstrBot API，不会访问 SauceNAO。

## 参考

- [SauceNAO API 文档](https://saucenao.com/user.php?page=search-api)
- [AstrBot 插件开发指南](https://astrbot.app/dev/star/plugin-new.html)
