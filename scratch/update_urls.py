#!/usr/bin/env python3
import csv
import os
import sys
import time
import yt_dlp

CSV_PATH = '/home/sbhr/git/quiz-disco-bot/data/intro/2006-2015アニソンイントロ.csv'
BACKUP_PATH = CSV_PATH + '.bak'

def clean_query(answer):
    # Replace ' / ' with ' ' for cleaner search queries
    return answer.replace(' / ', ' ').strip()

def search_youtube(query):
    ydl_opts = {
        'quiet': True,
        'default_search': 'ytsearch3', # Search top 3 results to allow filtering
        'max_downloads': 1,
        'noprogress': True,
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # We search for the query and retrieve metadata
            info = ydl.extract_info(query, download=False)
            if 'entries' in info and info['entries']:
                for entry in info['entries']:
                    if not entry:
                        continue
                    duration = entry.get('duration', 0)
                    # Filter: skip videos longer than 15 minutes (900s) or shorter than 50 seconds
                    # (since these might be 10-hour loops or 15-second previews)
                    if duration and (duration < 50 or duration > 900):
                        continue
                    
                    video_id = entry.get('id')
                    video_title = entry.get('title')
                    if video_id:
                        return f"https://www.youtube.com/watch?v={video_id}", video_title
                
                # If all top 3 were filtered out, fallback to the first result
                first_entry = info['entries'][0]
                if first_entry:
                    video_id = first_entry.get('id')
                    video_title = first_entry.get('title')
                    if video_id:
                        return f"https://www.youtube.com/watch?v={video_id}", video_title
        except Exception as e:
            print(f"Error searching for '{query}': {e}", file=sys.stderr)
    return None, None

def main():
    print("--- Starting YouTube URL Refinement Script ---")
    
    # 1. Read CSV entries
    if not os.path.exists(CSV_PATH):
        print(f"Error: CSV file not found at {CSV_PATH}", file=sys.stderr)
        sys.exit(1)
        
    entries = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            entries.append(row)
            
    print(f"Successfully loaded {len(entries)} entries from {CSV_PATH}")
    
    # 2. Create backup of original CSV
    if not os.path.exists(BACKUP_PATH):
        import shutil
        shutil.copyfile(CSV_PATH, BACKUP_PATH)
        print(f"Created backup of original file at: {BACKUP_PATH}")
    else:
        print(f"Backup already exists at: {BACKUP_PATH}")

    # 3. Process entries and search YouTube
    updated_count = 0
    skipped_count = 0
    errors_count = 0
    
    start_time = time.time()
    
    print("\nProcessing and searching for songs on YouTube...")
    print(f"{'No.':<4} | {'Song & Artist':<50} | {'Status':<10} | {'Matched Video Title'}")
    print("-" * 120)
    
    for idx, row in enumerate(entries, start=1):
        answer = row['answer']
        old_url = row['question']
        explanation = row['explanation']
        
        query = clean_query(answer)
        
        # Perform search
        new_url, matched_title = search_youtube(query)
        
        if new_url:
            # We parse the video ID from both old and new URLs to check if they match (ignoring time parameters)
            old_vid = old_url.split('v=')[-1].split('&')[0] if 'v=' in old_url else ''
            new_vid = new_url.split('v=')[-1].split('&')[0] if 'v=' in new_url else ''
            
            # Check if old and new video IDs match
            if old_vid == new_vid:
                status = "Unchanged"
                skipped_count += 1
            else:
                status = "Updated"
                row['question'] = new_url
                updated_count += 1
                
            print(f"{idx:<4} | {answer[:50]:<50} | {status:<10} | {matched_title[:50]}")
        else:
            status = "ERROR"
            errors_count += 1
            print(f"{idx:<4} | {answer[:50]:<50} | {status:<10} | Could not find any match")
            
        # Standard politeness delay to avoid rate-limiting
        time.sleep(1.0)
        
    # 4. Write back corrected data
    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(entries)
        
    duration = time.time() - start_time
    print("-" * 120)
    print("--- Processing Completed ---")
    print(f"Total time: {duration:.2f} seconds")
    print(f"Updated: {updated_count} URLs")
    print(f"Unchanged: {skipped_count} URLs")
    print(f"Errors/Failed: {errors_count} URLs")
    print(f"Refined CSV written back to: {CSV_PATH}")

if __name__ == '__main__':
    main()
