import csv
import random
import os
import glob
from typing import Dict, Optional, List

class QuestionStore:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        # { "genre_name": [ {question, answer, ...}, ... ] }
        self.questions_by_genre: Dict[str, List[Dict[str, str]]] = {}
        # Used questions tracking by question text
        self.used_questions = set()
        self._load_questions()

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

    def get_random_question(self, genre: str = "all") -> Optional[Dict[str, str]]:
        """Return a random question dictionary from the specified genre."""
        available_questions = []

        if genre == "all":
            for q_list in self.questions_by_genre.values():
                available_questions.extend(q_list)
        else:
            if genre not in self.questions_by_genre:
                return None
            available_questions = self.questions_by_genre[genre]

        # Filter out already used questions
        filtered_questions = [q for q in available_questions if q.get('question', '') not in self.used_questions]

        if not filtered_questions:
            return None
            
        chosen = random.choice(filtered_questions)
        self.used_questions.add(chosen.get('question', ''))
        return chosen

    def reset_used_questions(self):
        """Reset the used questions tracking."""
        self.used_questions.clear()
