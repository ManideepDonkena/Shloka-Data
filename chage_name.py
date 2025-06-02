import os
import re

# Directory containing the MP3 files
mp3_directory = "BrajaBeats_Gita_MP3"

# Regular expressions to match patterns to remove
youtube_id_pattern = r'\s+\[[a-zA-Z0-9_-]+\]'  # For YouTube ID in square brackets
shorts_pattern = r'#.*(?=\.mp3)'  # Removes everything from first # to .mp3 extension

# Check if directory exists
if not os.path.exists(mp3_directory):
    print(f"Directory '{mp3_directory}' does not exist!")
else:
    # Iterate through all files in the directory
    renamed_count = 0
    for filename in os.listdir(mp3_directory):
        # Check if the file is an MP3 file
        print(f"Checking: {filename}")
        if filename.endswith(".mp3"):
            print(f"Processing: {filename}")

            # Full path to the file
            file_path = os.path.join(mp3_directory, filename)
            
            # Create new filename by removing both patterns
            new_filename = re.sub(youtube_id_pattern, '', filename)
            new_filename = re.sub(shorts_pattern, '', new_filename)
            print(f"Original: {filename} -> New: {new_filename}")
            # Remove any trailing spaces before .mp3
            new_filename = re.sub(r'\s+\.mp3$', '.mp3', new_filename)
            
            # Only rename if there was a change
            if new_filename != filename:
                new_file_path = os.path.join(mp3_directory, new_filename)
                
                try:
                    # Rename the file
                    os.rename(file_path, new_file_path)
                    
                    # Print what was done
                    print(f"Renamed: {filename} -> {new_filename}")
                    renamed_count += 1
                except Exception as e:
                    print(f"Error renaming {filename}: {e}")
    
    print(f"\nCompleted! {renamed_count} files were renamed.")