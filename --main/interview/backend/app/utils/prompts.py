# -*- coding: utf-8 -*-
"""
Prompt 模板
"""

# 评估答案的 Prompt 模板
EVALUATION_PROMPT_TEMPLATE = """你是一位资深的{job_type}面试官，正在评估候选人的回答。

**题目信息：**
- 题目类型：{question_type}
- 难度：{difficulty}
- 题目：{question}
- 标准答案：{reference_answer}

**候选人回答：**
{user_answer}

**评估要求：**
请从以下维度进行评估（每项0-10分）：

1. **技术准确性** (technical_accuracy): 回答是否正确、是否有错误概念、是否符合技术规范
2. **表达清晰度** (clarity): 逻辑是否清晰、用词是否准确、是否易于理解
3. **深度广度** (depth_breadth): 是否深入理解本质、是否涉及相关知识点、是否有扩展思考

同时请：
4. **关键词分析**：列出候选人回答中命中的关键词（与标准答案对比），以及遗漏的重要关键词
5. **不足之处**：指出回答的具体不足（最多3条）
6. **改进建议**：给出具体可操作的改进建议（最多3条）

**重要**：请严格按照以下JSON格式返回，不要添加任何其他内容：

{{
  "technical_accuracy": 8.0,
  "clarity": 7.0,
  "depth_breadth": 6.0,
  "keywords_hit": ["关键词1", "关键词2"],
  "keywords_missed": ["关键词3", "关键词4"],
  "weaknesses": ["不足1", "不足2"],
  "suggestions": ["建议1", "建议2"]
}}
"""

# 生成追问的 Prompt 模板
FOLLOWUP_PROMPT_TEMPLATE = """你是一位{personality_name}的面试官。

**题目：**{question}

**候选人的回答：**{user_answer}

**评估结果：**
- 综合得分：{total_score}/10
- 主要不足：{weaknesses}

**追问要求：**
基于候选人回答的薄弱点，生成一个{followup_style}。

追问应该：
1. 针对候选人回答中的具体不足之处
2. 帮助深入理解概念或扩展知识面
3. 符合"{personality_name}"的风格
4. 简洁明确，一句话即可

**请直接返回追问内容，不要任何额外说明：**
"""

# 生成最终报告的 Prompt 模板
FINAL_REPORT_PROMPT_TEMPLATE = """你是一位资深的{job_type}面试官，正在为候选人撰写面试总结报告。

**面试信息：**
- 岗位：{job_type}
- 难度：{difficulty}
- 总题数：{total_questions}
- 正确率：{correct_rate:.1%}

**各维度平均分：**
- 技术准确性：{avg_technical:.1f}/10
- 表达清晰度：{avg_clarity:.1f}/10
- 深度广度：{avg_depth:.1f}/10

**答题详情：**
{answer_details}

**任务：**
请基于以上信息，生成：
1. **薄弱领域**（weak_areas）：候选人表现较差的知识点或领域（2-5条）
2. **优势领域**（strong_areas）：候选人表现较好的知识点或领域（1-3条）
3. **改进建议**（suggestions）：具体可操作的学习建议（3-5条）

**重要**：请严格按照以下JSON格式返回：

{{
  "weak_areas": ["薄弱点1", "薄弱点2"],
  "strong_areas": ["优势1", "优势2"],
  "suggestions": ["建议1", "建议2", "建议3"]
}}
"""


def build_evaluation_prompt(
    job_type: str,
    question_type: str,
    difficulty: str,
    question: str,
    reference_answer: str,
    user_answer: str
) -> str:
    """构建评估 Prompt"""
    reference_answer = (reference_answer or "").strip() or "????????????"
    return EVALUATION_PROMPT_TEMPLATE.format(
        job_type=job_type,
        question_type=question_type,
        difficulty=difficulty,
        question=question,
        reference_answer=reference_answer,
        user_answer=user_answer
    )


def build_followup_prompt(
    personality_name: str,
    question: str,
    user_answer: str,
    total_score: float,
    weaknesses: list,
    followup_style: str
) -> str:
    """构建追问 Prompt"""
    weaknesses_str = "、".join(weaknesses) if weaknesses else "无明显不足"

    return FOLLOWUP_PROMPT_TEMPLATE.format(
        personality_name=personality_name,
        question=question,
        user_answer=user_answer,
        total_score=total_score,
        weaknesses=weaknesses_str,
        followup_style=followup_style
    )


def build_final_report_prompt(
    job_type: str,
    difficulty: str,
    total_questions: int,
    correct_rate: float,
    avg_technical: float,
    avg_clarity: float,
    avg_depth: float,
    answer_details: str
) -> str:
    """构建最终报告 Prompt"""
    return FINAL_REPORT_PROMPT_TEMPLATE.format(
        job_type=job_type,
        difficulty=difficulty,
        total_questions=total_questions,
        correct_rate=correct_rate,
        avg_technical=avg_technical,
        avg_clarity=avg_clarity,
        avg_depth=avg_depth,
        answer_details=answer_details
    )
