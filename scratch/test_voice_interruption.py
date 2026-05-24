import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

class MockUser:
    def __init__(self, id, name):
        self.id = id
        self.display_name = name

# 擬似的なキャンセル監視ループのシミュレーション
async def simulate_cancellation_interruption():
    print("--- Simulating session cancellation interruption logic ---")
    
    # セッションの状態を表すフラグ
    session_force_stopped = False
    
    # 0.1秒単位でポーリング監視 (最大8.0秒 = 80回)
    timeout = 8.0
    elapsed = 0.0
    
    # キャンセルチェック用の関数
    def check_cancel():
        return session_force_stopped
    
    # バックグラウンドタスクで2.5秒後にセッションを強制終了するシミュレーション
    async def simulate_session_stop_after_delay():
        nonlocal session_force_stopped
        await asyncio.sleep(2.5)
        print("🛑 [Simulation] Session force_stop triggered (e.g. by `/stop_quiz`)!")
        session_force_stopped = True

    stop_task = asyncio.create_task(simulate_session_stop_after_delay())
    
    print("🎙️ Starting 8-second recording wait loop with check_cancel...")
    loop_interrupted = False
    
    for _ in range(int(timeout * 10)):
        # done フラグ、またはキャンセルチェック関数の検知
        if check_cancel():
            loop_interrupted = True
            break
        await asyncio.sleep(0.1)
        elapsed += 0.1

    await stop_task
    
    print("\n--- Simulation Result ---")
    print(f"Total loop time elapsed: {elapsed:.2f} seconds")
    if loop_interrupted:
        print("✅ PASS: The recording loop interrupted successfully and stopped as soon as session cancel was triggered!")
    else:
        print("❌ FAIL: The recording loop ignored the cancel trigger.")

if __name__ == "__main__":
    asyncio.run(simulate_cancellation_interruption())
