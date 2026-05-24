import asyncio
import os
import sys
import wave
import struct

# Add project root to path
sys.path.append(os.getcwd())

from core.answer import AnswerValidator

async def test_voice_validation():
    # 1. テスト用の無音WAVファイルを生成
    test_wav = "test_silence.wav"
    print(f"Creating silent test WAV file: {test_wav}")
    with wave.open(test_wav, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        # 5秒分の無音データ
        w.writeframes(b'\x00' * (48000 * 2 * 5))

    try:
        validator = AnswerValidator()
        
        question = "日本の首都はどこでしょう？"
        correct_answer = "東京"
        
        print("\n--- Testing validate_voice with silent audio ---")
        print(f"Question: {question}")
        print(f"Correct Answer: {correct_answer}")
        
        # 判定を実行
        transcript, is_correct = await validator.validate_voice(test_wav, correct_answer, question)
        
        print("\n--- Result ---")
        print(f"Transcript (文字起こし結果): '{transcript}'")
        print(f"Is Correct (正誤判定結果): {is_correct}")
        
        # 無音なので文字起こしは空か「」等になるはずで、正誤は当然Falseのはず
        if not is_correct:
            print("✅ PASS: Correctly identified silence as incorrect answer.")
        else:
            print("❌ FAIL: Silences shouldn't be correct.")
            
    finally:
        # クリーンアップ
        if os.path.exists(test_wav):
            os.remove(test_wav)
            print(f"Cleaned up {test_wav}")

if __name__ == "__main__":
    asyncio.run(test_voice_validation())
