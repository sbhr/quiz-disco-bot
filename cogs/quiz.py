import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from core.question import QuestionStore
from core.score import ScoreManager
from core.voice import VoiceManager
from core.answer import AnswerReceiver, AnswerValidator

class FastestFingerView(discord.ui.View):
    def __init__(self, timeout: float | None, answered_users: set, allowed_users: set):
        super().__init__(timeout=timeout)
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

        if self.pressed:
            await interaction.response.send_message("既に他の人が押しています！", ephemeral=True)
            return
            
        self.pressed = True
        self.pressed_user = interaction.user
        
        # Disable the button for all users
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(view=self)
        self.stop() # Stop listening to this view to break the wait()

    @discord.ui.button(label="降参する", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def surrender_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.allowed_users:
            await interaction.response.send_message("あなたは参加者ではありません！", ephemeral=True)
            return

        if interaction.user.id in self.answered_users:
            await interaction.response.send_message("あなたは既に回答済み（または降参済み）です！", ephemeral=True)
            return

        self.answered_users.add(interaction.user.id)
        
        # Check if all participants have answered/surrendered
        if len(self.allowed_users) > 0 and len(self.answered_users) >= len(self.allowed_users):
            await interaction.response.send_message(f"🏳️ **{interaction.user.display_name}** さんが降参しました。全員が回答・降参したため終了します。")
            self.all_done = True
            self.stop()
        else:
            await interaction.response.send_message(f"🏳️ **{interaction.user.display_name}** さんが降参しました。")

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
    def __init__(self, cog, original_interaction, rule, value):
        super().__init__(timeout=60)
        self.cog = cog
        self.original_interaction = original_interaction
        self.rule = rule
        self.value = value
        
        # ジャンル一覧を取得（「すべて」を追加）
        genres = list(self.cog.question_store.questions_by_genre.keys())
        genres = sorted(genres)
        
        # ボタンを追加（最大25個まで）
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
            
            # ボタンを無効化
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(content=f"ジャンル **{genre}** が選択されました。クイズを開始します...", view=self)
            
            # クイズセッションを開始
            await self.cog.start_quiz_session(interaction, self.rule, self.value, genre)
            
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

    @app_commands.command(name="recruit", description="クイズの参加者を募集するパネルを表示します")
    async def recruit_participants(self, interaction: discord.Interaction):
        self.registered_participants.clear()
        view = RecruitView(self)
        text = view.get_participants_text(interaction.guild)
        await interaction.response.send_message(content=f"**クイズ参加者募集！**\n以下のボタンで参加・辞退を選んでください。\n\n**現在の参加予定者 (0名):**\n{text}", view=view)

    @app_commands.command(name="stop_quiz", description="進行中のクイズセッションを強制終了します")
    async def stop_quiz(self, interaction: discord.Interaction):
        if not self.current_quiz_active:
            await interaction.response.send_message("現在進行中のクイズはありません。", ephemeral=True)
            return
            
        self.force_stop = True
        await interaction.response.send_message("クイズの強制終了リクエストを受け付けました。現在の問題が終わると終了します。")

    @app_commands.command(name="quiz", description="早押しクイズを開始します")
    @app_commands.describe(rule="ルールの種類", value="問題数または目標ポイント", genre="出題するジャンル（省略するとボタンで選択）")
    @app_commands.choices(rule=[
        app_commands.Choice(name="N問先取", value="first_to_n"),
        app_commands.Choice(name="全N問", value="total_n")
    ])
    async def quiz_start(self, interaction: discord.Interaction, rule: str = "first_to_n", value: int = 3, genre: str = None):
        if self.current_quiz_active:
            await interaction.response.send_message("既にクイズが進行中です！", ephemeral=True)
            return

        if not interaction.user.voice:
            await interaction.response.send_message("ボイスチャンネルに参加してから実行してください。", ephemeral=True)
            return

        if genre is None:
            view = GenreSelectView(self, interaction, rule, value)
            await interaction.response.send_message("出題するジャンルを選んでください：", view=view)
        else:
            await interaction.response.defer()
            await self.start_quiz_session(interaction, rule, value, genre)

    async def start_quiz_session(self, interaction: discord.Interaction, rule: str, value: int, genre: str):
        # ボイスチャンネルの取得
        vc = interaction.user.voice.channel
        
        try:
            voice_client = await self.voice_manager.join_channel(vc)
        except Exception as e:
            msg = f"ボイスチャンネルへの接続に失敗しました: {e}"
            if interaction.response.is_done():
                await interaction.followup.send(msg)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return
            
        self.current_quiz_active = True
        self.force_stop = False
        self.question_store.reset_used_questions()
        self.score_manager.reset_scores()
        
        if self.registered_participants:
            allowed_users = self.registered_participants.copy()
        else:
            allowed_users = {member.id for member in vc.members if not member.bot}
            
        questions_asked = 0
        rule_text = f"{value} 問先取" if rule == "first_to_n" else f"全 {value} 問"
        genre_text = "すべて" if genre == "all" else genre
        
        start_msg = f"🎮 **クイズセッション開始！** (ルール: {rule_text} / ジャンル: {genre_text})"
        if interaction.response.is_done():
            await interaction.followup.send(start_msg)
        else:
            await interaction.response.send_message(start_msg)
        
        while self.current_quiz_active:
            if self.force_stop:
                await interaction.channel.send("クイズが強制終了されました。")
                break
                
            question_data = self.question_store.get_random_question(genre)
            if not question_data:
                await interaction.channel.send(f"出題できる問題がなくなりました！（ジャンル: {genre_text}）クイズを終了します。")
                break
                
            questions_asked += 1
            question_text = question_data.get('question', '')
            correct_answer = question_data.get('answer', '')
            explanation = question_data.get('explanation', '')
            explanation_text = f"\n解説: {explanation}" if explanation else ""

            await interaction.channel.send(f"**第 {questions_asked} 問！**\n問題を読み上げます...")
            
            answered_users = set()
            should_play_audio = True
            
            while True:
                # Check if all participants have answered incorrectly
                if len(allowed_users) > 0 and len(answered_users) >= len(allowed_users):
                    await interaction.channel.send(f"参加者全員が不正解となりました！\n正解は **{correct_answer}** でした。{explanation_text}")
                    break

                # Show button (timeout=None disables UI timeout)
                view = FastestFingerView(timeout=None, answered_users=answered_users, allowed_users=allowed_users)
                msg = await interaction.channel.send("分かったら早押しボタンを押してください！", view=view)
                
                # Play audio
                if should_play_audio:
                    try:
                        await self.voice_manager.play_audio(voice_client, f"問題。{question_text}")
                    except Exception as e:
                        await interaction.channel.send(f"音声の再生に失敗しました。FFmpegがインストールされているか確認してください。({e})")
                        self.current_quiz_active = False
                        return
                
                # Wait for audio to finish while listening to button press
                while voice_client.is_playing() and not self.force_stop:
                    if view.pressed_user or view.all_done:
                        break
                    await asyncio.sleep(0.1)
                
                # If audio finished and no one pressed, start 7-second countdown
                timeout_triggered = False
                if not view.pressed_user and not view.all_done and not self.force_stop:
                    for i in range(7, 0, -1):
                        if view.pressed_user or view.all_done or self.force_stop:
                            break
                        try:
                            await msg.edit(content=f"分かったら早押しボタンを押してください！ (残り {i} 秒)")
                        except discord.errors.NotFound:
                            break
                        
                        # Wait for 1 second, checking button press every 0.1s
                        for _ in range(10):
                            if view.pressed_user or self.force_stop:
                                break
                            await asyncio.sleep(0.1)
                    else:
                        if not view.pressed_user:
                            timeout_triggered = True

                if self.force_stop:
                    break

                if timeout_triggered or view.all_done or not view.pressed_user:
                    self.voice_manager.stop_audio(voice_client)
                    view.stop()
                    try:
                        if view.all_done:
                            await msg.edit(content="全員が降参しました。", view=None)
                        else:
                            await msg.edit(content="時間切れです！", view=None) # remove buttons
                    except discord.errors.NotFound:
                        pass
                    
                    if view.all_done:
                        await interaction.channel.send(f"全員が降参または不正解となりました！\n正解は **{correct_answer}** でした。{explanation_text}")
                    else:
                        await interaction.channel.send(f"時間切れです！誰も押しませんでした。\n正解は **{correct_answer}** でした。{explanation_text}")
                    break
                    
                # Someone pressed the button!
                was_playing = voice_client.is_playing()
                self.voice_manager.stop_audio(voice_client)
                user = view.pressed_user
                
                await interaction.channel.send(f"🔔 **{user.display_name}** さんが押しました！ 10秒以内にテキストで解答を送信してください。")
                
                # Wait for text answer
                user_answer = await self.answer_receiver.wait_for_answer(interaction.channel, user, timeout=10.0)
                
                if not user_answer:
                    answered_users.add(user.id)
                    if len(allowed_users) > 0 and len(answered_users) >= len(allowed_users):
                        await interaction.channel.send(f"解答時間切れです！ 参加者全員が不正解となりました。\n正解は **{correct_answer}** でした。{explanation_text}")
                        break
                        
                    if was_playing:
                        await interaction.channel.send(f"解答時間切れです！\nもう一度問題を読み上げます...")
                        should_play_audio = True
                    else:
                        await interaction.channel.send(f"解答時間切れです！\n引き続き解答を受け付けます。")
                        should_play_audio = False
                    continue
                
                is_correct = self.answer_validator.validate(user_answer, correct_answer)
                if is_correct:
                    self.score_manager.add_score(user.id, 1)
                    score = self.score_manager.get_score(user.id)
                    await interaction.channel.send(f"🎉 **正解！** \n{user.display_name} さんに1ポイント！（合計: {score} ポイント）{explanation_text}")
                    break
                else:
                    answered_users.add(user.id)
                    if len(allowed_users) > 0 and len(answered_users) >= len(allowed_users):
                        await interaction.channel.send(f"❌ **不正解！** 参加者全員が不正解となりました。\n正解は **{correct_answer}** でした。{explanation_text}")
                        break
                        
                    if was_playing:
                        await interaction.channel.send(f"❌ **不正解！**\nもう一度問題を読み上げます...")
                        should_play_audio = True
                    else:
                        await interaction.channel.send(f"❌ **不正解！**\n引き続き解答を受け付けます。")
                        should_play_audio = False
                    continue
                    
            # 勝敗判定
            scores = self.score_manager.get_all_scores()
            session_ended = False
            
            if rule == "first_to_n":
                winner = None
                for uid, score in scores.items():
                    if score >= value:
                        winner = uid
                        break
                if winner:
                    await interaction.channel.send(f"🏆 <@{winner}> さんが {value} ポイントに到達しました！優勝です！")
                    session_ended = True
            elif rule == "total_n":
                if questions_asked >= value:
                    await interaction.channel.send(f"全 {value} 問が終了しました！")
                    session_ended = True
                    
            if session_ended:
                break
                
            await interaction.channel.send("次の問題まで 3秒...")
            await asyncio.sleep(3)

        # セッション終了時の処理
        self.current_quiz_active = False
        
        scores = self.score_manager.get_all_scores()
        if scores:
            sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            ranking_text = "**🏅 最終ランキング 🏅**\n"
            for rank, (uid, score) in enumerate(sorted_scores, 1):
                ranking_text += f"{rank}位: <@{uid}> - {score} ポイント\n"
            await interaction.channel.send(ranking_text)
        else:
            await interaction.channel.send("クイズセッションが終了しました。得点者はいませんでした。")

async def setup(bot):
    await bot.add_cog(QuizCog(bot))
