from thefuzz import fuzz
import discord
import asyncio

class AnswerValidator:
    def __init__(self, threshold: int = 80):
        """
        threshold: The similarity score (0-100) required to pass.
        80 is usually a good starting point to allow 1 character difference in short strings.
        """
        self.threshold = threshold

    def validate(self, user_answer: str, correct_answer: str) -> bool:
        """
        Compares user_answer with correct_answer using fuzzy matching.
        """
        # fuzz.ratio computes the standard Levenshtein distance similarity ratio
        score = fuzz.ratio(user_answer.lower(), correct_answer.lower())
        return score >= self.threshold

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
