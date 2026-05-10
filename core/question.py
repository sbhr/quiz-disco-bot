import csv
import random
from typing import Dict, Optional, List

class QuestionStore:
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.questions: List[Dict[str, str]] = []
        self._load_questions()

    def _load_questions(self):
        """Load questions from the CSV file."""
        try:
            with open(self.csv_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                self.questions = [row for row in reader]
        except Exception as e:
            print(f"Failed to load questions: {e}")
            self.questions = []

    def get_random_question(self) -> Optional[Dict[str, str]]:
        """Return a random question dictionary, or None if no questions exist."""
        if not self.questions:
            return None
        return random.choice(self.questions)
