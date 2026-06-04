#!/usr/bin/env python3
import csv
import os
import sys
import yt_dlp

CSV_PATH = '/home/sbhr/git/quiz-disco-bot/data/intro/2006-2015アニソンイントロ.csv'

# Dictionary mapping row index (1-indexed, corresponding to row number in Excel/CSV reader starting from 1 for data rows)
# to their corrected metadata: (Correct Title / Artist, Correction Description)
METADATA_CORRECTIONS = {
    57: { # Line 58 in raw CSV (row 57 in data list)
        "answer": "デート・ア・ライブ / sweet ARMS",
        "desc": "Corrected corrupted title 'Date in the Stark / alignment'"
    },
    68: { # Line 69 in raw CSV (row 68 in data list)
        "answer": "Daydream café / Petit Rabbit's",
        "desc": "Corrected corrupted title '天チカホウチ / 天天座理世、香風智乃、保登心愛'"
    },
    69: { # Line 70 in raw CSV (row 69 in data list)
        "answer": "ミカヅキ / さユり",
        "desc": "Corrected corrupted title '世迷言 / さユり' (explanation describes Mikazuki)"
    },
    79: { # Line 80 in raw CSV (row 79 in data list)
        "answer": "daze / じん feat. MARiA from GARNiDELiA",
        "desc": "Corrected corrupted title '素晴らしい世界 / じん' (explanation describes daze)"
    },
    82: { # Line 83 in raw CSV (row 82 in data list)
        "answer": "M@STERPIECE / 765PRO ALLSTARS",
        "desc": "Corrected corrupted title 'らむね色のプロローグ / 765PRO ALLSTARS' (explanation describes M@STERPIECE)"
    }
}

# List of row indices (1-indexed data rows) that failed in the first search run and need robust fallback search
FAILED_ROW_INDICES = [34, 49] # Departures (34), 紅蓮の弓矢 (49)

def search_youtube_robust(query):
    print(f"Searching YouTube for: '{query}'...")
    ydl_opts = {
        'quiet': True,
        'default_search': 'ytsearch5', # Fetch top 5 results to ensure we find a playable one
        'extract_flat': True,          # Flat extraction (never throws on premium/restricted videos)
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info and info['entries']:
                for idx, entry in enumerate(info['entries'], start=1):
                    if not entry:
                        continue
                    video_id = entry.get('id')
                    video_title = entry.get('title')
                    
                    if not video_id:
                        continue
                        
                    # Verify playability and duration of this specific video
                    try:
                        check_opts = {
                            'quiet': True,
                            'no_warnings': True,
                        }
                        with yt_dlp.YoutubeDL(check_opts) as checker:
                            v_info = checker.extract_info(video_id, download=False)
                            duration = v_info.get('duration', 0)
                            
                            # Filter out ultra-short or ultra-long videos
                            if duration and (duration < 50 or duration > 900):
                                print(f"  [Skip] Result #{idx} '{video_title}' due to duration ({duration}s)")
                                continue
                                
                            # If extraction succeeded and duration is good, we have our winner!
                            print(f"  [Match] Successfully verified playable result #{idx}: '{video_title}'")
                            return f"https://www.youtube.com/watch?v={video_id}", video_title
                    except Exception as ve:
                        # Video is premium-only, deleted, or geo-restricted - skip safely!
                        print(f"  [Skip] Result #{idx} '{video_title}' failed verification: {ve}")
                        continue
        except Exception as e:
            print(f"Error during search: {e}", file=sys.stderr)
            
    return None, None

def main():
    print("--- Starting YouTube URL Refinement & Metadata Correction ---")
    
    if not os.path.exists(CSV_PATH):
        print(f"Error: CSV not found at {CSV_PATH}", file=sys.stderr)
        sys.exit(1)
        
    entries = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            entries.append(row)
            
    print(f"Loaded {len(entries)} entries from database.")
    
    # Run corrections and searches
    # Target rows are: all metadata corrections + all previously failed rows
    target_rows = set(METADATA_CORRECTIONS.keys()).union(set(FAILED_ROW_INDICES))
    
    print(f"Identified {len(target_rows)} target rows for refinement.")
    
    updated_count = 0
    
    for idx, row in enumerate(entries, start=1):
        if idx not in target_rows:
            continue
            
        print("\n" + "="*80)
        print(f"Refining Row #{idx}:")
        print(f"  Original CSV Title: {row['answer']}")
        print(f"  Original CSV URL  : {row['question']}")
        
        # 1. Apply metadata correction if applicable
        if idx in METADATA_CORRECTIONS:
            correction = METADATA_CORRECTIONS[idx]
            row['answer'] = correction['answer']
            print(f"  -> Applied Metadata Correction: '{correction['answer']}' ({correction['desc']})")
            
        # 2. Run robust search
        query = row['answer'].replace(' / ', ' ').strip()
        new_url, matched_title = search_youtube_robust(query)
        
        if new_url:
            row['question'] = new_url
            updated_count += 1
            print(f"  -> Updated URL to: {new_url}")
            print(f"  -> Matched Title : {matched_title}")
        else:
            print(f"  -> ERROR: Could not find any playable public video for '{query}'!", file=sys.stderr)
            
    # Write updated entries back to CSV
    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(entries)
        
    print("\n" + "="*80)
    print("--- Refinement Process Completed! ---")
    print(f"Successfully refined and updated {updated_count} records.")
    print(f"CSV database finalized at: {CSV_PATH}")

if __name__ == '__main__':
    main()
