import discord
from discord.ext import commands
from discord import app_commands
from core.question import QuestionStore
from core.score import ScoreManager
from core.voice import VoiceManager
from core.answer import AnswerReceiver, AnswerValidator

class FastestFingerView(discord.ui.View):
    def __init__(self, timeout: float):
        super().__init__(timeout=timeout)
        self.pressed_user = None
        self.pressed = False

    @discord.ui.button(label="早押し！", style=discord.ButtonStyle.danger, emoji="🔴")
    async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
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

class QuizCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.question_store = QuestionStore("data/questions.csv")
        self.score_manager = ScoreManager()
        self.voice_manager = VoiceManager(bot)
        self.answer_receiver = AnswerReceiver(bot)
        self.answer_validator = AnswerValidator(threshold=80)
        
        self.current_quiz_active = False

    @app_commands.command(name="quiz", description="早押しクイズを開始します")
    async def quiz_start(self, interaction: discord.Interaction):
        await interaction.response.defer()

        if self.current_quiz_active:
            await interaction.followup.send("既にクイズが進行中です！", ephemeral=True)
            return
            
        if not interaction.user.voice:
            await interaction.followup.send("ボイスチャンネルに参加してから実行してください。", ephemeral=True)
            return
            
        vc = interaction.user.voice.channel
        
        try:
            voice_client = await self.voice_manager.join_channel(vc)
        except Exception as e:
            await interaction.followup.send(f"ボイスチャンネルへの接続に失敗しました: {e}", ephemeral=True)
            return
            
        question_data = self.question_store.get_random_question()
        if not question_data:
            await interaction.followup.send("問題が登録されていません。`data/questions.csv`を確認してください。", ephemeral=True)
            return
            
        self.current_quiz_active = True
        question_text = question_data['question']
        correct_answer = question_data['answer']
        explanation = question_data['explanation']

        await interaction.followup.send(f"**第1問！**\n問題を読み上げます...")
        
        # Show button
        view = FastestFingerView(timeout=30.0) # wait up to 30s for someone to press the button
        msg = await interaction.channel.send("分かったら早押しボタンを押してください！", view=view)
        
        # Play audio
        try:
            await self.voice_manager.play_audio(voice_client, question_text)
        except Exception as e:
            await interaction.channel.send(f"音声の再生に失敗しました。FFmpegがインストールされているか確認してください。({e})")
            self.current_quiz_active = False
            return
        
        # Wait for button press
        timeout = await view.wait()
        
        if timeout or not view.pressed_user:
            self.voice_manager.stop_audio(voice_client)
            await msg.edit(view=None) # remove buttons
            await interaction.channel.send(f"時間切れです！誰も押しませんでした。\n正解は **{correct_answer}** でした。\n解説: {explanation}")
            self.current_quiz_active = False
            return
            
        # Someone pressed the button!
        # Instantly stop audio reading
        self.voice_manager.stop_audio(voice_client)
        user = view.pressed_user
        
        await interaction.channel.send(f"🔔 **{user.display_name}** さんが押しました！ 10秒以内にテキストで解答を送信してください。")
        
        # Wait for text answer
        user_answer = await self.answer_receiver.wait_for_answer(interaction.channel, user, timeout=10.0)
        
        if not user_answer:
            await interaction.channel.send(f"時間切れです！残念...\n正解は **{correct_answer}** でした。\n解説: {explanation}")
        else:
            is_correct = self.answer_validator.validate(user_answer, correct_answer)
            if is_correct:
                self.score_manager.add_score(user.id, 1)
                score = self.score_manager.get_score(user.id)
                await interaction.channel.send(f"🎉 **正解！** \n{user.display_name} さんに1ポイント！（合計: {score} ポイント）\n解説: {explanation}")
            else:
                await interaction.channel.send(f"❌ **不正解！**\n正解は **{correct_answer}** でした。\n解説: {explanation}")
                
        self.current_quiz_active = False

async def setup(bot):
    await bot.add_cog(QuizCog(bot))
