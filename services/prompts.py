def build_resume_prompt(resume_text: str, jd_text: str) -> str:
    return f"""你是资深求职顾问与简历优化专家。
请阅读候选人的原始简历与目标岗位JD，输出一份“面向该岗位的定制化简历（Markdown）”：
要求：
- 结构包含：个人概述、核心技能（与JD强相关）、项目经历（STAR法强调结果与量化）、教育经历、加分项与关键词
- 语言跟随JD（JD中文则中文；JD英文则英文）
- 事实准确，不虚构；把与JD强相关内容前置
- 输出 Markdown 正文，无需额外解释

===【候选人原始简历】===
{resume_text}

===【目标岗位JD】===
{jd_text}
"""

def build_questions_prompt(jd_text: str) -> str:
    return f"""根据下面岗位JD，生成 8-12 个结构化面试问题（含追问要点），尽量覆盖技能、项目、数据指标、团队协作与风险意识。
输出为 JSON 数组，每个元素包含：
- question: 问题
- followups: 2-3 条追问要点（数组，短句）

===【岗位JD】===
{jd_text}
"""