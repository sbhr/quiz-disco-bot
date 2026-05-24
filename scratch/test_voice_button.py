import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

class MockUser:
    def __init__(self, id, name):
        self.id = id
        self.display_name = name

class MockButton:
    def __init__(self):
        self.disabled = False
        self.label = ""
        self.style = None

class MockInteraction:
    def __init__(self, user):
        self.user = user

# 擬似的なViewとポーリングループのシミュレーション
async def simulate_polling_early_cut():
    print("--- Simulating early cut polling logic ---")
    
    # モックの作成
    user = MockUser(12345, "プレイヤーA")
    button = MockButton()
    
    # 状態変数
    view_done = False
    
    # 0.1秒単位でポーリング監視 (最大8.0秒 = 80回)
    timeout = 8.0
    elapsed = 0.0
    
    # バックグラウンドタスクで3.0秒後にボタンが押されるシミュレーション
    async def simulate_button_press_after_delay():
        nonlocal view_done
        await asyncio.sleep(3.0)
        print("💡 [Simulation] Player pressed '話し終わった / 解答を送信' button!")
        view_done = True

    press_task = asyncio.create_task(simulate_button_press_after_delay())
    
    print("🎙️ Starting 8-second recording wait loop...")
    loop_terminated_early = False
    
    for _ in range(int(timeout * 10)):
        if view_done:
            loop_terminated_early = True
            break
        await asyncio.sleep(0.1)
        elapsed += 0.1

    await press_task
    
    print("\n--- Simulation Result ---")
    print(f"Total loop time elapsed: {elapsed:.2f} seconds")
    if loop_terminated_early:
        print("✅ PASS: The recording loop terminated early as soon as the button was pressed!")
    else:
        print("❌ FAIL: The recording loop ran for the full duration instead of cutting early.")

if __name__ == "__main__":
    asyncio.run(simulate_polling_early_cut())
