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
            
            return is_correct, False
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            print(f"Error during AI validation: {error_msg}")
            # ログ出力 (エラー)
            self._log_result(question, correct_answer, user_answer, False, f"AI_ERROR ({error_msg})")
            return False, True

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

    async def validate_voice(self, audio_file_path: str, correct_answer: str, question: str = "") -> tuple[str, bool]:
        """
        音声ファイルを読み込み、Geminiを使用して文字起こしと正誤判定を同時に行います。
        (transcript, correct) のタプルを返します。
        """
        if not self.client:
            return "", False

        from pydantic import BaseModel
        class VoiceAnswerResult(BaseModel):
            transcript: str
            correct: bool

        prompt = f"""
あなたはクイズの正誤判定および音声書き起こしのアシスタントです。
提供されたユーザーの音声ファイルを聴き、以下のステップで判定を行ってください。

【極めて重要な注意点】
提供された音声が無音である、または雑音のみで言葉が聞き取れない（発話がない）場合は、絶対に正解例から答えを類推して文字起こしを捏造しないでください。
音声内に言葉が聞き取れない場合：
- "transcript" は必ず空文字 "" にしてください。
- "correct" は必ず False にしてください。

1. 【文字起こし】
ユーザーの音声を日本語で文字起こししてください。多少のノイズや言いよどみは無視し、実際に発話された回答部分のみを抽出してください。

2. 【正誤判定】
文字起こししたユーザーの回答が、以下の「問題」および「正解例」に対して意味的に正しいかどうかを判定してください。

【正誤判定の基準】
- 漢字、ひらがな、カタカナの違いは正解としてください（例：「富士山」と「ふじさん」、「スイギュウ」と「水牛」、「テンシンハン」と「天津飯」はすべて正解）。
- アルファベットの大小文字、全角半角の違いは正解としてください。
- 英語名とカタカナ名の対応は正解としてください（例：「Coke ON」と「コークオン」は正解）。
- 正解例に含まれる「（ ）」や「( )」内の記述は、読み方、別名、または補足情報です。
  ユーザーの回答が括弧の外側の部分、括弧内の部分、あるいはその両方を組み合わせたものと一致すれば正解としてください。
- 多少の言い回しの違い、省略、通称も正解としてください（例：「太宰治」と「太宰」は正解）。
- 誤字脱字・聞き取りエラーがあっても、文脈上明らかに同じものを指していると判断できれば正解としてください。
- 意味が全く異なる、あるいは不十分な場合は不正解としてください。

【クイズ情報】
問題: {question}
正解例: {correct_answer}

【出力形式】
JSON形式のみで出力してください。
"""

        try:
            with open(audio_file_path, "rb") as f:
                audio_bytes = f.read()

            from google.genai import types

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=[
                    prompt,
                    types.Part.from_bytes(
                        data=audio_bytes,
                        mime_type="audio/wav"
                    )
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=VoiceAnswerResult,
                )
            )

            # JSONのパース
            result_data = json.loads(response.text)
            transcript = result_data.get("transcript", "")
            is_correct = result_data.get("correct", False)

            # ログ出力
            self._log_result(question, correct_answer, f"[Voice] {transcript}", is_correct, "AI_Voice")

            return transcript, is_correct
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            print(f"Error during AI voice validation: {error_msg}")
            # エラーログ
            self._log_result(question, correct_answer, "[Voice Error]", False, f"AI_Voice_ERROR ({error_msg})")
            return "", False
