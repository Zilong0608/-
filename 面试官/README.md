# AI 面试官系统

基于 RAG 和多人格的智能面试评估系统

## 功能特点

- 📚 **海量题库**: 基于 ChromaDB 向量数据库的 RAG 检索，支持动态问题加载
- 🎭 **多种人格**: 严格专业型、友好鼓励型、压力测试型、实战导向型四种面试官人格
- 📊 **多维评估**: 技术准确性、表达清晰度、深度广度三维度评分
- 💡 **智能追问**: 根据答题情况自动生成针对性追问
- 📈 **详细报告**: 生成包含薄弱领域、优势领域、改进建议的完整面试报告
- 💾 **本地存储**: SQLite 数据库存储所有面试记录（支持扩展 PostgreSQL）

## 系统架构

```
backend/
├── app/
│   ├── api/              # FastAPI 路由
│   ├── cli/              # 命令行工具
│   ├── core/             # 核心引擎
│   │   ├── interview_engine.py      # 面试引擎
│   │   ├── evaluation_engine.py     # 评估引擎
│   │   └── personality_manager.py   # 人格管理器
│   ├── services/         # 服务层
│   │   ├── ai_service.py            # OpenAI API 封装
│   │   ├── question_service.py      # 问题仓库 (RAG)
│   │   └── data_service.py          # 数据持久化
│   ├── models/           # 数据模型
│   ├── utils/            # 工具模块
│   ├── config/           # 配置文件
│   └── main.py           # FastAPI 应用入口
├── run_cli.py            # CLI 启动脚本
└── run_server.py         # API 服务器启动脚本
```

## 快速开始

### 1. 环境准备

**要求**:
- Python 3.10+
- OpenAI API Key
- ChromaDB 向量数据库（已有数据索引）

### 2. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `.env`:

```env
# OpenAI API 配置
OPENAI_API_KEY=your_openai_api_key_here

# RAG 向量数据库路径
RAG_VECTOR_STORE_PATH=../数据/data_index

# 数据库配置
DATABASE_TYPE=sqlite
SQLITE_DB_PATH=../data/interviews.db
```

### 4. 运行方式

#### 方式一：命令行模式（推荐入门）

```bash
python run_cli.py
```

交互式命令行界面，适合快速体验。

#### 方式二：API 服务器模式

```bash
python run_server.py
```

启动后访问：
- API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/api/v1/health

## 使用说明

### CLI 模式使用流程

1. **启动程序**
   ```bash
   python run_cli.py
   ```

2. **配置面试**
   - 输入岗位类型（如：后端开发）
   - 选择难度级别（简单/中等/困难）
   - 设置题目数量（建议 10-20 题）
   - 选择面试官人格或随机

3. **开始面试**
   - 查看开场白和第一个问题
   - 输入答案（支持多行，空行结束输入）
   - 查看评估结果和反馈
   - 如有追问，继续回答
   - 循环直到完成所有题目

4. **查看报告**
   - 面试结束后自动生成报告
   - 包含总体评分、薄弱领域、优势领域、改进建议

### API 模式使用流程

详见 API 文档：http://localhost:8000/docs

基本流程：

1. **创建会话**
   ```
   POST /api/v1/sessions
   ```

2. **启动面试**
   ```
   POST /api/v1/sessions/{session_id}/start
   ```

3. **提交答案**
   ```
   POST /api/v1/sessions/{session_id}/answer
   ```

4. **获取下一题**
   ```
   GET /api/v1/sessions/{session_id}/next-question
   ```

5. **结束面试**
   ```
   POST /api/v1/sessions/{session_id}/end
   ```

## 配置说明

### settings.yaml

主要配置项：

```yaml
rag:
  preload_count: 100          # 预加载问题数量
  refill_threshold: 20        # 触发补充的阈值

ai:
  model: "gpt-4o"            # OpenAI 模型
  max_retries: 3             # 最大重试次数
  timeout: 30                # 超时时间（秒）
  temperature:
    evaluation: 0.3          # 评估温度（低，稳定）
    followup: 0.7            # 追问温度（高，创意）
    report: 0.5              # 报告温度（中等）

interview:
  max_questions: 20          # 默认最大题数
  followup_score_min: 6.0    # 追问得分下限
  followup_score_max: 8.0    # 追问得分上限
```

### 人格配置

在 `app/config/personalities/` 目录下：

- `strict.yaml` - 严格专业型
- `friendly.yaml` - 友好鼓励型
- `pressure.yaml` - 压力测试型
- `practical.yaml` - 实战导向型

可自定义添加新人格。

## 数据流程

```
用户答题 → 评估引擎 → AI 评分 → 人格调整 → 生成反馈
                ↓
         判断是否追问
                ↓
         生成追问问题 → 用户回答追问
                ↓
         保存评估结果 → SQLite
                ↓
         继续下一题 / 结束面试
                ↓
         生成最终报告 → AI 分析 → 保存
```

## 评分标准

### 三维度评分（0-10 分）

1. **技术准确性** (权重 50%)
   - 回答是否正确
   - 是否有错误概念
   - 是否符合技术规范

2. **表达清晰度** (权重 20%)
   - 逻辑是否清晰
   - 用词是否准确
   - 是否易于理解

3. **深度广度** (权重 30%)
   - 是否深入理解本质
   - 是否涉及相关知识点
   - 是否有扩展思考

### 追问机制

- 总分在 6.0-8.0 分区间时触发追问
- 针对回答中的薄弱点进行深入考察
- 追问答案记录但不详细评分

### 通过标准

- 单题：总分 ≥ 6.0 视为通过
- 整体：通过率 ≥ 60% 为合格表现

## 常见问题

### Q: RAG 连接失败怎么办？

A: 检查以下几点：
1. `RAG_VECTOR_STORE_PATH` 路径是否正确
2. ChromaDB 数据索引是否存在
3. 数据索引是否有读取权限

### Q: OpenAI API 调用失败？

A: 检查：
1. `OPENAI_API_KEY` 是否正确
2. API Key 是否有足够额度
3. 网络是否可访问 OpenAI API
4. 是否遇到速率限制（系统会自动重试）

### Q: 如何添加自定义人格？

A: 在 `app/config/personalities/` 下创建新的 YAML 文件，参考现有人格配置格式。

### Q: 数据库文件在哪里？

A: 默认在 `../data/interviews.db`（可在 `.env` 中配置）

### Q: 如何查看历史面试记录？

A: 可使用 SQLite 客户端打开数据库文件，或通过 API 的统计接口查询。

## 扩展开发

### 添加新的评估维度

编辑 `app/utils/prompts.py` 中的评估模板，修改 `EvaluationResult` 模型。

### 切换到 PostgreSQL

1. 安装 `psycopg2`
2. 修改 `.env` 中 `DATABASE_TYPE=postgresql`
3. 实现 `DataService` 的 PostgreSQL 适配器

### 接入语音功能

参考 `wmvoice3` 项目，在 CLI 或 API 层添加语音输入/输出接口。

## 技术栈

- **后端框架**: FastAPI
- **AI 服务**: OpenAI GPT-4o
- **向量数据库**: ChromaDB
- **本地数据库**: SQLite
- **CLI 界面**: Rich
- **日志**: Loguru
- **配置**: PyYAML
- **环境变量**: python-dotenv

## 许可证

MIT License

## 联系方式

如有问题或建议，欢迎提出 Issue。
