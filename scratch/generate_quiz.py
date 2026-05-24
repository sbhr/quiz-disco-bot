import os
import csv
import sys
import argparse
import json
import time
import re
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# プロジェクトルートにパスを追加
sys.path.append(os.getcwd())

# 環境変数のロード
load_dotenv()

# Pydanticスキーマ定義（生成用）
class QuizQuestion(BaseModel):
    question: str = Field(
        description="早押しクイズの問題文。早押し用に聞き取りやすく、文章が進むにつれてヒントが徐々に具体的になるような構成。"
    )
    answer: str = Field(
        description="正確で簡潔な正解名（例: '富士山'、'夏目漱石' などの固有名詞、あるいは一般的な単語）。"
    )
    explanation: str = Field(
        description="正解に関する追加の興味深い事実や補足説明。"
    )

# Pydanticスキーマ定義（検証用）
class VerificationResult(BaseModel):
    is_valid: bool = Field(
        description="問題の事実関係が100%正確で、かつ答えが1つに絞り込める（曖昧さがない）場合は True。少しでも誤りや曖昧さがある場合は False。"
    )
    feedback: str = Field(
        description="問題に欠陥がある場合、その具体的な理由や事実誤認の指摘（欠陥がない場合は空文字）。"
    )
    corrected_question: str = Field(
        description="事実誤認や曖昧さを完全に修正・書き直した新しい問題文（欠陥がない場合は空文字）。"
    )
    corrected_answer: str = Field(
        description="修正後の正確な正解名（欠陥がない場合は空文字）。"
    )
    corrected_explanation: str = Field(
        description="修正後の正確な解説（欠陥がない場合は空文字）。"
    )

