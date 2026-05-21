import os
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock

# プロジェクトルートを Python パスに追加
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import discord
from cogs.quiz import QuizCog
from core.session import QuizSession

class TestParticipantRetention(unittest.TestCase):
    def setUp(self):
        # Botのモック
        self.bot = MagicMock()
        
        # QuizCogのインスタンス化
        self.cog = QuizCog(self.bot)
        
        # InteractionとChannelのモック
        self.interaction = MagicMock(spec=discord.Interaction)
        self.interaction.user = MagicMock()
        self.interaction.user.voice = MagicMock()
        self.interaction.user.voice.channel = MagicMock()
        
        self.channel = AsyncMock()
        self.interaction.channel = self.channel
        
        # Guildのモック
        self.guild = MagicMock()
        self.guild.get_member = MagicMock(side_effect=lambda uid: MagicMock(display_name=f"User{uid}"))
        self.interaction.guild = self.guild

    def test_end_quiz_session_retains_participants_and_sends_recruit(self):
        # セッションおよびスコアのモックを設定
        session = MagicMock(spec=QuizSession)
        session.allowed_users = {12345, 67890}
        self.cog.current_session = session
        self.cog.current_quiz_active = True
        
        # スコアマネージャーの戻り値モック
        self.cog.score_manager.get_all_scores = MagicMock(return_value={12345: 3, 67890: 1})
        
        # end_quiz_sessionを実行
        import asyncio
        asyncio.run(self.cog.end_quiz_session(self.interaction))
        
        # アサーション
        # 1. 現在のセッションとアクティブフラグがリセットされること
        self.assertFalse(self.cog.current_quiz_active)
        self.assertIsNone(self.cog.current_session)
        
        # 2. セッションの allowed_users が registered_participants に維持されること
        self.assertEqual(self.cog.registered_participants, {12345, 67890})
        
        # 3. 2つのメッセージ（ランキングと募集パネル）が送信されること
        self.assertEqual(self.channel.send.call_count, 2)
        
        # 最初のメッセージ（ランキングEmbed）の検証
        first_call_args, first_call_kwargs = self.channel.send.call_args_list[0]
        self.assertIn("embed", first_call_kwargs)
        embed = first_call_kwargs["embed"]
        self.assertEqual(embed.title, "🏁 クイズ終了！最終ランキング")
        
        # 2番目のメッセージ（募集パネル）の検証
        second_call_args, second_call_kwargs = self.channel.send.call_args_list[1]
        self.assertIn("content", second_call_kwargs)
        self.assertIn("view", second_call_kwargs)
        self.assertIn("クイズ参加者募集！", second_call_kwargs["content"])
        self.assertIn("現在の参加予定者 (2名):", second_call_kwargs["content"])
        self.assertIn("- User12345", second_call_kwargs["content"])
        self.assertIn("- User67890", second_call_kwargs["content"])

if __name__ == "__main__":
    unittest.main()
