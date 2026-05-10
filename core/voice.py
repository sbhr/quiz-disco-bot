import os
import discord
from gtts import gTTS
import asyncio

class VoiceManager:
    def __init__(self, bot):
        self.bot = bot
        self.audio_file_path = "temp_question.mp3"

    async def join_channel(self, channel: discord.VoiceChannel) -> discord.VoiceClient:
        """Join a voice channel."""
        if not channel:
            return None
        
        # Check if already connected
        voice_client = discord.utils.get(self.bot.voice_clients, guild=channel.guild)
        if voice_client and voice_client.is_connected():
            if voice_client.channel != channel:
                await voice_client.move_to(channel)
            return voice_client
        else:
            return await channel.connect()

    async def leave_channel(self, guild: discord.Guild):
        """Leave the voice channel."""
        voice_client = discord.utils.get(self.bot.voice_clients, guild=guild)
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()

    def generate_tts(self, text: str, lang: str = 'ja'):
        """Generate TTS audio file."""
        tts = gTTS(text=text, lang=lang)
        tts.save(self.audio_file_path)

    async def play_audio(self, voice_client: discord.VoiceClient, text: str):
        """Generate TTS and play it in the voice channel."""
        # Ensure we run the blocking gTTS generation in a thread to not block event loop
        await asyncio.to_thread(self.generate_tts, text)
        
        if voice_client.is_playing():
            voice_client.stop()
            
        audio_source = discord.FFmpegPCMAudio(self.audio_file_path)
        voice_client.play(audio_source)

    def stop_audio(self, voice_client: discord.VoiceClient):
        """Stop currently playing audio."""
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            
    def cleanup(self):
        """Remove temporary audio file."""
        if os.path.exists(self.audio_file_path):
            try:
                os.remove(self.audio_file_path)
            except Exception:
                pass
