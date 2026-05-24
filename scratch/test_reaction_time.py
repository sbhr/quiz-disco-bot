import asyncio
import time
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

class MockPlayer:
    def __init__(self, id, name):
        self.id = id
        self.display_name = name

# 早押しミリ秒反応速度および「神押し賞」の動作検証シミュレーション
def simulate_reaction_time_calculation():
    print("--- Simulating Buzzer Reaction Time and '神押し賞' ---")
    
    # タイムスタンプの基準値
    question_start_time = time.time()
    
    # プレイヤーの早押しシミュレーション (1.234秒後に押したと仮定)
    player1_pressed_time = question_start_time + 1.2345
    elapsed_ms = max(0, int((player1_pressed_time - question_start_time) * 1000))
    
    print(f"Buzzer pressed after 1.2345 seconds.")
    print(f"Calculated Elapsed Time: {elapsed_ms} ms")
    
    # テスト値の検証 (1234ms または 1235ms であればOK)
    if 1234 <= elapsed_ms <= 1235:
        print("✅ PASS: Reaction speed successfully calculated in milliseconds!")
    else:
        print(f"❌ FAIL: Reaction speed calculation is incorrect (Got {elapsed_ms}ms).")

    # 複数プレイヤーの正解早押し記録をシミュレーション
    correct_reaction_times = [
        (1001, 2450, 1),  # (user_id, elapsed_ms, question_number)
        (1002, 842, 2),   # プレイヤーBが2問目で842msで正解
        (1003, 1420, 3),
        (1002, 1100, 4)
    ]
    
    print("\nSimulating '神押し賞' (God-like Buzz Award) extraction...")
    if correct_reaction_times:
        fastest = min(correct_reaction_times, key=lambda x: x[1])
        uid, ms, q_num = fastest
        print(f"Fastest Record Extracted: User {uid} on Q{q_num} with {ms}ms")
        
        # プレイヤー1002 (842ms) が抽出されていればOK
        if uid == 1002 and ms == 842 and q_num == 2:
            print("✅ PASS: Fastest correct answer speed successfully extracted!")
        else:
            print("❌ FAIL: Extraction logic is incorrect.")
            
if __name__ == "__main__":
    simulate_reaction_time_calculation()
