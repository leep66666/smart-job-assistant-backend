def build_resume_prompt(resume_text: str, jd_text: str, language: str = 'zh') -> str:
    """
    根据语言生成对应的prompt
    language: 'zh' 或 'en'
    """
    if language == 'zh':
        return f"""# 角色

你是一位资深的简历优化专家和AI招聘助手。

# 背景

我将为你提供两份结构化信息：

1. 【个人信息库】：一个包含候选人所有背景信息的详细数据库，包括基本信息、教育背景、实习经历、项目经验、技能和奖项等。

2. 【岗位JD】：一个具体的目标岗位描述，包含了岗位的职责和要求。

# 任务

你的任务是根据【岗位JD】，从【个人信息库】中筛选、提炼、整合并优化信息，为候选人生成一份专业、高度匹配、且富有吸引力的求职简历。

# 生成要求

1. **高度匹配 (Relevance is Key):**
   - 仔细分析【岗位JD】中的每一个关键词（例如编程语言、技术框架、职责描述）。
   - 优先选择并突出【个人信息库】中与这些关键词最相关的经历和技能。对于不相关的次要信息，应省略或简化。

2. **量化成果 (Quantify Achievements):**
   - 将经历中的职责描述转化为可量化的成果。例如，不要只说"负责开发功能"，而要说"使用Go语言开发API，使查询延迟降低15%"。所有数据必须源自【个人信息库】。

3. **STAR法则:**
   - 在描述实习和项目经历时，尽量遵循STAR法则（Situation, Task, Action, Result），清晰地展现候选人在特定场景下的行动和带来的价值。

4. **结构清晰 (Clear Structure):**
   - 简历应包含以下部分：个人信息、专业技能、实习经历、项目经历、教育背景、奖项荣誉。请合理安排各部分的顺序，将最亮眼的部分（如实习经历）放在前面。
   - 使用Markdown格式，第一行必须是候选人的真实姓名，格式为：`# 姓名`
   - 姓名下方一行，用Markdown格式列出联系方式（电话、邮箱、GitHub、LinkedIn等），用 | 分隔
   - 使用 `##` 作为章节标题

5. **专业语言 (Professional Tone):**
   - 使用简洁、专业、有力的动词开头（例如：负责、实现、优化、参与、推动）。
   - 确保整份简历没有语法错误和拼写错误。

6. **事实准确性 (Factual Accuracy):**
   - **客观信息必须严格遵照【个人信息库】，绝对不能篡改或夸大：**
    - 姓名、电话、邮箱、GitHub等联系方式必须与【个人信息库】完全一致
    - 教育经历（学校名称、专业、学位、时间、GPA）必须与【个人信息库】完全一致
    - 工作经历的公司名称、职位名称、工作时间必须与【个人信息库】完全一致
    - 项目名称、项目时间必须与【个人信息库】完全一致
   - 所有量化数据必须源自【个人信息库】，不允许虚构或夸大

7. **输出格式:**
   - 输出纯Markdown格式，不要包含代码块标记（不要用 ``` 包裹）
   - 所有内容必须使用中文

# 输入信息

【个人信息库】:

---
{resume_text}
---

【岗位JD】:

---
{jd_text}
---

# 输出

请直接生成最终的简历内容（Markdown格式）。
"""
    else:
        return f"""# Role

You are a senior resume optimization expert and AI recruitment assistant.

# Background

I will provide you with two structured pieces of information:

1. 【Personal Information Database】: A detailed database containing all background information about the candidate, including basic information, educational background, internship experience, project experience, skills, and awards.

2. 【Job Description】: A specific target job description containing job responsibilities and requirements.

# Task

Your task is to filter, extract, integrate, and optimize information from the 【Personal Information Database】 based on the 【Job Description】, and generate a professional, highly matched, and attractive resume for the candidate.

# Generation Requirements

1. **High Relevance (Relevance is Key):**
   - Carefully analyze every keyword in the 【Job Description】(e.g., programming languages, technical frameworks, job responsibilities).
   - Prioritize and highlight experiences and skills from the 【Personal Information Database】 that are most relevant to these keywords. Omit or simplify irrelevant secondary information.

2. **Quantify Achievements:**
   - Transform responsibility descriptions into quantifiable achievements. For example, don't just say "responsible for developing features", but say "Developed API using Go language, reducing query latency by 15%". All data must come from the 【Personal Information Database】.

3. **STAR Method:**
   - When describing internship and project experiences, try to follow the STAR method (Situation, Task, Action, Result), clearly showing the candidate's actions and value in specific scenarios.

4. **Clear Structure:**
   - The resume should include the following sections: Personal Information, Professional Skills, Internship Experience, Project Experience, Educational Background, Awards and Honors. Arrange the order of each section reasonably, placing the most impressive parts (such as internship experience) first.
   - Use Markdown format, the first line must be the candidate's real name, formatted as: `# Name`
   - The second line should contain contact information (phone, email, GitHub, LinkedIn, etc.) in Markdown format, separated by |
   - Use `##` for section headings

5. **Professional Tone:**
   - Use concise, professional, and powerful verbs at the beginning (e.g., responsible for, implemented, optimized, participated in, promoted).
   - Ensure the entire resume has no grammatical errors or spelling mistakes.

6. **Factual Accuracy:**
   - **Objective information MUST strictly follow the 【Personal Information Database】, absolutely NO modification or exaggeration:**
    - Name, phone, email, GitHub and other contact information must be EXACTLY the same as the 【Personal Information Database】
    - Education (university name, major, degree, time period, GPA) must be EXACTLY the same as the 【Personal Information Database】
    - Work experience (company name, job title, time period) must be EXACTLY the same as the 【Personal Information Database】
    - Project names and time periods must be EXACTLY the same as the 【Personal Information Database】
   - All quantitative data must come from the 【Personal Information Database】, no fabrication or exaggeration is allowed

7. **Output Format:**
   - Output pure Markdown format, do NOT include code block markers (do NOT wrap in ```)
   - All content must be in English

# Input Information

【Personal Information Database】:

---
{resume_text}
---

【Job Description】:

---
{jd_text}
---

# Output

Please directly generate the final resume content (Markdown format).
"""

