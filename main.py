import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

class QuizBot(commands.Bot):
    def __init__(self):
        # Intents are required to read messages and voice states
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        # Load cogs
        await self.load_extension('cogs.quiz')
        # Sync slash commands
        await self.tree.sync()
        print("Slash commands synced.")

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')
        print('Bot is ready to play! Type /quiz in discord to start.')

if __name__ == '__main__':
    if not TOKEN or TOKEN == 'your_bot_token_here':
        print("Error: DISCORD_BOT_TOKEN is not set in .env file.")
        print("Please copy .env.template to .env and set your bot token.")
        exit(1)
        
    bot = QuizBot()
    bot.run(TOKEN)
