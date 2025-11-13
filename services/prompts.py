from ollama import chat
from ollama import ChatResponse
import re


##########################################简历生成prompts#########################################
# 第一步：提取求职意向和基本信息
def grap_user_info(user_data):
    grap_info = chat(model='qwen:7b', messages=[
    {
        'role': 'user',
        'content': f'''
    请分析以下用户信息：
    1. 提取用户的求职意向岗位（如果简历中明确提到）
    2. 如果没有明确求职意向，请根据用户的教育背景、项目经历、实习经历分析最匹配的3个岗位方向
    3. 提取用户的基本信息（姓名、性别、教育背景、工作经历、实习经历等）

    用户信息：
    """
    {user_data}
    """

    请按照以下格式返回：
    求职意向：[具体的岗位或分析出的最匹配岗位]
    基本信息：[结构化提取的基本信息]
    '''
        },
    ])
    content = grap_info['message']['content']
    # 提取求职意向
    career_match = re.search(r'求职意向：(.+)', content)
    career_target = career_match.group(1).strip() if career_match else ""
    # 提取基本信息
    info_match = re.search(r'基本信息：(.+)', content, re.DOTALL)
    basic_info = info_match.group(1).strip() if info_match else ""

    return career_target,basic_info

# 第二步：分析岗位求职要求
def get_career_analyze(career_target):
    analyze = chat(model='qwen:7b', messages=[
    {
        'role': 'user', 
        'content': f'''
    基于第一步分析的求职意向：{career_target}
    请详细分析该岗位的：
    1. 核心能力要求
    2. 具体职位要求  
    3. 主要工作职责

    请结构化返回分析结果。
    '''
        },
    ])
    career_analyze=analyze['message']['content']
    return career_analyze

# 第三步：匹配与润色经历
def generate_experience(career_target,career_analyze,basic_info):
    generate_experience = chat(model='qwen:7b', messages=[
    {
        'role': 'user',
        'content': f'''
    求职意向：{career_target}
    岗位要求：{career_analyze}
    用户基本信息：{basic_info}

    请使用STAR法则对用户的经历进行匹配和润色，重点突出：
    - 与目标岗位的相关性
    - 技术能力和成果量化
    - 使用的工具和方法论

    请按照以下格式返回润色后的经历：
    ### [经历名称]
    *[技术栈/工具]*
    - **情境（Situation）**：[项目背景]
    - **任务（Task）**：[具体任务]  
    - **行动（Action）**：[采取的行动，使用的技术]
    - **结果（Result）**：[量化成果]
    '''
        },
    ])
    experience=generate_experience['message']['content']
    return experience



def build_resume_prompt(user_data: str, jd_text: str) -> str:

    career_target,basic_info=grap_user_info(user_data)

    if jd_text==None:
        career_analyze=get_career_analyze(career_target)
    else:
        career_analyze=jd_text

    experience=generate_experience(career_target,career_analyze,basic_info)

    generate_resume =chat(model='qwen:7b', messages=[
    {
        'role': 'user',
        'content': f'''
    用户基本信息：{basic_info}
    润色后的经历：{experience}

    请将以上信息整合成完整的简历，保持与原始简历相似的格式，但使用润色后的内容。
    简历应包含：
    1. 基本信息部分
    2. 教育背景
    3. 实习经历（使用润色后的版本）
    4. 项目经历（使用润色后的版本） 
    5. 竞赛经历（使用润色后的版本）
    6. 技能证书等

    '''    
        },
    ])
    resume=generate_resume['message']['content']

    return resume



    
    


############################################面试问题prompts##################################################
def build_questions_prompt(career_target: str,user_resume:str) -> str:
    # 第一步：分析岗位要求
    generate_requirement = chat(model='qwen:7b', messages=[
    {
        'role': 'user',
        'content': f'''
    请分析以下目标岗位的面试要求：
    1. 提取该岗位的核心能力要求（技术能力、软技能等）
    2. 分析该岗位的典型工作场景和挑战
    3. 识别该岗位关注的关键经验和成果

    目标岗位：
    """
    {career_target}
    """

    请按照以下格式返回：
    核心能力要求：[列出5-8项关键能力]
    工作场景挑战：[描述2-3个典型工作场景]
    关键经验指标：[列出3-5个重点关注的经验领域]
    '''
        },
    ])
    job_requirements = generate_requirement['message']['content']

    # 第二步：生成风格化面试问题

    generate_question = chat(model='qwen:7b', messages=[
    {
        'role': 'user',
        'content': f'''
    目标岗位要求：{job_requirements}
    用户简历信息：{user_resume}

    你是一名资深HR,请基于岗位要求与用户简历的匹配度，生成以下不同风格的面试问题：

    ##  技术深度型问题
    *重点考察技术能力和专业深度*
    - [3-5个针对简历中具体技术栈的深入问题]
    - [2-3个场景化的技术解决方案问题]

    ##  行为经验型问题  
    *基于STAR法则的行为面试*
    - [3-4个针对简历中关键项目经历的问题]
    - [2-3个关于团队协作和问题处理的问题]

    ##  压力挑战型问题
    *考察应变能力和抗压能力*
    - [2-3个假设性的困难场景问题]
    - [1-2个针对简历中可能弱点的挑战性问题]

    ##  潜力发展型问题
    *考察学习能力和职业规划*
    - [2-3个关于技能学习和成长的问题]
    - [1-2个职业发展规划相关问题]

    请确保问题：
    1. 紧密结合简历中的具体经历
    2. 针对岗位要求中的关键能力
    3. 体现不同面试风格的考察重点
    4. 问题具体可操作，避免泛泛而谈
    '''
        },
    ])

    interview_question=generate_question['message']['content']
    return interview_question


###############################################生成面试反馈##################################################
def generate_feedback(interview_question,interview_answers_text):
    response_feedback = chat(model='qwen:7b', messages=[
    {
        'role': 'user',
        'content': f'''
    ## 面试评估任务

    **面试问题：**
    {interview_question}

    **面试者回答文本：**
    {interview_answers_text}

    ## 请从以下维度提供详细反馈：

    ###  回答质量评估
    1. **内容匹配度**：回答是否准确匹配问题意图
    2. **结构完整性**：是否逻辑清晰、条理分明
    3. **深度与广度**：是否展现专业深度和知识面

    ###  STAR法则应用分析
    - **情境(S)**：是否清晰描述背景环境
    - **任务(T)**：是否明确说明目标任务
    - **行动(A)**：是否详细阐述具体行动
    - **结果(R)**：是否量化展示成果效果

    ###  改进建议
    针对每个问题的回答：
    - **亮点肯定**：指出回答中的优秀表现
    - **不足指出**：明确需要改进的方面
    - **优化示范**：提供更好的回答示例

    ###  风险提示
    - **逻辑矛盾**：回答中是否存在前后不一致
    - **内容空洞**：是否缺乏具体细节支撑
    - **回避问题**：是否刻意避开关键问题

    ###  综合评分
    按5分制对每个回答评分，并给出总体评价

    请按以下格式返回：
    ## 面试反馈报告

    ### 问题1：[问题内容]
    **评分**：⭐️⭐️⭐️⭐️☆ (4/5)
    **亮点**：[具体亮点]
    **不足**：[具体不足]
    **建议**：[优化建议]
    **示范回答**：[更好的回答示例]

    ### 总体评价
    [综合表现总结和能力画像]
    '''
        },
    ])
    feed_back=response_feedback['message']['content']
    return feed_back
