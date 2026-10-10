"""小程序的 JS 语法兜底检查：括号/引号配平 + 常见错误。

没有 node 环境（本机未安装），无法用真正的 JS 解析器，
所以用一个状态机跳过字符串与注释后检查分隔符配平。
这只能抓住「括号写错」这类最常见的破坏，不能替代真正运行，
但比完全不检查要好。

用法：
    C:/Plant/plant-ai/venv/Scripts/python.exe tests/js_syntax_check.py
"""

import glob
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = "C:/Plant/绿植智能养护系统/zhwu"
PAIRS = {")": "(", "]": "[", "}": "{"}
BACKSLASH = "\\"


def check(path):
    src = open(path, encoding="utf-8").read()
    i, n, line = 0, len(src), 1
    stack = []

    while i < n:
        ch = src[i]

        if ch == "\n":
            line += 1
            i += 1
            continue

        # 行注释
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue

        # 块注释
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                if src[i] == "\n":
                    line += 1
                i += 1
            i += 2
            continue

        # 字符串（含模板串，模板串里的 ${} 这里不展开，够用）
        if ch in "'\"`":
            quote = ch
            i += 1
            while i < n:
                if src[i] == BACKSLASH:
                    i += 2
                    continue
                if src[i] == quote:
                    i += 1
                    break
                if src[i] == "\n":
                    line += 1
                i += 1
            continue

        if ch in "([{":
            stack.append((ch, line))
        elif ch in ")]}":
            if not stack or stack[-1][0] != PAIRS[ch]:
                return f"第 {line} 行：多余的 {ch}"
            stack.pop()

        i += 1

    if stack:
        return f"未闭合的 {stack[-1][0]}（从第 {stack[-1][1]} 行开始）"
    return None


def main():
    os.chdir(ROOT)
    files = (sorted(glob.glob("pages/*/*.js"))
             + sorted(glob.glob("utils/*.js"))
             + sorted(glob.glob("*.js")))
    bad = 0
    for f in files:
        err = check(f)
        if err:
            bad += 1
            print(f"  [失败] {f}: {err}")
        else:
            print(f"  [通过] {f}")
    print()
    print(f"共检查 {len(files)} 个 JS 文件，异常 {bad} 个")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
