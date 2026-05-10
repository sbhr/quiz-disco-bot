class ScoreManager:
    def __init__(self):
        # On-memory score storage: {user_id: score}
        # In the future, this can be replaced with SQLite logic
        self.scores = {}

    def add_score(self, user_id: int, points: int = 1):
        """Add points to a user's score."""
        if user_id not in self.scores:
            self.scores[user_id] = 0
        self.scores[user_id] += points

    def get_score(self, user_id: int) -> int:
        """Get the current score for a user."""
        return self.scores.get(user_id, 0)
    
    def get_all_scores(self) -> dict:
        """Get all scores."""
        return self.scores
