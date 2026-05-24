import asyncio
import discord
import time
import os
from core.question import QuestionStore
from core.score import ScoreManager
from core.voice import VoiceManager
from core.answer import AnswerReceiver, AnswerValidator

class QuizSession:
    def __init__(self, cog, interaction: discord.Interaction, rule: str, value: int, genre: str, penalty_type: str = "none", penalty_value: int = 0, unique: bool = True, voice_answer: bool = False):
        self.cog = cog
        self.interaction = interaction
        self.rule = rule
        self.value = value
        self.genre = genre
        self.penalty_type = penalty_type
        self.penalty_value = penalty_value
        self.unique = unique
        self.voice_answer = voice_answer
        
        # マネージャー類は Cog から参照
        self.voice_manager = cog.voice_manager
        self.question_store = cog.question_store
        self.score_manager = cog.score_manager
        self.answer_receiver = cog.answer_receiver
        self.answer_validator = cog.answer_validator
        
        self.is_active = True
        self.force_stop = False
        self.questions_asked = 0
        self.allowed_users = set()
        self.frozen_users = {}  # {user_id: timestamp_until_unfrozen or question_number_until_unfrozen}
        self.mistake_counts = {}  # {user_id: count_of_mistakes}
        self.disqualified_users = set()  # {user_id, ...}
        self.question_start_time = 0.0
        self.correct_reaction_times = []  # [(user_id, elapsed_ms, question_number)]

    async def run(self):
        """クイズセッションのメインループ"""
        # ボイスチャンネルの取得
        vc = self.interaction.user.voice.channel
        
        try:
            voice_client = await self.voice_manager.join_channel(vc)
        except Exception as e:
            msg = f"ボイスチャンネルへの接続に失敗しました: {e}"
            if self.interaction.response.is_done():
                await self.interaction.followup.send(msg)
            else:
                await self.interaction.response.send_message(msg, ephemeral=True)
            return

        try:
            self.score_manager.reset_scores()
            
            if self.cog.registered_participants:
                self.allowed_users = self.cog.registered_participants.copy()
            else:
                self.allowed_users = {member.id for member in vc.members if not member.bot}
                
            rule_text = f"{self.value} ポイント先取" if self.rule == "first_to_n" else f"全 {self.value} 問"
            genre_text = "すべて" if self.genre == "all" else self.genre
            
            # ペナルティ設定メッセージの生成
            if self.penalty_type == "none":
                penalty_text = ""
            elif self.penalty_type == "time":
                penalty_text = f" (お手つきペナルティ: {self.penalty_value}秒)"
            elif self.penalty_type == "skip":
                penalty_text = f" (お手つきペナルティ: 次の {self.penalty_value} 問休み)"
            elif self.penalty_type == "disqualify":
                penalty_text = f" (お手つきペナルティ: {self.penalty_value}回で失格)"
            else:
                penalty_text = ""
            
            start_msg = f"🎮 **クイズセッション開始！** (ルール: {rule_text} / ジャンル: {genre_text}{penalty_text})"
            if self.interaction.response.is_done():
                await self.interaction.followup.send(start_msg)
            else:
                await self.interaction.response.send_message(start_msg)
            
            while self.is_active:
                if self.force_stop or self.cog.force_stop:
                    await self.interaction.channel.send("クイズが強制終了されました。")
                    break
                    
                question_data = self.question_store.get_random_question(self.genre, self.unique)
                if question_data and question_data.get('_was_reset', False):
                    reset_embed = discord.Embed(
                        title="💡 出題履歴のリセット",
                        description=f"ジャンル **{genre_text}** のすべての問題が出尽くしたため、出題履歴をリセットして最初から出題します！",
                        color=discord.Color.blue()
                    )
                    await self.interaction.channel.send(embed=reset_embed)

                if not question_data:
                    await self.interaction.channel.send(f"出題できる問題がなくなりました！（ジャンル: {genre_text}）クイズを終了します。")
                    break
                    
                self.questions_asked += 1
                question_text = question_data.get('question', '')
                correct_answer = question_data.get('answer', '')
                explanation = question_data.get('explanation', '')

                embed = discord.Embed(
                    title=f"第 {self.questions_asked} 問",
                    description=f"**問題を読み上げます...**\n\n分かったら下のボタンを押し、音声またはチャットで解答してください。" if self.voice_answer else f"**問題を読み上げます...**\n\n分かったら下のボタンを押し、10秒以内にチャットで答えてください。",
                    color=discord.Color.blue()
                )
                embed.add_field(name="ジャンル", value=genre_text, inline=True)
                embed.add_field(name="現在の状況", value=f"進行中: {self.questions_asked}問目", inline=True)
                
                # ペナルティ表示のフッター設定
                if self.penalty_type == "time" and self.penalty_value > 0:
                    embed.set_footer(text=f"お手つきペナルティ: {self.penalty_value}秒休み")
                elif self.penalty_type == "skip" and self.penalty_value > 0:
                    embed.set_footer(text=f"お手つきペナルティ: 次の {self.penalty_value} 問休み")
                elif self.penalty_type == "disqualify" and self.penalty_value > 0:
                    embed.set_footer(text=f"お手つきペナルティ: {self.penalty_value}回間違いで失格")
                
                await self.interaction.channel.send(embed=embed)
                
                # 全員が失格になっているか確認
                active_users = self.allowed_users - self.disqualified_users
                if len(self.allowed_users) > 0 and len(active_users) == 0:
                    embed_all_disqualified = discord.Embed(
                        title="🚨 クイズ終了",
                        description="参加者全員が失格となったため、クイズセッションを終了します！",
                        color=discord.Color.red()
                    )
                    await self.interaction.channel.send(embed=embed_all_disqualified)
                    break
                
                answered_users = self.disqualified_users.copy()
                should_play_audio = True
                is_repeat = False
                
                while True:
                    # 全員が不正解かどうか
                    if len(self.allowed_users) > 0 and len(answered_users) >= len(self.allowed_users):
                        embed = discord.Embed(
                            title="全員不正解",
                            description=f"正解は **{correct_answer}** でした。",
                            color=discord.Color.red()
                        )
                        embed.add_field(name="問題文", value=question_text, inline=False)
                        if explanation:
                            embed.add_field(name="解説", value=explanation)
                        await self.interaction.channel.send(embed=embed)
                        break

                    # ボタンの表示
                    from cogs.quiz import FastestFingerView
                    view = FastestFingerView(self, timeout=None, answered_users=answered_users, allowed_users=self.allowed_users)
                    msg = await self.interaction.channel.send("分かったら早押しボタンを押してください！", view=view)
                    
                    # 音声再生
                    if should_play_audio:
                        try:
                            self.question_start_time = time.time()
                            await self.voice_manager.play_audio(voice_client, f"問題。{question_text}", use_local=is_repeat)
                            is_repeat = True
                        except Exception as e:
                            await self.interaction.channel.send(f"音声の再生に失敗しました。({e})")
                            self.is_active = False
                            return
                    
                    # ボタン押し待ち
                    while voice_client.is_playing() and not self.force_stop and not self.cog.force_stop:
                        if view.pressed_user or view.all_done:
                            break
                        await asyncio.sleep(0.1)
                    
                    # タイムアウトカウントダウン
                    timeout_triggered = False
                    if not view.pressed_user and not view.all_done and not self.force_stop and not self.cog.force_stop:
                        for i in range(7, 0, -1):
                            if view.pressed_user or view.all_done or self.force_stop or self.cog.force_stop:
                                break
                            try:
                                await msg.edit(content=f"分かったら早押しボタンを押してください！ (残り {i} 秒)")
                            except discord.errors.NotFound:
                                break
                            for _ in range(10):
                                if view.pressed_user or self.force_stop or self.cog.force_stop:
                                    break
                                await asyncio.sleep(0.1)
                        else:
                            if not view.pressed_user:
                                timeout_triggered = True

                    if self.force_stop or self.cog.force_stop:
                        break

                    if timeout_triggered or view.all_done or not view.pressed_user:
                        self.voice_manager.stop_audio(voice_client)
                        view.stop()
                        try:
                            if view.all_done:
                                await msg.edit(content="全員が降参しました。", view=None)
                            else:
                                await msg.edit(content="時間切れです！", view=None)
                        except discord.errors.NotFound:
                            pass
                        
                        embed = discord.Embed(
                            title="時間切れ / 全員降参",
                            description=f"正解は **{correct_answer}** でした。",
                            color=discord.Color.light_grey()
                        )
                        embed.add_field(name="問題文", value=question_text, inline=False)
                        if explanation:
                            embed.add_field(name="解説", value=explanation)
                        await self.interaction.channel.send(embed=embed)
                        break
                        
                    # 誰かが押した！
                    was_playing = voice_client.is_playing()
                    self.voice_manager.stop_audio(voice_client)
                    user = view.pressed_user
                    
                    # 早押し反応速度（ミリ秒）の算出
                    pressed_time = getattr(view, 'pressed_time', time.time())
                    if self.question_start_time > 0.0:
                        elapsed_ms = max(0, int((pressed_time - self.question_start_time) * 1000))
                    else:
                        elapsed_ms = 0
                    
                    if self.voice_answer:
                        # 音声回答モード
                        # 1. 解答者以外のサーバーミュート処理 (VoiceManager へ移行)
                        muted_members = await self.voice_manager.mute_all_except(vc, user)

                        try:
                            # 2. 録音処理 (AnswerReceiver にカプセル化、強制終了チェックと反応時間を渡す)
                            temp_wav = await self.answer_receiver.wait_for_voice_answer(
                                self.interaction.channel, 
                                voice_client, 
                                user, 
                                timeout=8.0,
                                check_cancel=lambda: self.force_stop or self.cog.force_stop,
                                elapsed_ms=elapsed_ms
                            )
                        finally:
                            # 3. サーバーミュート解除 (VoiceManager へ移行)
                            await self.voice_manager.unmute_members(muted_members)

                        # 4. 音声判定
                        if temp_wav:
                            await self.interaction.channel.send("🎙️ 録音が終了しました。正誤判定中...")
                            transcript, is_correct = await self.answer_validator.validate_voice(temp_wav, correct_answer, question_text)
                            
                            if os.path.exists(temp_wav):
                                try:
                                    os.remove(temp_wav)
                                except Exception:
                                    pass
                                    
                            if transcript:
                                await self.interaction.channel.send(f"🎙️ 聞き取り結果: **「{transcript}」**")
                                user_answer = transcript
                            else:
                                await self.interaction.channel.send("🎙️ 音声が聞き取れませんでした。")
                                user_answer = None
                        else:
                            await self.interaction.channel.send("🎙️ 録音データの生成に失敗しました。")
                            user_answer = None
                    else:
                        # テキスト解答モード
                        await self.interaction.channel.send(f"🔔 **{user.display_name}** さんが押しました！ (早押しタイム: **{elapsed_ms}ms**)\n10秒以内にテキストで解答を送信してください。")
                        # 解答待ち
                        user_answer = await self.answer_receiver.wait_for_answer(self.interaction.channel, user, timeout=10.0)
                        is_correct = False # 後続で更新されるためダミー値
                    
                    if not user_answer:
                        answered_users.add(user.id)
                        # ペナルティ設定がある場合
                        if self.penalty_type == "time" and self.penalty_value > 0:
                            self.frozen_users[user.id] = time.time() + self.penalty_value
                        elif self.penalty_type == "skip" and self.penalty_value > 0:
                            self.frozen_users[user.id] = self.questions_asked + self.penalty_value
                        elif self.penalty_type == "disqualify" and self.penalty_value > 0:
                            self.mistake_counts[user.id] = self.mistake_counts.get(user.id, 0) + 1
                            current_mistakes = self.mistake_counts[user.id]
                            if current_mistakes >= self.penalty_value:
                                self.disqualified_users.add(user.id)
                                embed_disq = discord.Embed(
                                    title="❌ プレイヤー失格",
                                    description=f"**{user.display_name}** さんは {self.penalty_value} 回不正解（またはタイムアウト）となったため、**失格・脱落**となりました！",
                                    color=discord.Color.red()
                                )
                                await self.interaction.channel.send(embed=embed_disq)
                            else:
                                await self.interaction.channel.send(f"⚠️ **{user.display_name}** さんはお手つきしました！ (お手つき回数: {current_mistakes}/{self.penalty_value})")

                        if len(self.allowed_users) > 0 and len(answered_users) >= len(self.allowed_users):
                            embed = discord.Embed(
                                title="全員不正解",
                                description=f"解答時間切れ（または聞き取り不可）です！ 正解は **{correct_answer}** でした。",
                                color=discord.Color.red()
                            )
                            embed.add_field(name="問題文", value=question_text, inline=False)
                            if explanation:
                                embed.add_field(name="解説", value=explanation)
                            await self.interaction.channel.send(embed=embed)
                            break
                            
                        if was_playing:
                            await self.interaction.channel.send(f"解答時間切れ（または聞き取り不可）です！\nもう一度問題を読み上げます...")
                            should_play_audio = True
                        else:
                            await self.interaction.channel.send(f"解答時間切れ（または聞き取り不可）です！\n引き続き解答を受け付けます。")
                            should_play_audio = False
                        continue
                    
                    # 正誤判定 (テキスト解答モードの場合のみ実行)
                    if not self.voice_answer:
                        is_correct = await self.answer_validator.validate(user_answer, correct_answer, question_text)
                    if is_correct:
                        self.score_manager.add_score(user.id, 1)
                        score = self.score_manager.get_score(user.id)
                        self.correct_reaction_times.append((user.id, elapsed_ms, self.questions_asked))
                        
                        embed = discord.Embed(
                            title="✨ 正解！",
                            description=f"**{user.display_name}** さん、お見事！\n\n正解: **{correct_answer}**",
                            color=discord.Color.green()
                        )
                        embed.add_field(name="問題文", value=question_text, inline=False)
                        embed.add_field(name="獲得ポイント", value="1 pt", inline=True)
                        embed.add_field(name="現在の合計", value=f"{score} pts", inline=True)
                        if explanation:
                            embed.add_field(name="解説", value=explanation, inline=False)
                        
                        await self.interaction.channel.send(embed=embed)
                        break
                    else:
                        answered_users.add(user.id)
                        # ペナルティ設定がある場合
                        if self.penalty_type == "time" and self.penalty_value > 0:
                            self.frozen_users[user.id] = time.time() + self.penalty_value
                        elif self.penalty_type == "skip" and self.penalty_value > 0:
                            self.frozen_users[user.id] = self.questions_asked + self.penalty_value
                        elif self.penalty_type == "disqualify" and self.penalty_value > 0:
                            self.mistake_counts[user.id] = self.mistake_counts.get(user.id, 0) + 1
                            current_mistakes = self.mistake_counts[user.id]
                            if current_mistakes >= self.penalty_value:
                                self.disqualified_users.add(user.id)
                                embed_disq = discord.Embed(
                                    title="❌ プレイヤー失格",
                                    description=f"**{user.display_name}** さんは {self.penalty_value} 回不正解となったため、**失格・脱落**となりました！",
                                    color=discord.Color.red()
                                )
                                await self.interaction.channel.send(embed=embed_disq)
                            else:
                                await self.interaction.channel.send(f"⚠️ **{user.display_name}** さんはお手つきしました！ (お手つき回数: {current_mistakes}/{self.penalty_value})")

                        if len(self.allowed_users) > 0 and len(answered_users) >= len(self.allowed_users):
                            embed = discord.Embed(
                                title="全員不正解",
                                description=f"不正解！ 正解は **{correct_answer}** でした。",
                                color=discord.Color.red()
                            )
                            embed.add_field(name="問題文", value=question_text, inline=False)
                            if explanation:
                                embed.add_field(name="解説", value=explanation)
                            await self.interaction.channel.send(embed=embed)
                            break
                            
                        if was_playing:
                            await self.interaction.channel.send(f"❌ **不正解！**\nもう一度問題を読み上げます...")
                            should_play_audio = True
                        else:
                            await self.interaction.channel.send(f"❌ **不正解！**\n引き続き解答を受け付けます。")
                            should_play_audio = False
                        continue
                        
                # 勝敗判定
                scores = self.score_manager.get_all_scores()
                session_ended = False
                
                if self.rule == "first_to_n":
                    winner = None
                    for uid, score in scores.items():
                        if score >= self.value:
                            winner = uid
                            break
                    if winner:
                        self.score_manager.add_win(winner)
                        await self.interaction.channel.send(f"🏆 <@{winner}> さんが {self.value} ポイントに到達しました！優勝です！")
                        session_ended = True
                elif self.rule == "total_n":
                    if self.questions_asked >= self.value:
                        # 最多得点者を優勝者とする
                        if scores:
                            max_score = max(scores.values())
                            winners = [uid for uid, s in scores.items() if s == max_score]
                            for w in winners:
                                self.score_manager.add_win(w)
                        
                        await self.interaction.channel.send(f"全 {self.value} 問が終了しました！")
                        session_ended = True
                        
                if session_ended:
                    break
                    
                await self.interaction.channel.send("次の問題まで 5秒...")
                await asyncio.sleep(5)

            # 神押し賞の発表
            if self.correct_reaction_times:
                fastest = min(self.correct_reaction_times, key=lambda x: x[1])
                uid, ms, q_num = fastest
                embed = discord.Embed(
                    title="⚡ 神押し賞（最速正解記録）",
                    description=f"🏆 <@{uid}> さん\n第 {q_num} 問にて、わずか **{ms}ms** の超反応で正解しました！",
                    color=discord.Color.gold()
                )
                await self.interaction.channel.send(embed=embed)
        except Exception as e:
            print(f"Unexpected error in QuizSession.run: {e}")
            import traceback
            traceback.print_exc()
            
            # リッチなエラーメッセージの送信
            embed = discord.Embed(
                title="⚠️ システムエラー発生",
                description=f"クイズセッション中に予期せぬエラーが発生したため、セッションを安全に終了しました。\n\n**エラー内容:**\n`{e}`",
                color=discord.Color.red()
            )
            try:
                await self.interaction.channel.send(embed=embed)
            except Exception:
                pass

            # エラー時は安全のためにボイスチャンネルから退出させる
            try:
                await self.voice_manager.leave_channel(self.interaction.guild)
            except Exception as err:
                print(f"Failed to leave channel on error: {err}")
        finally:
            # セッションのクリーンアップ
            self.is_active = False
            await self.cog.end_quiz_session(self.interaction)
