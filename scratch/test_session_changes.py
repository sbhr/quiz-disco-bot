import os
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock

# プロジェクトルートを Python パスに追加
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import discord
from core.session import QuizSession

class TestSessionChanges(unittest.TestCase):
    def setUp(self):
        # モックの作成
        self.cog = MagicMock()
        self.cog.voice_manager = AsyncMock()
        self.cog.question_store = MagicMock()
        self.cog.score_manager = MagicMock()
        self.cog.answer_receiver = AsyncMock()
        self.cog.answer_validator = AsyncMock()
        self.cog.registered_participants = set()
        
        self.interaction = MagicMock(spec=discord.Interaction)
        self.interaction.user = MagicMock()
        self.interaction.user.voice = MagicMock()
        self.interaction.user.voice.channel = MagicMock()
        self.interaction.response = MagicMock()
        self.interaction.response.is_done = MagicMock(return_value=True)
        self.interaction.followup = AsyncMock()
        
        # チャンネルのモック
        self.channel = AsyncMock()
        self.interaction.channel = self.channel

    def test_session_embed_and_interval(self):
        # セッションの初期化
        session = QuizSession(
            cog=self.cog,
            interaction=self.interaction,
            rule="total_n",
            value=1,
            genre="GenreA",
            penalty=0,
            unique=True
        )

        # 1. 待機秒数とメッセージが5秒になっているか検証
        # session.py の 283-284行目に相当する箇所のダミー検証またはソースコード解析
        with open("core/session.py", "r", encoding="utf-8") as f:
            code = f.read()
        
        self.assertIn('"次の問題まで 5秒..."', code, "待機メッセージが '次の問題まで 5秒...' になっていません")
        self.assertIn("await asyncio.sleep(5)", code, "待機処理が 'await asyncio.sleep(5)' になっていません")
        self.assertNotIn('"次の問題まで 3秒..."', code, "古い待機メッセージ '次の問題まで 3秒...' が残っています")
        self.assertNotIn("await asyncio.sleep(3)", code, "古い待機処理 'await asyncio.sleep(3)' が残っています")

        # 2. 正解・全員不正解・時間切れの各箇所で Embed に "問題文" フィールドが追加されているかソースコードから検出
        # 各 Embed で embed.add_field(name="問題文", value=question_text, inline=False) が追加されているか検証
        embed_count = code.count('embed.add_field(name="問題文", value=question_text, inline=False)')
        self.assertEqual(embed_count, 5, f"結果発表用の5つのEmbedすべてに '問題文' フィールドが追加されている必要があります。見つかった数: {embed_count}")

        print("✅ core/session.py の変更（問題文の表示および5秒の待機処理）が正常に適用されていることを確認しました！")

if __name__ == "__main__":
    unittest.main()
