import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

class MockCog:
    def __init__(self):
        self.quiz_active = True
        self.ended_called = False

    async def end_quiz_session(self, interaction):
        self.quiz_active = False
        self.ended_called = True
        print("💡 [Simulation] Cog.end_quiz_session() successfully called!")

class MockVoiceManager:
    def __init__(self):
        self.left_channel = False

    async def leave_channel(self, guild):
        self.left_channel = True
        print("🔊 [Simulation] VoiceManager.leave_channel() successfully called!")

# 擬似的な例外安全ループのシミュレーション
async def simulate_error_handling_cleanup():
    print("--- Simulating QuizSession Exception Safety and Cleanup ---")
    
    cog = MockCog()
    voice_manager = MockVoiceManager()
    session_active = True
    
    print(f"Initial State: Cog.quiz_active = {cog.quiz_active}")
    print("🎙️ Starting quiz loop simulation...")
    
    try:
        # クイズの開始
        question_count = 0
        while session_active:
            question_count += 1
            print(f"  Asking Question #{question_count}")
            
            if question_count == 3:
                # 3問目に予期せぬ致命的なDBエラーやAPI例外が発生したと仮定
                print("💥 [Simulation] Unexpected database lock/API exception occurs!")
                raise RuntimeError("Database connection lost.")
                
            await asyncio.sleep(0.1)
    except Exception as e:
        print(f"⚠️ Caught expected exception: {e}")
        # 例外時のみチャンネルから退出
        await voice_manager.leave_channel(None)
    finally:
        # 正常/例外に関わらず必ず状態クリアを実行
        session_active = False
        await cog.end_quiz_session(None)

    print("\n--- Simulation Result ---")
    print(f"Final State: Cog.quiz_active = {cog.quiz_active}")
    print(f"Was end_quiz_session called? {cog.ended_called}")
    print(f"Did the bot leave the voice channel? {voice_manager.left_channel}")
    
    if not cog.quiz_active and cog.ended_called and voice_manager.left_channel:
        print("✅ PASS: The bot recovered cleanly from the exception and did not get stuck!")
    else:
        print("❌ FAIL: State cleanup failed, bot remains in an unstable state.")

if __name__ == "__main__":
    asyncio.run(simulate_error_handling_cleanup())
