import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import time
from core.question import QuestionStore
from core.score import ScoreManager
from core.voice import VoiceManager
from core.answer import AnswerReceiver, AnswerValidator
from core.session import QuizSession, IntroQuizSession

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

        # 失格のチェック
        if interaction.user.id in self.session.disqualified_users:
            await interaction.response.send_message("❌ あなたは失格となったため、回答できません。", ephemeral=True)
            return

        # お手つきペナルティのチェック
        if interaction.user.id in self.session.frozen_users:
            if self.session.penalty_type == "time":
                remaining = self.session.frozen_users[interaction.user.id] - time.time()
                if remaining > 0:
                    await interaction.response.send_message(f"⌛ お手つきペナルティ中です！ あと {remaining:.1f} 秒待ってください。", ephemeral=True)
                    return
            elif self.session.penalty_type == "skip":
                target_q = self.session.frozen_users[interaction.user.id]
                current_q = self.session.questions_asked
                if current_q <= target_q:
                    remaining_qs = target_q - current_q + 1
                    await interaction.response.send_message(f"⌛ お手つきペナルティ中です！ 次の {remaining_qs} 問回答できません (第 {target_q + 1} 問から復帰可能)。", ephemeral=True)
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
    def __init__(self, cog, original_interaction, rule, value, penalty_type, penalty_value, unique=True, is_intro=False):
        super().__init__(timeout=60)
        self.cog = cog
        self.original_interaction = original_interaction
        self.rule = rule
        self.value = value
        self.penalty_type = penalty_type
        self.penalty_value = penalty_value
        self.unique = unique
        self.is_intro = is_intro
        
        store = self.cog.intro_question_store if is_intro else self.cog.question_store
        self.genres = sorted(list(store.questions_by_genre.keys()))
        self.page = 0
        self.items_per_page = 20
        
        self.update_items()

    def get_settings_text(self):
        rule_text = f"{self.value} ポイント先取" if self.rule == "first_to_n" else f"全 {self.value} 問"
        if self.penalty_type == "none":
            penalty_text = "なし"
        elif self.penalty_type == "time":
            penalty_text = f"{self.penalty_value}秒休み"
        elif self.penalty_type == "skip":
            penalty_text = f"次の{self.penalty_value}問休み"
        elif self.penalty_type == "disqualify":
            penalty_text = f"{self.penalty_value}回で失格"
        else:
            penalty_text = "なし"
        unique_text = "する" if self.unique else "しない"
        return f"💡 現在の設定\nルール: **{rule_text}** | ペナルティ: **{penalty_text}** | 重複回避: **{unique_text}**"

    def update_items(self):
        self.clear_items()
        
        start = self.page * self.items_per_page
        end = start + self.items_per_page
        page_genres = self.genres[start:end]
        
        # Add genre buttons
        for genre_name in page_genres:
            button = discord.ui.Button(label=genre_name, style=discord.ButtonStyle.primary)
            button.callback = self.create_genre_callback(genre_name)
            self.add_item(button)
            
        # Add navigation buttons
        total_pages = (len(self.genres) + self.items_per_page - 1) // self.items_per_page
        
        if self.page > 0:
            prev_button = discord.ui.Button(label="⬅️ 前のページ", style=discord.ButtonStyle.secondary)
            prev_button.callback = self.prev_page
            self.add_item(prev_button)
            
        if self.page < total_pages - 1:
            next_button = discord.ui.Button(label="次のページ ➡️", style=discord.ButtonStyle.secondary)
            next_button.callback = self.next_page
            self.add_item(next_button)
            
        # Add "すべて" button
        all_button = discord.ui.Button(label="すべて", style=discord.ButtonStyle.success)
        all_button.callback = self.create_genre_callback("all")
        self.add_item(all_button)

        # Add "前回の設定を復元" button
        if getattr(self.cog, 'last_settings', None):
            restore_button = discord.ui.Button(label="前回の設定を復元", style=discord.ButtonStyle.secondary, emoji="🔄", row=4)
            restore_button.callback = self.restore_settings
            self.add_item(restore_button)

    async def restore_settings(self, interaction: discord.Interaction):
        prev = self.cog.last_settings
        self.rule = prev.get("rule", self.rule)
        self.value = prev.get("value", self.value)
        self.penalty_type = prev.get("penalty_type", self.penalty_type)
        self.penalty_value = prev.get("penalty_value", self.penalty_value)
        self.unique = prev.get("unique", self.unique)
        
        total_pages = (len(self.genres) + self.items_per_page - 1) // self.items_per_page
        content = f"{self.get_settings_text()}\n\n出題するジャンルを選んでください (ページ {self.page + 1}/{total_pages})："
        await interaction.response.edit_message(content=content, view=self)

    def create_genre_callback(self, genre):
        async def callback(interaction: discord.Interaction):
            
            for item in self.children:
                item.disabled = True
            rule_text = f"{self.value} ポイント先取" if self.rule == "first_to_n" else f"全 {self.value} 問"
            prefix = "イントロクイズ - " if self.is_intro else ""
            await interaction.response.edit_message(content=f"ルール: **{rule_text}** / ジャンル **{prefix}{genre}** で開始します...", view=self)
            
            await self.cog.start_quiz_session(interaction, self.rule, self.value, genre, self.penalty_type, self.penalty_value, self.unique, is_intro=self.is_intro)
            
        return callback

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self.update_items()
        total_pages = (len(self.genres) + self.items_per_page - 1) // self.items_per_page
        content = f"{self.get_settings_text()}\n\n出題するジャンルを選んでください (ページ {self.page + 1}/{total_pages})："
        await interaction.response.edit_message(content=content, view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self.update_items()
        total_pages = (len(self.genres) + self.items_per_page - 1) // self.items_per_page
        content = f"{self.get_settings_text()}\n\n出題するジャンルを選んでください (ページ {self.page + 1}/{total_pages})："
        await interaction.response.edit_message(content=content, view=self)

class QuizCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.question_store = QuestionStore("data", db_path="data/quiz.db")
        self.intro_question_store = QuestionStore("data/intro", db_path="data/quiz_intro.db")
        self.score_manager = ScoreManager()
        self.voice_manager = VoiceManager(bot)
        self.answer_receiver = AnswerReceiver(bot)
        self.answer_validator = AnswerValidator(threshold=80)
        
        self.current_quiz_active = False
        self.force_stop = False
        self.registered_participants = set()
        self.last_settings = None
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
    @app_commands.rename(
        rule="ルール",
        value="設定値",
        genre="ジャンル",
        penalty_type="ペナルティの種類",
        penalty_value="ペナルティの値",
        unique="重複回避"
    )
    @app_commands.describe(
        rule="ルールの種類（目標ポイント先取、または全N問）", 
        value="目標ポイント、または出題する総問題数", 
        genre="出題するジャンル（省略するとジャンル選択ボタンを表示）", 
        penalty_type="お手つき（不正解）時のペナルティ形式",
        penalty_value="ペナルティの数値（時間休みなら秒数、問題数休みなら休み問数、失格なら最大お手つき回数）",
        unique="同じ問題を二度と出さないようにする（重複回避）か（デフォルト: True）"
    )
    @app_commands.choices(
        rule=[
            app_commands.Choice(name="目標ポイント先取", value="first_to_n"),
            app_commands.Choice(name="全N問", value="total_n")
        ],
        penalty_type=[
            app_commands.Choice(name="ペナルティなし", value="none"),
            app_commands.Choice(name="時間休み（秒）", value="time"),
            app_commands.Choice(name="問題数休み（問）", value="skip"),
            app_commands.Choice(name="お手つき回数で失格", value="disqualify")
        ]
    )
    async def quiz_start(
        self, 
        interaction: discord.Interaction, 
        rule: str = "first_to_n", 
        value: int = 3, 
        genre: str = None, 
        penalty_type: str = "none",
        penalty_value: int = 0,
        unique: bool = True
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
            view = GenreSelectView(self, interaction, rule, value, penalty_type, penalty_value, unique)
            await interaction.response.send_message(f"{view.get_settings_text()}\n\n出題するジャンルを選んでください：", view=view)
        else:
            await interaction.response.defer()
            await self.start_quiz_session(interaction, rule, value, genre, penalty_type, penalty_value, unique)

    @app_commands.command(name="intro_quiz", description="YouTubeの音源を使用した早押しイントロクイズを開始します")
    @app_commands.rename(
        rule="ルール",
        value="設定値",
        genre="ジャンル",
        penalty_type="ペナルティの種類",
        penalty_value="ペナルティの値",
        unique="重複回避"
    )
    @app_commands.describe(
        rule="ルールの種類（目標ポイント先取、または全N問）", 
        value="目標ポイント、または出題する総問題数", 
        genre="出題するジャンル（省略するとジャンル選択ボタンを表示）", 
        penalty_type="お手つき（不正解）時のペナルティ形式",
        penalty_value="ペナルティの数値（時間休みなら秒数、問題数休みなら休み問数、失格なら最大お手つき回数）",
        unique="同じ問題を二度と出さないようにする（重複回避）か（デフォルト: True）"
    )
    @app_commands.choices(
        rule=[
            app_commands.Choice(name="目標ポイント先取", value="first_to_n"),
            app_commands.Choice(name="全N問", value="total_n")
        ],
        penalty_type=[
            app_commands.Choice(name="ペナルティなし", value="none"),
            app_commands.Choice(name="時間休み（秒）", value="time"),
            app_commands.Choice(name="問題数休み（問）", value="skip"),
            app_commands.Choice(name="お手つき回数で失格", value="disqualify")
        ]
    )
    async def intro_quiz_start(
        self, 
        interaction: discord.Interaction, 
        rule: str = "first_to_n", 
        value: int = 3, 
        genre: str = None, 
        penalty_type: str = "none",
        penalty_value: int = 0,
        unique: bool = True
    ):
        if self.current_quiz_active:
            await interaction.response.send_message("既にクイズが進行中です！", ephemeral=True)
            return

        if not interaction.user.voice:
            await interaction.response.send_message("ボイスチャンネルに参加してから実行してください。", ephemeral=True)
            return

        # ローカルのイントロCSVファイルを再読み込みして、新規追加や更新を即座に反映
        self.intro_question_store.reload_questions()

        if genre is None:
            view = GenreSelectView(self, interaction, rule, value, penalty_type, penalty_value, unique, is_intro=True)
            await interaction.response.send_message(f"{view.get_settings_text()}\n\n出題するイントロクイズのジャンルを選んでください：", view=view)
        else:
            await interaction.response.defer()
            await self.start_quiz_session(interaction, rule, value, genre, penalty_type, penalty_value, unique, is_intro=True)

    async def start_quiz_session(self, interaction: discord.Interaction, rule: str, value: int, genre: str, penalty_type: str = "none", penalty_value: int = 0, unique: bool = True, is_intro: bool = False):
        self.last_settings = {
            "rule": rule,
            "value": value,
            "penalty_type": penalty_type,
            "penalty_value": penalty_value,
            "unique": unique
        }
        if is_intro:
            self.current_session = IntroQuizSession(self, interaction, rule, value, genre, penalty_type, penalty_value, unique)
        else:
            self.current_session = QuizSession(self, interaction, rule, value, genre, penalty_type, penalty_value, unique, voice_answer=False)
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
