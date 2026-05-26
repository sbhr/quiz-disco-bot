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

    async def play_audio(self, voice_client: discord.VoiceClient, text: str, use_local: bool = False):
        """edge-ttsで音声を生成し、ボイスチャンネルで再生する（use_local=Trueかつファイルが存在する場合は生成をスキップして再生、失敗時はgTTSにフォールバック）"""
        if use_local and os.path.exists(self.audio_file_path):
            print("🔊 Using local audio file for replay.")
        else:
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

    async def play_youtube(self, voice_client: discord.VoiceClient, url: str, start_time: int = 0):
        """YouTube の音源を指定された秒数からストリーミング再生する"""
        import yt_dlp
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        
        loop = asyncio.get_event_loop()
        
        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                return info.get('url')
                
        try:
            stream_url = await loop.run_in_executor(None, extract)
        except Exception as e:
            print(f"Failed to extract stream URL from YouTube: {e}")
            raise e
            
        if not stream_url:
            raise ValueError("Could not extract stream URL from YouTube.")
            
        if voice_client.is_playing():
            voice_client.stop()
            
        before_options = f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {start_time}"
        options = "-vn"
        
        audio_source = discord.FFmpegPCMAudio(
            stream_url,
            before_options=before_options,
            options=options
        )
        
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

    async def mute_all_except(self, channel: discord.VoiceChannel, exclude_member: discord.Member) -> list[discord.Member]:
        """指定したユーザー以外のボイスチャンネルメンバーをミュートし、ミュートしたメンバーのリストを返します"""
        muted = []
        if not channel:
            return muted
        for member in channel.members:
            if member.id != exclude_member.id and not member.bot:
                if member.voice and not member.voice.mute:
                    try:
                        await member.edit(mute=True, reason="早押しクイズ解答中")
                        muted.append(member)
                    except Exception as e:
                        print(f"Failed to mute {member.name} in VoiceManager: {e}")
        return muted

    async def unmute_members(self, members: list[discord.Member]):
        """指定されたメンバーリストのミュートを解除します"""
        for member in members:
            try:
                # メンバーがまだボイスチャンネルに残っており、かつミュート状態である場合のみ解除
                if member.voice and member.voice.mute:
                    await member.edit(mute=False, reason="早押しクイズ解答終了")
            except Exception as e:
                print(f"Failed to unmute {member.name} in VoiceManager: {e}")
