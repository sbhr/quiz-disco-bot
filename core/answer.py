from thefuzz import fuzz
import discord
import asyncio

from core.ai_validator import AIAnswerValidator

class AnswerValidator:
    def __init__(self, threshold: int = 85):
        """
        threshold: 85以上のスコアは即正解とみなします。
        それ以下（かつ一定以上）の場合はAIに問い合わせます。
        """
        self.threshold = threshold
        self.ai_validator = AIAnswerValidator()

    async def validate(self, user_answer: str, correct_answer: str, question: str = "") -> bool:
        """
        Fuzzy matching と AI を組み合わせて正誤判定を行います。
        """
        # 1. 文字ベースの判定 (Fuzzy matching)
        score = fuzz.ratio(user_answer.lower(), correct_answer.lower())
        
        # スコアが非常に高い場合は即正解
        if score >= self.threshold:
            # ログ出力 (Fuzzy matchingで正解した場合)
            self.ai_validator._log_result(question, correct_answer, user_answer, True, f"Fuzzy({score})")
            return True
            
        # 判定が微妙な場合または文字種が異なる場合のみAIに問い合わせる (ハイブリッド判定)
        is_correct, is_error = await self.ai_validator.validate(question, correct_answer, user_answer)
        
        if is_error:
            # AIがエラー（クォータ制限など）の場合は、Fuzzy Matchingのしきい値を下げてフォールバックする
            # partial_ratioを使用して、部分一致でも高ければ正解とする
            fallback_score = fuzz.partial_ratio(user_answer.lower(), correct_answer.lower())
            if fallback_score >= 80:
                self.ai_validator._log_result(question, correct_answer, user_answer, True, f"AI_Fallback_Fuzzy({fallback_score})")
                return True
        
        return is_correct

class AnswerReceiver:
    def __init__(self, bot):
        self.bot = bot

    async def wait_for_answer(self, channel: discord.TextChannel, user: discord.Member, timeout: float = 10.0) -> str:
        """
        Wait for a text answer from a specific user in a specific channel.
        In the future, this could be extended to wait for an audio transcript.
        """
        def check(m: discord.Message):
            return m.author == user and m.channel == channel

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=timeout)
            return msg.content
        except asyncio.TimeoutError:
            return None
