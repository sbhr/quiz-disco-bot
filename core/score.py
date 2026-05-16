import sqlite3
import os

class ScoreManager:
    def __init__(self, db_path="data/quiz.db"):
        self.db_path = db_path
        self.scores = {}  # セッションごとのスコア（オンメモリ）
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id INTEGER PRIMARY KEY, 
                      lifetime_score INTEGER DEFAULT 0, 
                      total_wins INTEGER DEFAULT 0)''')
        conn.commit()
        conn.close()

    def add_score(self, user_id: int, points: int = 1):
        """現在のセッションと生涯スコアの両方に加算する"""
        # セッションスコアの更新
        if user_id not in self.scores:
            self.scores[user_id] = 0
        self.scores[user_id] += points
        
        # 生涯スコアの更新
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        c.execute("UPDATE users SET lifetime_score = lifetime_score + ? WHERE user_id = ?", (points, user_id))
        conn.commit()
        conn.close()

    def add_win(self, user_id: int):
        """優勝回数を加算する"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        c.execute("UPDATE users SET total_wins = total_wins + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    def get_score(self, user_id: int) -> int:
        """現在のセッションでのスコアを取得"""
        return self.scores.get(user_id, 0)

    def get_lifetime_stats(self, user_id: int) -> dict:
        """生涯統計を取得"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT lifetime_score, total_wins FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {"lifetime_score": row[0], "total_wins": row[1]}
        return {"lifetime_score": 0, "total_wins": 0}
    
    def get_all_scores(self) -> dict:
        """現在のセッションの全スコアを取得"""
        return self.scores

    def reset_scores(self):
        """現在のセッションのスコアをリセット"""
        self.scores = {}
