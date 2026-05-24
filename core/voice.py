import os
import discord
import edge_tts
import asyncio
from gtts import gTTS
from discord.ext import voice_recv

class VoiceManager:
    def __init__(self, bot):
        self.bot = bot
        self.audio_file_path = "temp_question.mp3"
        # 日本語の女性の声（Nanami）を使用。他にも Keita (男性) などが選択可能。
        self.voice_name = "ja-JP-NanamiNeural"

    async def join_channel(self, channel: discord.VoiceChannel) -> discord.VoiceClient:
        """ボイスチャンネルに参加する"""
        if not channel:
            return None
        
        # 既に接続済みか確認
        voice_client = discord.utils.get(self.bot.voice_clients, guild=channel.guild)
        if voice_client and voice_client.is_connected():
            if voice_client.channel != channel:
                await voice_client.move_to(channel)
            return voice_client
        else:
            return await channel.connect(cls=voice_recv.VoiceRecvClient)

    async def leave_channel(self, guild: discord.Guild):
        """ボイスチャンネルから退出する"""
        voice_client = discord.utils.get(self.bot.voice_clients, guild=guild)
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()

    async def play_audio(self, voice_client: discord.VoiceClient, text: str):
        """edge-ttsで音声を生成し、ボイスチャンネルで再生する（失敗時はgTTSにフォールバック）"""
        try:
            # 音声生成 (edge-ttsは非同期対応)
            communicate = edge_tts.Communicate(text, self.voice_name)
            await communicate.save(self.audio_file_path)
        except Exception as e:
            print(f"edge-tts error: {e}. Falling back to gTTS...")
            # gTTSは同期関数なのでスレッドで実行するか、短時間なので直接実行
            tts = gTTS(text=text, lang='ja')
            tts.save(self.audio_file_path)
        
        if voice_client.is_playing():
            voice_client.stop()
            
        audio_source = discord.FFmpegPCMAudio(self.audio_file_path)
        voice_client.play(audio_source)

    def stop_audio(self, voice_client: discord.VoiceClient):
        """再生中の音声を停止する"""
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            
    def cleanup(self):
        """一時音声ファイルを削除する"""
        if os.path.exists(self.audio_file_path):
            try:
                os.remove(self.audio_file_path)
            except Exception:
                pass
