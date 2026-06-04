#!/usr/bin/env python3
import csv
import os
import sys
from update_urls import clean_query, search_youtube

CSV_PATH = '/home/sbhr/git/quiz-disco-bot/data/intro/2006-2015アニソンイントロ.csv'

def main():
    print("--- Running Subset Search Test (First 5 Songs) ---")
    if not os.path.exists(CSV_PATH):
        print(f"Error: CSV file not found at {CSV_PATH}")
        sys.exit(1)
        
    entries = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append(row)
            
    test_subset = entries[:5]
    print(f"Loaded {len(test_subset)} songs for testing.")
    
    print(f"{'No.':<4} | {'Song & Artist':<50} | {'Old URL':<45} | {'New URL':<45} | {'Match Title'}")
    print("-" * 170)
    
    for idx, row in enumerate(test_subset, start=1):
        answer = row['answer']
        old_url = row['question']
        
        query = clean_query(answer)
        new_url, matched_title = search_youtube(query)
        
        print(f"{idx:<4} | {answer[:50]:<50} | {old_url[:45]:<45} | {new_url[:45] if new_url else 'FAILED':<45} | {matched_title[:45] if matched_title else 'N/A'}")
        
    print("-" * 170)
    print("Subset test complete!")

if __name__ == '__main__':
    main()