def build_resume_verification_prompt(resume_text: str, generated_resume: str, language: str = 'zh') -> str:
    """
    构建简历检阅提示词
    resume_text: 原始个人信息库
    generated_resume: 生成的简历
    language: 'zh' 或 'en'
    """
    if language == 'zh':
        return f"""# 角色

你是一个极其严谨和细致的AI简历事实核查官。你的唯一任务是检验一份生成的简历内容是否完全忠于原始的个人信息库，杜绝任何形式的夸大和虚构。

# 背景

我将为你提供两份信息：

1. 【个人信息库】：这是唯一的事实来源（Ground Truth），包含了候选人真实、完整的背景信息。

2. 【生成的简历】：这是一份由AI根据个人信息库和某个岗位JD生成的简历。

# 任务

你的任务是逐字逐句地对比【生成的简历】和【个人信息库】，判断简历中是否存在任何"胡编乱造"或"无中生有"的内容。

# 检验标准

1. **事实一致性:** 简历中的每一个信息点（如公司名称、项目名称、时间、使用的技术、具体数据、获得的奖项等）都必须能在【个人信息库】中找到完全对应的原始记录。

2. **数据准确性:** 简历中提到的所有量化指标（如"GPA 3.85"、"留存率提升5%"、"延迟降低15%"等）必须与【个人信息库】中的数据完全一致，不允许有任何夸大或修改。

3. **技能真实性:** 简历中列出的所有技能，必须是【个人信息库】中明确提到的。不允许虚构候选人未掌握的技能。

# 输出要求

请按照以下格式进行输出：

1. **检验结论:**
   - 如果简历完全忠于信息库，请回答："**检验通过：简历内容与个人信息库完全一致，未发现胡编乱造。**"
   - 如果发现任何不一致，请回答："**检验失败：简历内容与个人信息库存在不一致，发现胡编乱造的内容。**"

2. **置信度 (Confidence Score):**
   - 请给出一个百分比形式的置信度，表示你对上述"检验结论"的确定程度。例如："**置信度：99.5%**"。

3. **差异详情 (Discrepancy Details):**
   - 如果检验失败，请在此部分详细列出所有不一致的地方。每一条差异都应包含：
     - **【简历中的陈述】:** "..."
     - **【信息库中的原文】:** "..." 或 "【信息库中未找到相关记录】"
     - **【问题类型】:** (例如：数据夸大、技能虚构、事实不符等)

# 输入信息

【个人信息库】:

---
{resume_text}
---

【生成的简历】:

---
{generated_resume}
---

# 输出

请根据上述输出要求，开始你的检验工作。
"""
    else:
        return f"""# Role

You are an extremely rigorous and meticulous AI resume fact-checker. Your sole task is to verify whether a generated resume content is completely faithful to the original personal information database, eliminating any form of exaggeration and fabrication.

# Background

I will provide you with two pieces of information:

1. 【Personal Information Database】: This is the only source of truth (Ground Truth), containing the candidate's real and complete background information.

2. 【Generated Resume】: This is a resume generated by AI based on the personal information database and a job description.

# Task

Your task is to compare the 【Generated Resume】 and the 【Personal Information Database】 word by word, and determine whether there is any "fabricated" or "made-up" content in the resume.

# Verification Standards

1. **Factual Consistency:** Every piece of information in the resume (such as company names, project names, time periods, technologies used, specific data, awards received, etc.) must have a completely corresponding original record in the 【Personal Information Database】.

2. **Data Accuracy:** All quantitative indicators mentioned in the resume (such as "GPA 3.85", "retention rate increased by 5%", "latency reduced by 15%", etc.) must be completely consistent with the data in the 【Personal Information Database】, and no exaggeration or modification is allowed.

3. **Skill Authenticity:** All skills listed in the resume must be explicitly mentioned in the 【Personal Information Database】. It is not allowed to fabricate skills that the candidate does not possess.

# Output Requirements

Please output according to the following format:

1. **Verification Conclusion:**
   - If the resume is completely faithful to the database, please answer: "**Verification Passed: The resume content is completely consistent with the personal information database, no fabrication found.**"
   - If any inconsistency is found, please answer: "**Verification Failed: The resume content is inconsistent with the personal information database, fabricated content found.**"

2. **Confidence Score:**
   - Please provide a percentage confidence score indicating your certainty about the above "verification conclusion". For example: "**Confidence: 99.5%**".

3. **Discrepancy Details:**
   - If verification fails, please list all inconsistencies in detail in this section. Each discrepancy should include:
     - **【Statement in Resume】:** "..."
     - **【Original Text in Database】:** "..." or "【No relevant record found in database】"
     - **【Issue Type】:** (e.g., data exaggeration, skill fabrication, factual inconsistency, etc.)

# Input Information

【Personal Information Database】:

---
{resume_text}
---

【Generated Resume】:

---
{generated_resume}
---

# Output

Please start your verification work according to the above output requirements.
"""

def build_questions_prompt(jd_text: str) -> str:
    return f"""根据下面岗位JD，生成 10 个结构化面试问题（含追问要点），尽量覆盖技能、项目、数据指标、团队协作与风险意识。
输出为 JSON 数组，每个元素包含：
- question: 问题
- followups: 2-3 条追问要点（数组，短句）

要求：
1. 必须生成恰好 10 个问题
2. 问题应该针对岗位JD的具体要求
3. 问题应该多样化，涵盖技术能力、项目经验、软技能等方面
4. 输出格式必须是有效的 JSON 数组

===【岗位JD】===
{jd_text}
"""