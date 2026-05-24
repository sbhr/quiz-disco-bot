import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import time
from core.question import QuestionStore
from core.score import ScoreManager
from core.voice import VoiceManager
from core.answer import AnswerReceiver, AnswerValidator
from core.session import QuizSession

class FastestFingerView(discord.ui.View):
    def __init__(self, session, timeout: float | None, answered_users: set, allowed_users: set):
        super().__init__(timeout=timeout)
        self.session = session
        self.cog = session.cog
        self.pressed_user = None
        self.pressed = False
        self.answered_users = answered_users
        self.allowed_users = allowed_users
        self.all_done = False

    @discord.ui.button(label="早押し！", style=discord.ButtonStyle.danger, emoji="🔴")
    async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.allowed_users:
            await interaction.response.send_message("あなたは参加者ではありません！", ephemeral=True)
            return

        if interaction.user.id in self.answered_users:
            await interaction.response.send_message("あなたは既に回答済みです！", ephemeral=True)
            return

        # お手つきペナルティのチェック
        if interaction.user.id in self.session.frozen_users:
            remaining = self.session.frozen_users[interaction.user.id] - time.time()
            if remaining > 0:
                await interaction.response.send_message(f"お手つきペナルティ中です！ あと {remaining:.1f} 秒待ってください。", ephemeral=True)
                return

        if self.pressed:
            await interaction.response.send_message("既に他の人が押しています！", ephemeral=True)
            return
            
        self.pressed = True
        self.pressed_user = interaction.user
        self.pressed_time = time.time()
        
        # 全ボタンを無効化
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="降参する", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def surrender_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.allowed_users:
            await interaction.response.send_message("あなたは参加者ではありません！", ephemeral=True)
            return

        if interaction.user.id in self.answered_users:
            await interaction.response.send_message("あなたは既に回答済み（または降参済み）です！", ephemeral=True)
            return

        self.answered_users.add(interaction.user.id)
        
        if len(self.allowed_users) > 0 and len(self.answered_users) >= len(self.allowed_users):
            await interaction.response.send_message(f"🏳️ **{interaction.user.display_name}** さんが降参しました。全員が回答・降参したため終了します。")
            self.all_done = True
            self.stop()
        else:
            await interaction.response.send_message(f"🏳️ **{interaction.user.display_name}** さんが降参しました。")

    @discord.ui.button(label="終了する", style=discord.ButtonStyle.secondary, emoji="⏹️")
    async def stop_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.allowed_users:
            await interaction.response.send_message("参加者以外はクイズを終了できません。", ephemeral=True)
            return

        self.cog.force_stop = True
        self.session.force_stop = True
        await interaction.response.send_message(f"🛑 **{interaction.user.display_name}** さんがクイズの終了をリクエストしました。")
        self.stop()

class RecruitView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    def get_participants_text(self, guild):
        if not self.cog.registered_participants:
            return "現在参加者はいません。"
        
        members = []
        for user_id in self.cog.registered_participants:
            member = guild.get_member(user_id)
            if member:
                members.append(member.display_name)
            else:
                members.append(f"Unknown (ID: {user_id})")
                
        return "\n".join([f"- {name}" for name in members])

    @discord.ui.button(label="参加する", style=discord.ButtonStyle.success, emoji="🟢")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.registered_participants.add(interaction.user.id)
        text = self.get_participants_text(interaction.guild)
        await interaction.response.edit_message(content=f"**クイズ参加者募集！**\n以下のボタンで参加・辞退を選んでください。\n\n**現在の参加予定者 ({len(self.cog.registered_participants)}名):**\n{text}", view=self)

    @discord.ui.button(label="辞退する", style=discord.ButtonStyle.secondary, emoji="🔴")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.cog.registered_participants:
            self.cog.registered_participants.remove(interaction.user.id)
        text = self.get_participants_text(interaction.guild)
        await interaction.response.edit_message(content=f"**クイズ参加者募集！**\n以下のボタンで参加・辞退を選んでください。\n\n**現在の参加予定者 ({len(self.cog.registered_participants)}名):**\n{text}", view=self)

class GenreSelectView(discord.ui.View):
    def __init__(self, cog, original_interaction, rule, value, penalty, unique=True, voice_answer=False):
        super().__init__(timeout=60)
        self.cog = cog
        self.original_interaction = original_interaction
        self.rule = rule
        self.value = value
        self.penalty = penalty
        self.unique = unique
        self.voice_answer = voice_answer
        
        genres = list(self.cog.question_store.questions_by_genre.keys())
        genres = sorted(genres)
        
        for genre_name in genres[:24]:
            button = discord.ui.Button(label=genre_name, style=discord.ButtonStyle.primary)
            button.callback = self.create_callback(genre_name)
            self.add_item(button)
            
        all_button = discord.ui.Button(label="すべて", style=discord.ButtonStyle.success)
        all_button.callback = self.create_callback("all")
        self.add_item(all_button)

    def create_callback(self, genre):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.original_interaction.user.id:
                await interaction.response.send_message("コマンドを実行した本人しか操作できません。", ephemeral=True)
                return
            
            for item in self.children:
                item.disabled = True
            rule_text = f"{self.value} ポイント先取" if self.rule == "first_to_n" else f"全 {self.value} 問"
            await interaction.response.edit_message(content=f"ルール: **{rule_text}** / ジャンル **{genre}** で開始します...", view=self)
            
            await self.cog.start_quiz_session(interaction, self.rule, self.value, genre, self.penalty, self.unique, self.voice_answer)
            
        return callback

class QuizCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.question_store = QuestionStore("data")
        self.score_manager = ScoreManager()
        self.voice_manager = VoiceManager(bot)
        self.answer_receiver = AnswerReceiver(bot)
        self.answer_validator = AnswerValidator(threshold=80)
        
        self.current_quiz_active = False
        self.force_stop = False
        self.registered_participants = set()
        self.current_session = None

    @app_commands.command(name="recruit", description="クイズの参加者を募集するパネルを表示します")
    async def recruit_participants(self, interaction: discord.Interaction):
        self.registered_participants.clear()
        view = RecruitView(self)
        text = view.get_participants_text(interaction.guild)
        await interaction.response.send_message(content=f"**クイズ参加者募集！**\n以下のボタンで参加・辞退を選んでください。\n\n**現在の参加予定者 (0名):**\n{text}", view=view)

    @app_commands.command(name="stop_quiz", description="進行中のクイズセッションを強制終了します")
    async def stop_quiz(self, interaction: discord.Interaction):
        if not self.current_quiz_active or not self.current_session:
            await interaction.response.send_message("現在進行中のクイズはありません。", ephemeral=True)
            return
            
        self.force_stop = True
        self.current_session.force_stop = True
        await interaction.response.send_message("クイズの強制終了リクエストを受け付けました。現在の問題が終わると終了します。")

    @app_commands.command(name="stats", description="累計成績を表示します")
    async def stats(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        stats = self.score_manager.get_lifetime_stats(target.id)
        
        embed = discord.Embed(
            title=f"📊 {target.display_name} さんの通算成績",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="累計正解数", value=f"{stats['lifetime_score']} 問", inline=True)
        embed.add_field(name="優勝回数", value=f"{stats['total_wins']} 回", inline=True)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unmute_all", description="ボイスチャンネル内の全員のミュートを強制解除します")
    async def unmute_all(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("ボイスチャンネルに参加してから実行してください。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        vc = interaction.user.voice.channel
        unmuted_count = 0
        for member in vc.members:
            if not member.bot and member.voice and member.voice.mute:
                try:
                    await member.edit(mute=False, reason="緊急ミュート解除")
                    unmuted_count += 1
                except Exception as e:
                    print(f"Failed to unmute {member.name} in slash command: {e}")

        await interaction.followup.send(f"🔊 ボイスチャンネル内の {unmuted_count} 名のサーバーミュートを解除しました。", ephemeral=True)

    @app_commands.command(name="quiz", description="早押しクイズを開始します")
    @app_commands.describe(
        rule="ルールの種類", 
        value="問題数または目標ポイント", 
        genre="出題するジャンル（省略するとボタンで選択）", 
        penalty="不正解時の休み時間（秒、0でなし）",
        unique="1回出た問題を出さないようにする（重複回避）か（デフォルト: True）",
        voice_answer="音声で回答するかどうか（デフォルト: False）"
    )
    @app_commands.choices(rule=[
        app_commands.Choice(name="目標ポイント先取", value="first_to_n"),
        app_commands.Choice(name="全N問", value="total_n")
    ])
    async def quiz_start(
        self, 
        interaction: discord.Interaction, 
        rule: str = "first_to_n", 
        value: int = 3, 
        genre: str = None, 
        penalty: int = 0,
        unique: bool = True,
        voice_answer: bool = False
    ):
        if self.current_quiz_active:
            await interaction.response.send_message("既にクイズが進行中です！", ephemeral=True)
            return

        if not interaction.user.voice:
            await interaction.response.send_message("ボイスチャンネルに参加してから実行してください。", ephemeral=True)
            return

        # ローカルのCSVファイルを再読み込みして、新規追加や更新を即座に反映
        self.question_store.reload_questions()

        if genre is None:
            view = GenreSelectView(self, interaction, rule, value, penalty, unique, voice_answer)
            await interaction.response.send_message("出題するジャンルを選んでください：", view=view)
        else:
            await interaction.response.defer()
            await self.start_quiz_session(interaction, rule, value, genre, penalty, unique, voice_answer)

    async def start_quiz_session(self, interaction: discord.Interaction, rule: str, value: int, genre: str, penalty: int = 0, unique: bool = True, voice_answer: bool = False):
        self.current_session = QuizSession(self, interaction, rule, value, genre, penalty, unique, voice_answer)
        self.current_quiz_active = True
        self.force_stop = False
        await self.current_session.run()


    async def end_quiz_session(self, interaction: discord.Interaction):
        # 1. セッションクリア前に参加ユーザーを抽出
        allowed_users = set()
        if self.current_session:
            allowed_users = self.current_session.allowed_users.copy()

        self.current_quiz_active = False
        self.current_session = None
        
        # 2. 参加状態の継続
        if allowed_users:
            self.registered_participants = allowed_users.copy()
        
        scores = self.score_manager.get_all_scores()
        if scores:
            sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            embed = discord.Embed(title="🏁 クイズ終了！最終ランキング", color=discord.Color.gold())
            medals = ["🥇", "🥈", "🥉"]
            ranking_text = ""
            for i, (uid, score) in enumerate(sorted_scores):
                medal = medals[i] if i < 3 else "🔹"
                ranking_text += f"{medal} **{i+1}位**: <@{uid}> - {score} pts\n"
            embed.description = ranking_text
            await interaction.channel.send(embed=embed)
        else:
            await interaction.channel.send("🏁 **クイズ終了！**（スコア記録はありませんでした）")

        # 3. 募集パネルを自動表示
        view = RecruitView(self)
        text = view.get_participants_text(interaction.guild)
        await interaction.channel.send(
            content=f"**クイズ参加者募集！**\n以下のボタンで参加・辞退を選んでください。\n\n**現在の参加予定者 ({len(self.registered_participants)}名):**\n{text}",
            view=view
        )

async def setup(bot):
    await bot.add_cog(QuizCog(bot))
