#!/usr/bin/env python3
import csv
import os

CSV_PATH = '/home/sbhr/git/quiz-disco-bot/data/intro/2006-2015アニソンイントロ.csv'

def main():
    if not os.path.exists(CSV_PATH):
        print(f"Error: CSV not found at {CSV_PATH}")
        return

    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        print(f"{'Idx':<4} | {'CSV Answer (Title / Artist)':<60} | {'Explanation (First 60 chars)'}")
        print("-" * 130)
        for idx, row in enumerate(reader, start=1):
            ans = row['answer']
            exp = row['explanation'].replace('\n', ' ')
            print(f"{idx:<4} | {ans[:60]:<60} | {exp[:60]}")

if __name__ == '__main__':
    main()
