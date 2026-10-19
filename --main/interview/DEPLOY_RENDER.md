# Render 后端部署

- Root Directory：`--main/interview/backend`
- Build Command：`pip install -r requirements.txt`
- Start Command：`uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health Check Path：`/healthz`（不调用外部服务）
- 必需环境变量：`OPENAI_API_KEY`，填写实际密钥。

## 使用本地题库恢复服务

在 Render 的 Environment 中设置：

```text
QUESTION_JSON_PATH=../../data/第一轮仔细清洗/interview_questions_categorized.json
SKIP_STARTUP_TESTS=1
```

JSON 路径相对于 backend 解析，显式 JSON 配置优先于 Supabase。
没有配置题库来源时也会自动使用此附带题库。
这能绕开 Supabase 的 DNS/连接故障；不会修复错误的远程域名。

## 使用 Supabase

移除 `QUESTION_JSON_PATH`，设置真实的 `SUPABASE_URL`、`SUPABASE_SERVICE_KEY`，以及可选的 `SUPABASE_TABLE`。
URL 应为项目根地址，例如 `https://<实际项目标识>.supabase.co`，不要填写示例域名、控制台地址、API 路径或外层引号。

Supabase 的网络连接失败时会记录警告并使用附带题库；认证、表结构和空表错误仍会明确报错，不伪装为连接故障。
如果必须使用远程最新题库，请检查警告并修复 Supabase 配置后重新部署。

`SKIP_STARTUP_TESTS=1` 只跳过额外的连通性探测，不会阻止所选题库在初始化时加载。
SQLite 默认写入部署实例的本地文件；要跨重启保留记录，需要挂载持久磁盘并设置 `SQLITE_DB_PATH`。

参考：[Render 端口绑定](https://render.com/docs/web-services#port-binding)、[部署排错](https://render.com/docs/troubleshooting-deploys)。
