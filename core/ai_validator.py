import os
import json
from datetime import datetime
import discord
from google import genai
from dotenv import load_dotenv

load_dotenv()

class AIAnswerValidator:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            self.client = None
            print("Warning: GEMINI_API_KEY not found in environment variables.")
            return

        self.model_id = 'gemini-flash-latest'
        self.client = genai.Client(api_key=api_key)
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    async def validate(self, question: str, correct_answer: str, user_answer: str) -> bool:
        """
        AI (Gemini) を使用して回答の正誤を判定します。
        """
        if not self.client:
            return False

        prompt = f"""
あなたはクイズの正誤判定アシスタントです。
以下の「問題」「正解例」「ユーザーの回答」を比較して、ユーザーの回答が意味的に正しいかどうかを判定してください。

【判定基準】
- 漢字、ひらがな、カタカナの違いは正解としてください（例：「富士山」と「ふじさん」、「スイギュウ」と「水牛」、「テンシンハン」と「天津飯」はすべて正解）。
- アルファベットの大小文字、全角半角の違いは正解としてください。
- 英語名とカタカナ名の対応は正解としてください（例：「Coke ON」と「コークオン」は正解）。
- 正解例に含まれる「（ ）」や「( )」内の記述は、読み方、別名、または補足情報です。
  ユーザーの回答が括弧の外側の部分、括弧内の部分、あるいはその両方を組み合わせたものと一致すれば正解としてください。
  例：正解例が「相田（あいだ）みつを」の場合、「相田みつを」も「あいだみつを」も正解です。
  例：正解例が「Coke ON(コークオン)」の場合、「coke on」も「コークオン」も正解です。
  例：正解例が「天津飯（てんしんはん）」の場合、「天津飯」も「てんしんはん」も「テンシンハン」も正解です。
- 多少の言い回しの違い、省略、通称も正解としてください（例：「太宰治」と「太宰」は正解）。
- 誤字脱字があっても、人間が読んで明らかに同じものを指していると判断できれば正解としてください。
- 意味が全く異なる、あるいは不十分な場合は不正解としてください。

【入力】
問題: {question}
正解例: {correct_answer}
ユーザーの回答: {user_answer}

【出力形式】
判定結果のみを "True" または "False" で出力してください。余計な解説は不要です。
"""

        try:
            # google-genai client calls are synchronous by default in this library version
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            result_text = response.text.strip().lower()
            is_correct = "true" in result_text
            
            # ログ出力 (成功)
            self._log_result(question, correct_answer, user_answer, is_correct, "AI")
            
            return is_correct
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            print(f"Error during AI validation: {error_msg}")
            # ログ出力 (エラー)
            self._log_result(question, correct_answer, user_answer, False, f"AI_ERROR ({error_msg})")
            return False

    def _log_result(self, question: str, correct_answer: str, user_answer: str, result: bool, method: str):
        """
        判定結果をJSONL形式でログファイルに保存します。
        """
        # プロジェクトルートに logs ディレクトリを作成
        log_dir = os.path.join(self.base_dir, "logs")
        try:
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
                
            log_file = os.path.join(log_dir, "answer_validation.jsonl")
            log_data = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "method": method,
                "result": result,
                "question": question,
                "correct_answer": correct_answer,
                "user_answer": user_answer
            }
            
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_data, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"Failed to write log: {e}")
