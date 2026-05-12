import asyncio
import os
import sys

# プロジェクトのルートをパスに追加
sys.path.append(os.getcwd())

from core.answer import AnswerValidator
import core.answer
print(f"DEBUG: core.answer location: {core.answer.__file__}")

async def test_validation():
    validator = AnswerValidator()
    
    test_cases = [
        {
            "question": "「恋をしたのだ。そんなことは、全くはじめてであった。」という書き出しで始まる、杉基イクラの漫画『ナナマル サンバツ』の主人公は誰？",
            "correct": "越山識",
            "user": "こしやましき",
            "expected": True,
            "desc": "ひらがな判定"
        },
        {
            "question": "代表曲に『虹を編めたら』や『青空のラプソディ』がある音楽グループは何でしょう?",
            "correct": "fhána",
            "user": "ファナ",
            "expected": True,
            "desc": "カタカナ読み"
        },
        {
            "question": "夏目漱石の小説『坊っちゃん』の舞台はどこ？",
            "correct": "愛媛県松山市",
            "user": "松山",
            "expected": True,
            "desc": "省略形"
        },
        {
            "question": "日本の首都は？",
            "correct": "東京",
            "user": "大阪",
            "expected": False,
            "desc": "明らかに間違い"
        }
    ]

    print("--- AI Validation Test Start ---")
    for case in test_cases:
        result = await validator.validate(case["user"], case["correct"], case["question"])
        status = "✅ PASS" if result == case["expected"] else "❌ FAIL"
        print(f"[{case['desc']}] User: {case['user']} | Correct: {case['correct']} | Result: {result} | {status}")
    print("--- Test End ---")

if __name__ == "__main__":
    asyncio.run(test_validation())