class QuizGenerator:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("Error: GEMINI_API_KEY not found in environment variables.")
            sys.exit(1)
        self.client = genai.Client(api_key=api_key)
        self.model_id = 'gemini-flash-latest'

    def _call_api_with_retry(self, prompt: str, schema) -> str:
        """API呼び出しをラップし、429エラーが発生した際に自動的にリトライします"""
        max_retries = 5
        base_delay = 15.0
        
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema,
                    )
                )
                return response.text
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    delay = base_delay
                    # "Please retry in 47.89s" から数値部分をパース
                    match = re.search(r"Please retry in ([\d\.]+)s", err_str)
                    if match:
                        delay = float(match.group(1)) + 2.0
                    else:
                        # "retryDelay': '47s'" などからパース
                        match_sec = re.search(r"retryDelay':\s*'(\d+)s'", err_str)
                        if match_sec:
                            delay = float(match_sec.group(1)) + 2.0
                    
                    print(f"  ⚠️ APIレートリミット(429)を検知しました。{delay:.1f} 秒間待機して再試行します (試行 {attempt + 1}/{max_retries})...")
                    time.sleep(delay)
                else:
                    raise e
        raise Exception("API呼び出しがレートリミットにより上限回数を超えました。")

    def generate_single_raw_question(self, theme: str, question_num: int, exclude_list: list[str]) -> QuizQuestion:
        """指定されたテーマに沿ったクイズのラフ案を1問生成します"""
        exclude_str = "\n".join([f"- {q}" for q in exclude_list])
        
        prompt = f"""
あなたはプロのクイズ作家です。テーマ「{theme}」に関する面白い早押しクイズ問題を1問作成してください。

【クイズ作成のルール】
1. 早押し用に適した文章構成にしてください（文頭は一般的な情報から入り、文末に向かって徐々にヒントが具体的になる構成）。
2. 事実関係が客観的に証明されている、明確な事実のみを扱ってください。
3. 以下の既出問題リストにある問題や答えと、重複または極めて類似した問題は絶対に避けてください。

【既出問題・答えリスト】
{exclude_str if exclude_list else "なし"}

必ず指定されたJSON形式に沿って出力してください。
"""

        response_text = self._call_api_with_retry(prompt, QuizQuestion)
        return QuizQuestion.model_validate_json(response_text)

    def verify_and_correct_question(self, theme: str, question: QuizQuestion) -> tuple[QuizQuestion, bool, str]:
        """生成されたクイズに事実誤認や曖昧さがないかを厳しく監査し、必要に応じて修正します"""
        prompt = f"""
あなたはクイズ大会の極めて厳格な「ファクトチェッカー兼編集長」です。
テーマ「{theme}」について作成された以下のクイズ問題案の「事実関係の正確性」および「答えの一意性（別解が存在しうる曖昧さがないか）」を厳しく監査してください。

【監査対象のクイズ案】
問題文: {question.question}
正解例: {question.answer}
解説: {question.explanation}

【監査基準】
- 歴史的事件の年号、人名、科学的事実、作品名などに少しでも事実誤認（ハルシネーション）がないか？
- 問題文の情報から、正解例の答えが100%一意に決定されるか？（他の解釈や別解が成立してしまう曖昧な問題になっていないか？）
- 読み上げクイズとして日本語が極めて美しく、聞き取りやすいか？

少しでも事実関係の誤りや曖昧さ、日本語の不自然さがある場合は、「不合格 (is_valid = False)」とし、完璧に事実確認・ファクトチェックを施した正確な問題文・正解・解説へと完全に修正・書き直しを行ってください。
完全に合格の場合は、「合格 (is_valid = True)」とし、修正データは空文字にしてください。
"""

        response_text = self._call_api_with_retry(prompt, VerificationResult)
        verify_res = VerificationResult.model_validate_json(response_text)
        
        if not verify_res.is_valid:
            # 修正データが適用可能な場合は修正データを返す
            corrected = QuizQuestion(
                question=verify_res.corrected_question if verify_res.corrected_question else question.question,
                answer=verify_res.corrected_answer if verify_res.corrected_answer else question.answer,
                explanation=verify_res.corrected_explanation if verify_res.corrected_explanation else question.explanation
            )
            return corrected, False, verify_res.feedback
        
        return question, True, ""

    def generate_precise_quiz_set(self, theme: str, num_questions: int) -> list[QuizQuestion]:
        """テーマに沿った高精度なクイズセットを指定された問題数分、順次生成・監査します"""
        verified_questions = []
        exclude_list = []
        
        print(f"\n🚀 クイズ自動生成スタート (テーマ: 「{theme}」 / 生成目標: {num_questions} 問)")
        print("==================================================")
        
        q_count = 0
        attempts = 0
        max_attempts = num_questions * 2  # 無限ループ防止用の最大試行回数
        
        while len(verified_questions) < num_questions and attempts < max_attempts:
            attempts += 1
            current_num = len(verified_questions) + 1
            print(f"\n[第 {current_num} 問] ラフ案を生成中...")
            
            try:
                # 1. クイズの生成
                raw_q = self.generate_single_raw_question(theme, current_num, exclude_list)
                print(f"  📝 生成された案: Answer = 「{raw_q.answer}」")
                
                # 2. ファクトチェック監査と自己修正
                print("  🔍 ファクトチェックによる監査を実行中...")
                verified_q, is_valid, feedback = self.verify_and_correct_question(theme, raw_q)
                
                if is_valid:
                    print(f"  ✅ [監査合格] 事実確認OK。品質に問題ありません。")
                else:
                    print(f"  ⚠️ [監査不合格] 事実関係の誤り、または曖昧さを検知しました。")
                    print(f"  📝 指摘内容: {feedback}")
                    print(f"  ⚡ [自動修正適用] 修正後の正解: 「{verified_q.answer}」")
                
                # 3. リストに追加
                verified_questions.append(verified_q)
                exclude_list.append(verified_q.answer)
                exclude_list.append(verified_q.question[:30]) # 部分一致重複防止用
                
                print(f"  ✨ 第 {current_num} 問の生成・監査が完了しました！")
                
                # APIのクォータ消費を緩やかにするため、生成後に少しウェイトを入れる
                time.sleep(2)
                
            except Exception as e:
                print(f"  ❌ 処理中にエラーが発生しました。スキップして再試行します: {e}")
                continue
                
        print("\n==================================================")
        print(f"🎉 クイズの生成・監査がすべて完了しました！ (成功: {len(verified_questions)} / 試行: {attempts})")
        return verified_questions

def main():
    parser = argparse.ArgumentParser(description="Geminiの自己検証モデルを用いた高精度クイズ自動生成スクリプト")
    parser.add_argument("--theme", type=str, required=True, help="クイズのテーマ（例: ポケモン、日本の歴史）")
    parser.add_argument("--num", type=int, default=10, help="生成するクイズ問題数 (デフォルト: 10)")
    args = parser.parse_args()

    # 出力先の決定
    output_dir = "data"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    csv_filename = f"{args.theme}.csv"
    csv_path = os.path.join(output_dir, csv_filename)

    # クイズ生成の実行
    generator = QuizGenerator()
    quiz_set = generator.generate_precise_quiz_set(args.theme, args.num)

    if not quiz_set:
        print("クイズ問題の生成に失敗しました。")
        sys.exit(1)

    # CSVファイルへの書き出し
    print(f"\n💾 ファイルに保存中: {csv_path}")
    try:
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["question", "answer", "explanation"])
            for q in quiz_set:
                writer.writerow([q.question, q.answer, q.explanation])
        print(f"✨ 正常に保存されました！既存のBot上で `/quiz` コマンドを実行し、ジャンル「{args.theme}」を選択して遊べます！")
    except Exception as e:
        print(f"ファイルの保存に失敗しました: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
