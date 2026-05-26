from thefuzz import fuzz
import discord
import asyncio
import os

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

    async def validate_voice(self, audio_file_path: str, correct_answer: str, question: str = "") -> tuple[str, bool]:
        """
        音声ファイルをAI判定器に渡し、文字起こし結果と正誤結果のタプルを返します。
        """
        return await self.ai_validator.validate_voice(audio_file_path, correct_answer, question)

class AnswerReceiver:
    def __init__(self, bot):
        self.bot = bot

    async def wait_for_answer(self, channel: discord.TextChannel, user: discord.Member, timeout: float = 10.0, prompt_msg: discord.Message = None) -> str:
        """
        Wait for a text answer from a specific user in a specific channel.
        In the future, this could be extended to wait for an audio transcript.
        """
        def check(m: discord.Message):
            return m.author == user and m.channel == channel

        if prompt_msg is None:
            try:
                msg = await self.bot.wait_for('message', check=check, timeout=timeout)
                return msg.content
            except asyncio.TimeoutError:
                return None

        # prompt_msg is provided. Start countdown concurrently.
        base_content = prompt_msg.content.rsplit("\n⌛ **残り", 1)[0]

        async def run_countdown():
            try:
                for i in range(int(timeout), 0, -1):
                    try:
                        await prompt_msg.edit(content=f"{base_content}\n⌛ **残り {i} 秒**")
                    except discord.errors.NotFound:
                        break
                    except Exception as e:
                        print(f"Error editing countdown message: {e}")
                    
                    # Sleep 1 second in 0.1s steps to react faster to cancellation/answer
                    for _ in range(10):
                        await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass

        countdown = asyncio.create_task(run_countdown())
        try:
            msg = await self.bot.wait_for('message', check=check, timeout=timeout)
            return msg.content
        except asyncio.TimeoutError:
            return None
        finally:
            countdown.cancel()
            try:
                await prompt_msg.edit(content=base_content)
            except Exception:
                pass

    async def wait_for_voice_answer(self, channel: discord.TextChannel, voice_client, user: discord.Member, timeout: float = 8.0, check_cancel=None, elapsed_ms=None) -> str:
        """
        ユーザーの音声を最大 timeout 秒間録音し、録音された一時ファイルパス (.wav) を返します。
        話し終わったボタンが押された場合、または外部キャンセルフラグが立った場合、早期に録音を終了してファイルパスを返します。
        """
        from discord.ext import voice_recv

        temp_wav = f"temp_voice_{user.id}.wav"
        if os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass

        # 音声回答完了ボタン付きのViewを送信
        view = VoiceAnswerDoneView(user, timeout=timeout)
        time_str = f" (早押しタイム: **{elapsed_ms}ms**)" if elapsed_ms is not None else ""
        msg_text = f"🔔 **{user.display_name}** さんが押しました！{time_str}\n音声で回答してください！ (最大 {int(timeout)} 秒間録音します)\n話し終わったら下のボタンを押すか、そのままお待ちください。"
        done_msg = await channel.send(msg_text, view=view)
        view.message = done_msg

        try:
            sink = voice_recv.WaveSink(temp_wav)
            filtered_sink = voice_recv.UserFilter(sink, user)
            voice_client.listen(filtered_sink)

            # 0.1秒単位でポーリング監視しながら、残り秒数をカウントダウンする
            last_remaining = int(timeout)
            for step in range(int(timeout * 10)):
                if view.done or (check_cancel and check_cancel()):
                    break
                
                remaining = int(timeout - (step / 10))
                if remaining != last_remaining:
                    last_remaining = remaining
                    try:
                        await done_msg.edit(content=f"{msg_text}\n⌛ **残り {remaining} 秒**")
                    except Exception:
                        pass
                await asyncio.sleep(0.1)
        finally:
            try:
                voice_client.stop_listening()
            except Exception:
                pass

            view.stop()
            try:
                for child in view.children:
                    child.disabled = True
                await done_msg.edit(content=msg_text, view=view)
            except Exception:
                pass

        return temp_wav if os.path.exists(temp_wav) else None

class VoiceAnswerDoneView(discord.ui.View):
    def __init__(self, user: discord.Member, timeout: float):
        super().__init__(timeout=timeout)
        self.user = user
        self.done = False
        self.message = None

    @discord.ui.button(label="🎙️ 話し終わった / 解答を送信", style=discord.ButtonStyle.success, emoji="✅")
    async def done_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("あなたには解答権がありません！", ephemeral=True)
            return

        self.done = True
        button.disabled = True
        button.label = "🎙️ 解答を送信しました"
        button.style = discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self):
        # タイムアウト時にボタンを無効化
        if self.message:
            try:
                for child in self.children:
                    child.disabled = True
                    if isinstance(child, discord.ui.Button) and child.label == "🎙️ 話し終わった / 解答を送信":
                        child.label = "🎙️ 時間切れ / 録音終了"
                        child.style = discord.ButtonStyle.secondary
                await self.message.edit(view=self)
            except Exception:
                pass
