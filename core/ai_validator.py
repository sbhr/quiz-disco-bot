import os
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
- 漢字、ひらがな、カタカナの違いは正解としてください（例：「富士山」と「ふじさん」は正解）。
- 多少の言い回しの違い、省略、通称も正解としてください（例：「太宰治」と「太宰」は正解）。
- 誤字脱字があっても、意味が明らかに一致していれば正解としてください。
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
            return "true" in result_text
        except Exception as e:
            print(f"Error during AI validation: {e}")
            return False
