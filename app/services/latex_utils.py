import re
from typing import Tuple

LATEX_SPECIAL = {
    '\\': r'\textbackslash{}',
    '{': r'\{',
    '}': r'\}',
    '#': r'\#',
    '$': r'\$',
    '%': r'\%',
    '&': r'\&',
    '_': r'\_',
    '^': r'\^{}',
    '~': r'\~{}',
}

def escape_latex(text: str) -> str:
    """转义普通段落中的 LaTeX 特殊字符"""
    # 先替换反斜杠，避免后续二次替
    text = text.replace('\\', LATEX_SPECIAL['\\'])
    for ch, rep in LATEX_SPECIAL.items():
        if ch == '\\':
            continue
        text = text.replace(ch, rep)
    return text

def markdown_to_latex(md: str) -> str:
    """
    极简 Markdown -> LaTeX：
    - #/##/### 标题 -> \section/\subsection/\subsubsection
    - 列表行以 -, *, • 开头 -> itemize
    - 行内 `code` -> \texttt{}
    - 三引号代码块 ``` -> verbatim
    - 其他行做 LaTeX 特殊字符转义
    """
    lines = md.splitlines()
    out = []
    in_verbatim = False
    in_itemize = False

    def flush_itemize():
        nonlocal in_itemize
        if in_itemize:
            out.append(r'\end{itemize}')
            in_itemize = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # 代码块开始/结束：```lang 或 ```
        if re.match(r'\s*```', line):
            flush_itemize()
            if not in_verbatim:
                out.append(r'\begin{verbatim}')
                in_verbatim = True
            else:
                out.append(r'\end{verbatim}')
                in_verbatim = False
            i += 1
            continue

        if in_verbatim:
            out.append(line)  # verbatim 里不做转义
            i += 1
            continue

        # 标题
        if line.startswith('### '):
            flush_itemize()
            out.append(r'\subsubsection{' + escape_latex(line[4:].strip()) + '}')
            i += 1
            continue
        if line.startswith('## '):
            flush_itemize()
            out.append(r'\subsection{' + escape_latex(line[3:].strip()) + '}')
            i += 1
            continue
        if line.startswith('# '):
            flush_itemize()
            out.append(r'\section{' + escape_latex(line[2:].strip()) + '}')
            i += 1
            continue

        # 列表项
        if re.match(r'^\s*([-*•])\s+', line):
            if not in_itemize:
                out.append(r'\begin{itemize}')
                in_itemize = True
            item_text = re.sub(r'^\s*([-*•])\s+', '', line)
            out.append(r'\item ' + escape_latex(item_text))
            i += 1
            continue
        else:
            flush_itemize()

        # 行内代码 `code`
        def repl_inline_code(m):
            inner = m.group(1)
            # 在 \texttt{} 里只做最小替换，避免大范围转义破坏等宽体
            inner = inner.replace('\\', r'\textbackslash{}')
            inner = inner.replace('{', r'\{').replace('}', r'\}')
            return r'\texttt{' + inner + '}'

        line = re.sub(r'`([^`]+)`', repl_inline_code, line)

        # 普通段落转义
        if line.strip():
            out.append(escape_latex(line))
        else:
            out.append('')  # 空行保留段落

        i += 1

    flush_itemize()
    return '\n'.join(out)


def wrap_into_template(body: str, chinese: bool = True) -> str:
    """
    把正文塞进一个安全的 LaTeX 模板里：
    - chinese=True 时：用 fontspec + 系统中文字体（macOS：PingFang SC）
    - 不依赖 minted 等需要 shell-escape 的包
    """
    if chinese:
        return r"""
\documentclass[11pt]{article}
\usepackage{fontspec}
\setmainfont{Times New Roman}
\newfontfamily\cnfont{PingFang SC}  % macOS 常见中文字体
\usepackage{geometry}
\geometry{a4paper,margin=1in}
\usepackage[colorlinks=true,linkcolor=blue,urlcolor=blue]{hyperref}
\setlength{\parskip}{6pt}
\begin{document}
{\cnfont
""" + body + r"""
}
\end{document}
"""
    else:
        return r"""
\documentclass[11pt]{article}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{geometry}
\geometry{a4paper,margin=1in}
\usepackage[colorlinks=true,linkcolor=blue,urlcolor=blue]{hyperref}
\setlength{\parskip}{6pt}
\begin{document}
""" + body + r"""
\end{document}
"""