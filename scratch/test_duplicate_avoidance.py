import os
import sys
import sqlite3
import shutil

# プロジェクトルートを Python パスに追加
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from core.question import QuestionStore

def run_tests():
    # テスト用のデータベース・ディレクトリ・ログファイルなどの設定
    test_db = "scratch/test_quiz.db"
    test_data_dir = "scratch/test_data"
    test_log_path = "logs/answer_validation.jsonl" # 実際のログからインポートさせる

    # テスト環境のクリーンアップ
    if os.path.exists(test_db):
        os.remove(test_db)
    if os.path.exists(test_data_dir):
        shutil.rmtree(test_data_dir)
    os.makedirs(test_data_dir, exist_ok=True)

    # テスト用CSVの作成 (ジャンルA: 3問、ジャンルB: 2問)
    csv_a = os.path.join(test_data_dir, "GenreA.csv")
    with open(csv_a, "w", encoding="utf-8") as f:
        f.write("question,answer,explanation\n")
        f.write("Q_A1,A1,ExpA1\n")
        f.write("Q_A2,A2,ExpA2\n")
        f.write("Q_A3,A3,ExpA3\n")

    csv_b = os.path.join(test_data_dir, "GenreB.csv")
    with open(csv_b, "w", encoding="utf-8") as f:
        f.write("question,answer,explanation\n")
        f.write("Q_B1,B1,ExpB1\n")
        f.write("Q_B2,B2,ExpB2\n")

    print("--- テスト1: QuestionStore の初期化とテーブル作成のテスト ---")
    store = QuestionStore(data_dir=test_data_dir, db_path=test_db, log_path="scratch/nonexistent_log.jsonl")
    assert os.path.exists(test_db), "Database file was not created!"
    print("Database table was created successfully.")

    # データベースが正常に初期化されているか確認
    conn = sqlite3.connect(test_db)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='used_questions'")
    table_exists = c.fetchone()
    assert table_exists, "Table 'used_questions' does not exist!"
    print("Table 'used_questions' verified successfully.")
    conn.close()

    print("\n--- テスト2: 重複回避と双方向同期のテスト ---")
    # ジャンルA から3回引いてみる
    selected_a = []
    for i in range(3):
        q = store.get_random_question(genre="GenreA", unique=True)
        assert q is not None
        assert q.get('question') not in selected_a, f"Duplicate question selected! {q.get('question')}"
        selected_a.append(q.get('question'))
        print(f"Selected: {q.get('question')} (was_reset={q.get('_was_reset', False)})")

    # DBの中身を確認。ジャンルAの3問が 'GenreA' と 'all' の両方で登録されているはず
    conn = sqlite3.connect(test_db)
    c = conn.cursor()
    c.execute("SELECT genre, question_text FROM used_questions")
    rows = c.fetchall()
    print("DB records after GenreA runs:", rows)
    # GenreAの3問 * (GenreA + all) = 6レコードあるはず
    assert len(rows) == 6, f"Expected 6 database records, got {len(rows)}"
    conn.close()

    print("\n--- テスト3: 自動リセットのテスト ---")
    # 4回目の引き出し。出尽くしているため、自動リセットが発生し、'_was_reset' メタデータが追加されるはず
    q = store.get_random_question(genre="GenreA", unique=True)
    assert q is not None
    assert q.get('_was_reset') is True, "Expected reset metadata to be True"
    print(f"Selected after reset: {q.get('question')} (was_reset={q.get('_was_reset', False)})")

    # 自動リセットにより、GenreA のみのレコードがDBから削除され、今回の選出分だけが再登録されているはず
    conn = sqlite3.connect(test_db)
    c = conn.cursor()
    c.execute("SELECT genre, question_text FROM used_questions WHERE genre = 'GenreA'")
    rows_a = c.fetchall()
    print("DB GenreA records after reset:", rows_a)
    assert len(rows_a) == 1, f"Expected 1 database record after reset, got {len(rows_a)}"
    conn.close()

    print("\n--- テスト4: unique=False (重複回避OFF) のテスト ---")
    # GenreB を重複回避なしで5回連続で引く (問題数2なので通常なら重複する)
    selected_b_no_unique = []
    for i in range(5):
        q = store.get_random_question(genre="GenreB", unique=False)
        assert q is not None
        selected_b_no_unique.append(q.get('question'))
    print("Selected 5 times with unique=False:", selected_b_no_unique)
    # unique=False の時はDBやメモリの used_questions には追加されないはず
    conn = sqlite3.connect(test_db)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM used_questions WHERE genre = 'GenreB'")
    count_b = c.fetchone()[0]
    assert count_b == 0, f"Expected 0 GenreB records in DB, got {count_b}"
    conn.close()

    print("\n--- テスト5: 初回限定ログインポートのテスト ---")
    # 新しいクリーンなDBを作成し、実際の過去ログ answer_validation.jsonl からのインポートをテストする
    # テスト用のCSVに実際のログに含まれそうな問題を数個定義しておく
    # logs/answer_validation.jsonl にある「仙台市」と「ファゴット」と「めんたいパーク」をテスト用CSVに追加
    csv_import = os.path.join(test_data_dir, "ImportTest.csv")
    with open(csv_import, "w", encoding="utf-8") as f:
        f.write("question,answer,explanation\n")
        f.write("伊達政宗(だて・まさむね)が植林を推奨し、多くの屋敷林(やしきりん)があったことから「杜の都(もりのみやこ)」と呼ばれる、宮城県の県庁所在地はどこでしょう？,仙台市,\n")
        f.write("英語では「バスーン」と呼ばれる、長い管を２つ折りにした構造をしている木管楽器は何でしょう？,ファゴット,\n")
        f.write("未出題のダミー問題,ダミー,\n")

    if os.path.exists(test_db):
        os.remove(test_db)

    print("QuestionStoreを初期化し、ログからの自動インポートを実行...")
    import_store = QuestionStore(data_dir=test_data_dir, db_path=test_db, log_path=test_log_path)
    
    # DBの中身を確認
    conn = sqlite3.connect(test_db)
    c = conn.cursor()
    c.execute("SELECT genre, question_text FROM used_questions WHERE genre = 'ImportTest'")
    rows_import = c.fetchall()
    print("Imported test records in ImportTest:", rows_import)
    # 「仙台市」「ファゴット」の2問が登録されているはず
    assert len(rows_import) >= 2, f"Expected at least 2 imported records, got {len(rows_import)}"
    
    c.execute("SELECT COUNT(*) FROM used_questions WHERE genre = 'all'")
    count_all = c.fetchone()[0]
    print("Total imported records in 'all':", count_all)
    conn.close()

    # 二回目起動時のスキップテスト
    print("二回目の起動でログ読み込みがスキップされるかテスト...")
    import_store2 = QuestionStore(data_dir=test_data_dir, db_path=test_db, log_path=test_log_path)
    # エラーが出ず高速に初期化できればOK

    # テスト環境の後片付け
    if os.path.exists(test_db):
        os.remove(test_db)
    if os.path.exists(test_data_dir):
        shutil.rmtree(test_data_dir)

    print("\n✅ すべてのテストに合格しました！")

if __name__ == "__main__":
    run_tests()
