import csv
import random
import os
import glob
import sqlite3
import json
from typing import Dict, Optional, List, Set

class QuestionStore:
    def __init__(self, data_dir: str, db_path: str = "data/quiz.db", log_path: str = "logs/answer_validation.jsonl"):
        self.data_dir = data_dir
        self.db_path = db_path
        self.log_path = log_path
        # { "genre_name": [ {question, answer, ...}, ... ] }
        self.questions_by_genre: Dict[str, List[Dict[str, str]]] = {}
        # Used questions tracking by genre: { "genre_name": set(question_texts) }
        self.used_questions: Dict[str, Set[str]] = {}
        
        self._load_questions()
        self._init_db()
        self._load_used_questions_from_db()
        self._import_used_questions_from_log_if_empty()

    def _init_db(self):
        """SQLite データベースの初期化とテーブル作成"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS used_questions
                     (genre TEXT, 
                      question_text TEXT, 
                      PRIMARY KEY (genre, question_text))''')
        conn.commit()
        conn.close()

    def _load_used_questions_from_db(self):
        """SQLite から出題履歴をメモリに読み込む"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT genre, question_text FROM used_questions")
        rows = c.fetchall()
        conn.close()

        for genre, question_text in rows:
            if genre not in self.used_questions:
                self.used_questions[genre] = set()
            self.used_questions[genre].add(question_text)

    def _import_used_questions_from_log_if_empty(self):
        """データベースが空の場合のみ、ログファイルから既出問題をインポートする"""
        # 既にデータベースにデータがある場合はインポートをスキップ
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM used_questions")
        count = c.fetchone()[0]
        conn.close()

        if count > 0:
            return

        log_path = self.log_path
        if not os.path.exists(log_path):
            return

        print(f"[{self.__class__.__name__}] SQLite 履歴が空のため、{log_path} からのインポートを開始します...")
        
        imported_count = 0
        parsed_questions = set()
        
        try:
            with open(log_path, mode='r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        question = data.get('question')
                        if question:
                            parsed_questions.add(question)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Failed to read logs for import: {e}")
            return

        if not parsed_questions:
            return

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # パースした問題をジャンル判定してインサート
        for question in parsed_questions:
            found_genres = []
            
            # 各ジャンルに属するかチェック
            for genre, q_list in self.questions_by_genre.items():
                if any(q.get('question', '') == question for q in q_list):
                    found_genres.append(genre)
                    
                    if genre not in self.used_questions:
                        self.used_questions[genre] = set()
                    self.used_questions[genre].add(question)
                    
                    c.execute("INSERT OR IGNORE INTO used_questions (genre, question_text) VALUES (?, ?)", (genre, question))
                    imported_count += 1
            
            # 'all' 側にも追加
            if 'all' not in self.used_questions:
                self.used_questions['all'] = set()
            self.used_questions['all'].add(question)
            c.execute("INSERT OR IGNORE INTO used_questions (genre, question_text) VALUES (?, ?)", ('all', question))
            imported_count += 1

        conn.commit()
        conn.close()
        print(f"[{self.__class__.__name__}] {log_path} から {imported_count} 件の既出履歴を SQLite にインポートしました。")

    def _load_questions(self):
        """Load questions from all CSV files in the data directory."""
        if not os.path.exists(self.data_dir):
            print(f"Directory {self.data_dir} does not exist.")
            return

        csv_files = glob.glob(os.path.join(self.data_dir, "*.csv"))
        for file_path in csv_files:
            genre_name = os.path.splitext(os.path.basename(file_path))[0]
            try:
                with open(file_path, mode='r', encoding='utf-8') as f:
                    # Check if the first line contains a header
                    first_line = f.readline()
                    f.seek(0)
                    
                    if first_line and "question" in first_line.lower() and "answer" in first_line.lower():
                        reader = csv.DictReader(f)
                    else:
                        # Fallback for CSVs without headers
                        reader = csv.DictReader(f, fieldnames=['question', 'answer', 'explanation'])
                        
                    self.questions_by_genre[genre_name] = [row for row in reader]
            except Exception as e:
                print(f"Failed to load questions from {file_path}: {e}")

    def get_random_question(self, genre: str = "all", unique: bool = True) -> Optional[Dict[str, str]]:
        """Return a random question dictionary from the specified genre."""
        available_questions = []

        if genre == "all":
            for q_list in self.questions_by_genre.values():
                available_questions.extend(q_list)
        else:
            if genre not in self.questions_by_genre:
                return None
            available_questions = self.questions_by_genre[genre]

        if not available_questions:
            return None

        # 重複回避が無効（OFF）の場合
        if not unique:
            return random.choice(available_questions)

        # 重複回避が有効（ON）の場合
        if genre not in self.used_questions:
            self.used_questions[genre] = set()

        # 既出でない問題をフィルタリング
        filtered_questions = [q for q in available_questions if q.get('question', '') not in self.used_questions[genre]]

        was_reset = False
        # すべて出尽くした場合、履歴をリセット
        if not filtered_questions:
            print(f"[{self.__class__.__name__}] ジャンル '{genre}' のすべての問題が出尽くしたため、出題履歴をリセットします。")
            self.used_questions[genre].clear()
            
            # SQLite からジャンルのデータを削除
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("DELETE FROM used_questions WHERE genre = ?", (genre,))
            conn.commit()
            conn.close()
            
            filtered_questions = available_questions
            was_reset = True

        chosen = random.choice(filtered_questions)
        question_text = chosen.get('question', '')

        # メモリ上の履歴に追加
        self.used_questions[genre].add(question_text)

        # SQLite データベースへ保存
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO used_questions (genre, question_text) VALUES (?, ?)", (genre, question_text))

        # 双方向の履歴同期: 元のジャンルを特定して追加
        for g_name, q_list in self.questions_by_genre.items():
            if any(q.get('question', '') == question_text for q in q_list):
                if g_name not in self.used_questions:
                    self.used_questions[g_name] = set()
                self.used_questions[g_name].add(question_text)
                c.execute("INSERT OR IGNORE INTO used_questions (genre, question_text) VALUES (?, ?)", (g_name, question_text))

        # 'all' 側にも追加
        if 'all' not in self.used_questions:
            self.used_questions['all'] = set()
        self.used_questions['all'].add(question_text)
        c.execute("INSERT OR IGNORE INTO used_questions (genre, question_text) VALUES (?, ?)", ('all', question_text))

        conn.commit()
        conn.close()

        # リセットが発生した場合はメタデータを付与して返す
        if was_reset:
            chosen = chosen.copy()
            chosen['_was_reset'] = True

        return chosen

    def reset_used_questions(self, genre: str = None):
        """Reset the used questions tracking. If genre is specified, reset only that genre's tracking."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        if genre:
            if genre in self.used_questions:
                self.used_questions[genre].clear()
            c.execute("DELETE FROM used_questions WHERE genre = ?", (genre,))
        else:
            self.used_questions.clear()
            c.execute("DELETE FROM used_questions")
            
        conn.commit()
        conn.close()

