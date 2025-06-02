import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext
import json
import pygame
import os
import re
import numpy as np
import librosa
import time
import math

class GitaWaveformTagger:
    def __init__(self, root):
        self.root = root
        self.root.title("Gita Audio Tagger")
        self.root.geometry("1400x900")
        
        # Initialize pygame for audio playback
        pygame.init()
        pygame.mixer.init()
        
        # Initialize variables
        self.audio_file = None
        self.verse_data = None
        self.y = None  # Audio time series
        self.sr = None  # Sample rate
        self.segments = []  # List of (start, end, label, tag_type) tuples
        self.current_selection = None  # Currently selected segment (start, end)
        self.selected_segment_index = None
        self.is_playing = False
        self.segment_start = None  # Temporarily store segment start time
        self.segment_end = None    # Temporarily store segment end time
        self.current_label = None
        self.current_tag_type = "word"  # Default tag type (word or line)
        self.all_verses = []  # To store all verse data from JSON
        self.chapter = None
        self.verse = None
        self.current_playback_position = 0  # Current playback position in seconds
        self.audio_duration = 0  # Duration of audio in seconds
        
        # Set up the UI
        self.setup_ui()
        print("UI Setted")
    
        
        # Set up keyboard shortcuts
        self.setup_shortcuts()
        
        # Auto-load resources
        self.auto_load_resources()
        
    def auto_load_resources(self):
        """Automatically load gita.json and BrajaBeats folder if available"""
        # Load gita.json
        gita_json_path = os.path.join(os.getcwd(), "gita.json")
        if os.path.exists(gita_json_path):
            self.load_gita_data_file(gita_json_path)
            
        # Load BrajaBeats folder
        braja_folder = os.path.join(os.getcwd(), "BrajaBeats_Gita_MP3")
        # if os.path.exists(braja_folder) and os.path.isdir(braja_folder):
        #     self.load_audio_directory_path(braja_folder)
            
    def setup_ui(self):
        # Create main frames
        self.top_frame = tk.Frame(self.root)
        self.top_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.audio_control_frame = tk.Frame(self.root)
        self.audio_control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.controls_frame = tk.Frame(self.root)
        self.controls_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.bottom_frame = tk.Frame(self.root)
        self.bottom_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Top frame controls (file loading)
        tk.Button(self.top_frame, text="Load Audio", command=self.load_audio).pack(side=tk.LEFT, padx=5)
        tk.Button(self.top_frame, text="Browse Directory", command=self.list_audio_directory).pack(side=tk.LEFT, padx=5)
        tk.Button(self.top_frame, text="Load Gita Data", command=self.load_gita_data).pack(side=tk.LEFT, padx=5)
        
        # Navigation frame for chapter/verse selection
        nav_frame = tk.Frame(self.top_frame)
        nav_frame.pack(side=tk.LEFT, padx=20)
        
        tk.Label(nav_frame, text="Chapter:").pack(side=tk.LEFT, padx=2)
        self.chapter_var = tk.StringVar()
        self.chapter_entry = tk.Entry(nav_frame, textvariable=self.chapter_var, width=5)
        self.chapter_entry.pack(side=tk.LEFT, padx=2)
        
        tk.Label(nav_frame, text="Verse:").pack(side=tk.LEFT, padx=2)
        self.verse_var = tk.StringVar()
        self.verse_entry = tk.Entry(nav_frame, textvariable=self.verse_var, width=5)
        self.verse_entry.pack(side=tk.LEFT, padx=2)
        
        tk.Button(nav_frame, text="Go", command=self.go_to_verse).pack(side=tk.LEFT, padx=5)
        
        # Audio file info
        self.audio_info_var = tk.StringVar(value="No audio loaded")
        tk.Label(self.top_frame, textvariable=self.audio_info_var).pack(side=tk.RIGHT, padx=10)
        
        # Audio position slider
        self.setup_audio_controls()
        
        # Control buttons
        self.setup_control_buttons()
        
        # Bottom frame - Split into two panels
        self.setup_bottom_panels()
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        self.status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
    def setup_audio_controls(self):
        """Set up audio position slider and segment sliders"""
        # Main slider frame
        slider_frame = tk.LabelFrame(self.audio_control_frame, text="Audio Position")
        slider_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Current position display
        position_frame = tk.Frame(slider_frame)
        position_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(position_frame, text="Position:").pack(side=tk.LEFT)
        self.position_var = tk.StringVar(value="0:00.000")
        tk.Label(position_frame, textvariable=self.position_var, width=10).pack(side=tk.LEFT, padx=5)
        
        tk.Label(position_frame, text="Duration:").pack(side=tk.LEFT, padx=10)
        self.duration_var = tk.StringVar(value="0:00.000")
        tk.Label(position_frame, textvariable=self.duration_var, width=10).pack(side=tk.LEFT, padx=5)
        
        # Main audio position slider
        self.position_slider = ttk.Scale(
            slider_frame, 
            from_=0, to=100, 
            orient=tk.HORIZONTAL,
            command=self.on_position_slider_change
        )
        self.position_slider.pack(fill=tk.X, padx=10, pady=5)
        
        # Add time markers below the slider
        self.time_canvas = tk.Canvas(slider_frame, height=20, bg='white')
        self.time_canvas.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        # Segment controls in collapsible frames
        self.start_frame = tk.LabelFrame(self.audio_control_frame, text="Segment Start")
        self.end_frame = tk.LabelFrame(self.audio_control_frame, text="Segment End")
        
        # Initially hidden
        self.start_frame_visible = False
        self.end_frame_visible = False
        
    def show_start_slider(self):
        """Show the segment start slider"""
        if not self.start_frame_visible:
            self.start_frame.pack(fill=tk.X, padx=5, pady=5)
            self.start_frame_visible = True
            
            # Clear previous widgets
            for widget in self.start_frame.winfo_children():
                widget.destroy()
            
            # Start position controls
            start_controls = tk.Frame(self.start_frame)
            start_controls.pack(fill=tk.X, padx=5, pady=5)
            
            tk.Label(start_controls, text="Start Position:").pack(side=tk.LEFT)
            self.start_pos_var = tk.StringVar(value=self.format_time(self.current_playback_position))
            tk.Label(start_controls, textvariable=self.start_pos_var, width=10).pack(side=tk.LEFT, padx=5)
            
            # Set to current button
            tk.Button(
                start_controls, 
                text="Set to Current Position", 
                command=self.set_start_to_current
            ).pack(side=tk.RIGHT, padx=5)
            
            # Start position slider
            self.start_slider = ttk.Scale(
                self.start_frame, 
                from_=0, to=self.audio_duration,
                orient=tk.HORIZONTAL,
                command=self.on_start_slider_change,
                value=self.current_playback_position
            )
            self.start_slider.pack(fill=tk.X, padx=10, pady=5)
            
            # Update the start marker
            self.segment_start = self.current_playback_position
            self.update_selection()
    
    def show_end_slider(self):
        """Show the segment end slider"""
        if not self.end_frame_visible:
            self.end_frame.pack(fill=tk.X, padx=5, pady=5)
            self.end_frame_visible = True
            
            # Clear previous widgets
            for widget in self.end_frame.winfo_children():
                widget.destroy()
            
            # End position controls
            end_controls = tk.Frame(self.end_frame)
            end_controls.pack(fill=tk.X, padx=5, pady=5)
            
            tk.Label(end_controls, text="End Position:").pack(side=tk.LEFT)
            self.end_pos_var = tk.StringVar(value=self.format_time(self.current_playback_position))
            tk.Label(end_controls, textvariable=self.end_pos_var, width=10).pack(side=tk.LEFT, padx=5)
            
            # Set to current button
            tk.Button(
                end_controls, 
                text="Set to Current Position", 
                command=self.set_end_to_current
            ).pack(side=tk.RIGHT, padx=5)
            
            # End position slider
            self.end_slider = ttk.Scale(
                self.end_frame, 
                from_=0, to=self.audio_duration,
                orient=tk.HORIZONTAL,
                command=self.on_end_slider_change,
                value=self.current_playback_position
            )
            self.end_slider.pack(fill=tk.X, padx=10, pady=5)
            
            # Update the end marker
            self.segment_end = self.current_playback_position
            self.update_selection()
    
    def set_start_to_current(self):
        """Set segment start to current playback position"""
        self.segment_start = self.current_playback_position
        self.start_slider.set(self.current_playback_position)
        self.start_pos_var.set(self.format_time(self.current_playback_position))
        self.update_selection()
        self.status_var.set(f"Start point set to {self.format_time(self.current_playback_position)}")
    
    def set_end_to_current(self):
        """Set segment end to current playback position"""
        self.segment_end = self.current_playback_position
        self.end_slider.set(self.current_playback_position)
        self.end_pos_var.set(self.format_time(self.current_playback_position))
        self.update_selection()
        self.status_var.set(f"End point set to {self.format_time(self.current_playback_position)}")
    
    def on_start_slider_change(self, value):
        """Handle changes to the start position slider"""
        value = float(value)
        
        # Update segment start position
        self.segment_start = value
        self.start_pos_var.set(self.format_time(value))
        
        # Make sure start doesn't go past end
        if self.segment_end is not None and value > self.segment_end:
            self.segment_end = value
            self.end_slider.set(value)
            self.end_pos_var.set(self.format_time(value))
        
        self.update_selection()
    
    def on_end_slider_change(self, value):
        """Handle changes to the end position slider"""
        value = float(value)
        
        # Update segment end position
        self.segment_end = value
        self.end_pos_var.set(self.format_time(value))
        
        # Make sure end doesn't go before start
        if self.segment_start is not None and value < self.segment_start:
            self.segment_start = value
            self.start_slider.set(value)
            self.start_pos_var.set(self.format_time(value))
        
        self.update_selection()
    
    def on_position_slider_change(self, value):
        """Handle changes to the main position slider"""
        if not self.audio_file or self.audio_duration == 0:
            return
            
        # Convert slider value (0-100) to position in seconds
        position_pct = float(value) / 100
        position_sec = position_pct * self.audio_duration
        
        # Jump to the new position
        self.current_playback_position = position_sec
        self.position_var.set(self.format_time(position_sec))
        
        # If audio is playing, restart from new position
        if self.is_playing:
            pygame.mixer.music.play(start=position_sec)
            self._playback_start = position_sec
        
        # Draw time markers
        self.draw_time_markers()
    
    def draw_time_markers(self):
        """Draw time markers below the audio position slider"""
        self.time_canvas.delete("all")
        
        if self.audio_duration == 0:
            return
            
        # Get canvas dimensions
        width = self.time_canvas.winfo_width()
        height = self.time_canvas.winfo_height()
        
        if width <= 1:  # Not fully rendered yet
            self.root.after(100, self.draw_time_markers)
            return
        
        # Determine appropriate interval based on audio duration
        if self.audio_duration <= 10:
            interval = 1  # 1 second intervals
        elif self.audio_duration <= 60:
            interval = 5  # 5 second intervals
        elif self.audio_duration <= 300:
            interval = 30  # 30 second intervals
        else:
            interval = 60  # 1 minute intervals
        
        # Draw time markers
        for t in range(0, int(self.audio_duration) + 1, interval):
            x_pos = int((t / self.audio_duration) * width)
            self.time_canvas.create_line(x_pos, 0, x_pos, height/2, fill="black")
            self.time_canvas.create_text(x_pos, height-5, text=self.format_time(t, show_ms=False))
        
        # Draw segment markers if available
        if self.segment_start is not None:
            start_pos = int((self.segment_start / self.audio_duration) * width)
            self.time_canvas.create_line(start_pos, 0, start_pos, height, fill="red", width=2)
        
        if self.segment_end is not None:
            end_pos = int((self.segment_end / self.audio_duration) * width)
            self.time_canvas.create_line(end_pos, 0, end_pos, height, fill="green", width=2)
    
    def update_selection(self):
        """Update current selection based on segment start/end markers"""
        if self.segment_start is not None and self.segment_end is not None:
            start, end = self.segment_start, self.segment_end
            # Ensure start is before end
            if start > end:
                start, end = end, start
            
            self.current_selection = (start, end)
            dur = end - start
            self.status_var.set(f"Selection: {self.format_time(start)} - {self.format_time(end)} ({self.format_time(dur)})")
            
            # Update time markers
            self.draw_time_markers()

    def setup_control_buttons(self):
        # Playback controls
        playback_frame = tk.Frame(self.controls_frame)
        playback_frame.pack(side=tk.LEFT, padx=10)
        
        tk.Button(playback_frame, text="Play/Pause", command=self.toggle_play).pack(side=tk.LEFT, padx=5)
        tk.Button(playback_frame, text="Play Selection", command=self.play_selection).pack(side=tk.LEFT, padx=5)
        tk.Button(playback_frame, text="Stop", command=self.stop_playback).pack(side=tk.LEFT, padx=5)
        
        # Segment controls
        segment_frame = tk.Frame(self.controls_frame)
        segment_frame.pack(side=tk.LEFT, padx=10)
        
        # Add dedicated buttons for segment start/end marking
        tk.Button(segment_frame, text="Mark Start (B)", command=self.mark_segment_start, 
                 bg="#ffcccc").pack(side=tk.LEFT, padx=5)
        tk.Button(segment_frame, text="Mark End (E)", command=self.mark_segment_end, 
                 bg="#ccffcc").pack(side=tk.LEFT, padx=5)
        tk.Button(segment_frame, text="Clear Selection (C)", command=self.clear_selection).pack(side=tk.LEFT, padx=5)
        tk.Button(segment_frame, text="Add Segment (A)", command=self.add_segment).pack(side=tk.LEFT, padx=5)
        tk.Button(segment_frame, text="Delete Segment", command=self.delete_segment).pack(side=tk.LEFT, padx=5)
        
        # Tag type selection
        tag_frame = tk.Frame(self.controls_frame)
        tag_frame.pack(side=tk.LEFT, padx=20)
        
        tk.Label(tag_frame, text="Tag Type:").pack(side=tk.LEFT)
        
        self.tag_type_var = tk.StringVar(value="word")
        tag_type_combo = ttk.Combobox(tag_frame, 
                                      textvariable=self.tag_type_var, 
                                      values=["word", "line"],
                                      width=6,
                                      state="readonly")
        tag_type_combo.pack(side=tk.LEFT, padx=5)
        tag_type_combo.bind("<<ComboboxSelected>>", self.on_tag_type_change)
        
        # Navigation buttons
        nav_frame = tk.Frame(self.controls_frame)
        nav_frame.pack(side=tk.RIGHT, padx=10)
        
        tk.Button(nav_frame, text="◀ -1s", command=self.jump_back).pack(side=tk.LEFT, padx=5)
        tk.Button(nav_frame, text="+1s ▶", command=self.jump_forward).pack(side=tk.LEFT, padx=5)
    
    def on_tag_type_change(self, event):
        """Handle change to tag type"""
        self.current_tag_type = self.tag_type_var.get()
        self.status_var.set(f"Tag type set to: {self.current_tag_type}")
    
    def setup_bottom_panels(self):
        # Create a PanedWindow for splitting the bottom area
        paned = ttk.PanedWindow(self.bottom_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        # Left panel - Verse details
        left_frame = ttk.LabelFrame(paned, text="Verse Details")
        paned.add(left_frame, weight=1)
        
        self.verse_display = scrolledtext.ScrolledText(left_frame, height=10, wrap=tk.WORD)
        self.verse_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Right panel - split into top (segments list) and bottom (label input)
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)
        
        # Segments list
        segments_frame = ttk.LabelFrame(right_frame, text="Segments")
        segments_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create tree view for segments
        columns = ("Start", "End", "Duration", "Label", "Type")
        self.segments_tree = ttk.Treeview(segments_frame, columns=columns, show="headings")
        
        # Define column headings
        for col in columns:
            self.segments_tree.heading(col, text=col)
            width = 60 if col in ("Start", "End", "Duration", "Type") else 200
            self.segments_tree.column(col, width=width)
        
        self.segments_tree.pack(fill=tk.BOTH, expand=True)
        self.segments_tree.bind("<<TreeviewSelect>>", self.on_segment_select)
        
        # Scrollbar for segments tree
        scrollbar = ttk.Scrollbar(segments_frame, orient=tk.VERTICAL, command=self.segments_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.segments_tree.configure(yscrollcommand=scrollbar.set)
        
        # Custom label input
        label_frame = ttk.LabelFrame(right_frame, text="Segment Label")
        label_frame.pack(fill=tk.X, expand=False, padx=5, pady=5)
        
        label_entry_frame = ttk.Frame(label_frame)
        label_entry_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(label_entry_frame, text="Label:").pack(side=tk.LEFT)
        
        self.label_var = tk.StringVar()
        self.label_entry = tk.Entry(label_entry_frame, textvariable=self.label_var, width=40)
        self.label_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        tk.Button(label_entry_frame, text="Set Label", command=self.set_custom_label).pack(side=tk.RIGHT)
        
        # Save button at the bottom
        tk.Button(right_frame, text="Save Tagged Data", command=self.save_tagged_data, 
                 bg="#4CAF50", fg="white").pack(fill=tk.X, padx=5, pady=10)
        
    def set_custom_label(self):
        """Set the custom label for the segment"""
        label_text = self.label_var.get().strip()
        if label_text:
            self.current_label = label_text
            self.status_var.set(f"Label set to: {label_text}")
            
            # If there's a selection, add the segment right away
            if self.current_selection:
                self.add_segment()
    
    def load_audio(self):
        """Load an audio file and display its waveform"""
        audio_file = filedialog.askopenfilename(
            filetypes = [
    ("Audio Files", "*.mp3 *.wav *.ogg"),
    ("All Files", "*.*")
]
        )      
        print("")
        
        if not audio_file:
            return
            
        self.load_audio_file(audio_file)
    
    def load_audio_file(self, audio_file):
        """Load the specified audio file"""
        self.audio_file = audio_file
        self.status_var.set(f"Loading audio: {os.path.basename(audio_file)}")
        self.root.update()
        
        try:
            # Load audio data using librosa
            self.y, self.sr = librosa.load(audio_file, sr=None)
            self.audio_duration = librosa.get_duration(y=self.y, sr=self.sr)
            
            # Update audio info
            file_name = os.path.basename(audio_file)
            duration_str = time.strftime("%M:%S", time.gmtime(self.audio_duration))
            self.audio_info_var.set(f"File: {file_name} | Duration: {duration_str}")
            self.duration_var.set(self.format_time(self.audio_duration))
            
            # Reset position
            self.current_playback_position = 0
            self.position_var.set(self.format_time(0))
            self.position_slider.set(0)
            
            # Clear segments
            self.segments = []
            self.update_segments_tree()
            self.status_var.set("loading...")
            # Load audio for playback
            # start time 
            print("started")
            pygame.mixer.music.load(audio_file)
          
            # Draw time markers
            self.draw_time_markers()
            print("done"  )
            self.status_var.set(f"Loaded audio: {file_name}")
            
            # Try to extract chapter and verse from filename
            self.extract_from_audio_filename()
            
        except Exception as e:
            self.status_var.set(f"Error loading audio: {str(e)}")
    
    # Add a new method to list audio directory files
    def list_audio_directory(self):
        """Allow user to select an audio directory and list all audio files"""
        audio_dir = filedialog.askdirectory(title="Select Directory with Audio Files")
        if audio_dir:
            self.load_audio_directory_path(audio_dir)
    
    def load_audio_directory_path(self, audio_dir):
        """Load all audio files from a directory"""
        try:
            # Get all files in the directory
            all_files = os.listdir(audio_dir)
            
            # Filter for audio files
            audio_files = []
            for filename in all_files:
                if filename.lower().endswith(('.mp3', '.wav', '.ogg')):
                    full_path = os.path.join(audio_dir, filename)
                    audio_files.append(full_path)
            
            if not audio_files:
                self.status_var.set(f"No audio files found in {audio_dir}")
                return
                
            # Sort files by chapter.verse for Gita files
            audio_files.sort(key=self.sort_by_chapter_verse)
            
            # Show a dialog to select a file from the list
            dialog = tk.Toplevel(self.root)
            dialog.title("Select Audio File")
            dialog.geometry("600x400")
            
            # Add a filter input
            filter_frame = tk.Frame(dialog)
            filter_frame.pack(fill=tk.X, padx=10, pady=5)
            
            tk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT, padx=5)
            filter_var = tk.StringVar()
            filter_entry = tk.Entry(filter_frame, textvariable=filter_var, width=30)
            filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            # Add chapter/verse filter
            ch_verse_frame = tk.Frame(dialog)
            ch_verse_frame.pack(fill=tk.X, padx=10, pady=5)
            
            tk.Label(ch_verse_frame, text="Chapter:").pack(side=tk.LEFT, padx=5)
            ch_filter_var = tk.StringVar()
            ch_filter_entry = tk.Entry(ch_verse_frame, textvariable=ch_filter_var, width=5)
            ch_filter_entry.pack(side=tk.LEFT, padx=5)
            
            tk.Label(ch_verse_frame, text="Verse:").pack(side=tk.LEFT, padx=5)
            verse_filter_var = tk.StringVar()
            verse_filter_entry = tk.Entry(ch_verse_frame, textvariable=verse_filter_var, width=5)
            verse_filter_entry.pack(side=tk.LEFT, padx=5)
            
            # Function to apply filter
            def apply_filter(*args):
                filter_text = filter_var.get().lower()
                ch_filter = ch_filter_var.get()
                verse_filter = verse_filter_var.get()
                
                listbox.delete(0, tk.END)
                for file_path in audio_files:
                    filename = os.path.basename(file_path)
                    
                    # Apply text filter
                    if filter_text and filter_text not in filename.lower():
                        continue
                    
                    # Apply chapter/verse filter
                    if ch_filter or verse_filter:
                        match = re.search(r'(\d+)\.(\d+)', filename)
                        if match:
                            chapter, verse = match.groups()
                            if ch_filter and chapter != ch_filter:
                                continue
                            if verse_filter and verse != verse_filter:
                                continue
                        else:
                            # Skip if not matching pattern
                            if ch_filter or verse_filter:
                                continue
                    
                    listbox.insert(tk.END, filename)
            
            filter_var.trace("w", apply_filter)
            ch_filter_var.trace("w", apply_filter)
            verse_filter_var.trace("w", apply_filter)
            
            # Create a scrolled listbox
            frame = tk.Frame(dialog)
            frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
            scrollbar = tk.Scrollbar(frame)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            listbox = tk.Listbox(frame, yscrollcommand=scrollbar.set)
            listbox.pack(fill=tk.BOTH, expand=True)
            scrollbar.config(command=listbox.yview)
            
            # Function to handle file selection
            def on_select(event=None):
                selection = listbox.curselection()
                if selection:
                    index = selection[0]
                    filename = listbox.get(index)
                    # Find the full path
                    for file_path in audio_files:
                        if os.path.basename(file_path) == filename:
                            self.load_audio_file(file_path)
                            dialog.destroy()
                            break
            
            # Fill listbox with file names (not full paths)
            for file_path in audio_files:
                filename = os.path.basename(file_path)
                listbox.insert(tk.END, filename)
            
            # Add select button
            button_frame = tk.Frame(dialog)
            button_frame.pack(fill=tk.X, padx=10, pady=5)
            
            tk.Button(button_frame, text="Select", command=on_select).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
            
            # Double-click to select
            listbox.bind("<Double-Button-1>", on_select)
            
            # Focus the dialog
            dialog.transient(self.root)
            dialog.grab_set()
            self.root.wait_window(dialog)
            
            self.status_var.set(f"Found {len(audio_files)} audio files in directory")
            
        except Exception as e:
            self.status_var.set(f"Error loading audio directory: {str(e)}")
    
    def sort_by_chapter_verse(self, file_path):
        """Sort key for audio files based on chapter and verse numbers"""
        filename = os.path.basename(file_path)
        match = re.search(r'(\d+)\.(\d+)', filename)
        if match:
            chapter = int(match.group(1))
            verse = int(match.group(2))
            return (chapter, verse)
        return (999, 999)  # Default for files that don't match pattern
    
    def mark_segment_start(self):
        """Mark the current playback position as the start of a segment"""
        if self.y is None or self.audio_duration == 0:
            self.status_var.set("No audio loaded")
            return
            
        # Show the start slider
        self.show_start_slider()
    
    def mark_segment_end(self):
        """Mark the current playback position as the end of a segment"""
        if self.y is None or self.audio_duration == 0:
            self.status_var.set("No audio loaded")
            return
            
        # Show the end slider
        self.show_end_slider()
    
    def update_position(self):
        """Update the position indicator during playback"""
        if self.is_playing and pygame.mixer.music.get_busy():
            pos_ms = pygame.mixer.music.get_pos()
            pos_sec = pos_ms / 1000.0
            
            # If we're playing a selection, adjust the position relative to selection start
            if hasattr(self, '_playback_start'):
                pos_sec += self._playback_start
            
            # Limit to audio duration
            pos_sec = min(pos_sec, self.audio_duration)
            
            # Store current playback position
            self.current_playback_position = pos_sec
            
            # Update position display
            self.position_var.set(self.format_time(pos_sec))
            
            # Update slider position without triggering the callback
            slider_pos = (pos_sec / self.audio_duration) * 100 if self.audio_duration > 0 else 0
            self.position_slider.set(slider_pos)
            
            # Check if we need to stop at end of selection
            if self.current_selection and pos_sec >= self.current_selection[1]:
                pygame.mixer.music.stop()
                self.is_playing = False
                self.status_var.set("Playback of selection complete")
                return
            
            # Schedule next update
            self.root.after(50, self.update_position)
    
    def toggle_play(self):
        """Toggle play/pause of the entire audio file"""
        if self.audio_file is None:
            self.status_var.set("No audio file loaded")
            return
            
        if self.is_playing:
            pygame.mixer.music.pause()
            self.is_playing = False
            self.status_var.set("Playback paused")
        else:
            # Start from current position
            pygame.mixer.music.play(start=self.current_playback_position)
            self._playback_start = self.current_playback_position
            
            self.is_playing = True
            self.status_var.set("Playing audio")
            
            # Start position update loop
            self.update_position()
    
    def play_selection(self):
        """Play only the selected segment"""
        if self.audio_file is None:
            self.status_var.set("No audio file loaded")
            return
            
        if self.current_selection is None:
            self.status_var.set("No selection to play")
            return
            
        start, end = self.current_selection
        
        # Store the start time for position calculation
        self._playback_start = start
        
        # Load audio
        pygame.mixer.music.load(self.audio_file)
        
        # Start playback from selection start
        pygame.mixer.music.play(start=start)
        
        self.is_playing = True
        self.status_var.set(f"Playing selection: {self.format_time(start)} - {self.format_time(end)}")
        
        # Start position update loop
        self.update_position()
    
    def stop_playback(self):
        """Stop audio playback"""
        pygame.mixer.music.stop()
        self.is_playing = False
        self.status_var.set("Playback stopped")
    
    def clear_selection(self):
        """Clear the current selection"""
        self.current_selection = None
        self.segment_start = None
        self.segment_end = None
        
        # Hide slider frames
        if self.start_frame_visible:
            self.start_frame.pack_forget()
            self.start_frame_visible = False
            
        if self.end_frame_visible:
            self.end_frame.pack_forget()
            self.end_frame_visible = False
        
        # Redraw time markers
        self.draw_time_markers()
        
        self.status_var.set("Selection cleared")
    
    def add_segment(self):
        """Add the current selection as a new segment with a label"""
        if self.current_selection is None:
            self.status_var.set("No selection to add")
            return
            
        if self.current_label is None:
            self.status_var.set("No label entered. Please enter a label in the text field.")
            return
            
        start, end = self.current_selection
        label = self.current_label
        tag_type = self.current_tag_type
        
        # Add segment
        self.segments.append((start, end, label, tag_type))
        
        # Update display
        self.update_segments_tree()
        
        # Clear current selection
        self.clear_selection()
        
        self.status_var.set(f"Added {tag_type} segment: {self.format_time(start)} - {self.format_time(end)} with label: {label}")
    
    def delete_segment(self):
        """Delete the selected segment"""
        if self.selected_segment_index is None:
            self.status_var.set("No segment selected to delete")
            return
            
        # Get selected segment
        segment = self.segments[self.selected_segment_index]
        start, end, label, tag_type = segment
        
        # Remove segment
        self.segments.pop(self.selected_segment_index)
        
        # Update display
        self.update_segments_tree()
        
        # Clear selection
        self.selected_segment_index = None
        
        self.status_var.set(f"Deleted segment: {self.format_time(start)} - {self.format_time(end)}")
    
    def update_segments_tree(self):
        """Update the segments treeview with current segments"""
        # Clear existing items
        for item in self.segments_tree.get_children():
            self.segments_tree.delete(item)
            
        # Add all segments
        for i, (start, end, label, tag_type) in enumerate(self.segments):
            duration = end - start
            self.segments_tree.insert("", "end", values=(
                self.format_time(start),
                self.format_time(end),
                self.format_time(duration),
                label,
                tag_type
            ))
    
    def on_segment_select(self, event):
        """Handle selection of a segment in the tree view"""
        selected_items = self.segments_tree.selection()
        if not selected_items:
            self.selected_segment_index = None
            return
            
        # Get the index of the selected segment
        item = selected_items[0]
        item_index = self.segments_tree.index(item)
        self.selected_segment_index = item_index
        
        # Set current selection to match segment
        start, end, label, tag_type = self.segments[item_index]
        self.current_selection = (start, end)
        
        # Set the label entry to match the segment
        self.label_var.set(label)
        
        # Set the tag type to match the segment
        self.tag_type_var.set(tag_type)
        
        # Update slider values if visible
        if self.start_frame_visible:
            self.start_slider.set(start)
            self.start_pos_var.set(self.format_time(start))
            self.segment_start = start
            
        if self.end_frame_visible:
            self.end_slider.set(end)
            self.end_pos_var.set(self.format_time(end))
            self.segment_end = end
        
        # Update time markers
        self.draw_time_markers()
        
        self.status_var.set(f"Selected {tag_type} segment: {self.format_time(start)} - {self.format_time(end)}")
    
    def jump_back(self):
        """Jump back 1 second in the audio"""
        if self.y is None or self.audio_duration == 0:
            return
            
        # Calculate new position (1 second back)
        new_pos = max(0, self.current_playback_position - 1.0)
        
        # Update position
        self.current_playback_position = new_pos
        self.position_var.set(self.format_time(new_pos))
        
        # Update slider
        self.position_slider.set((new_pos / self.audio_duration) * 100)
        
        # If playing, jump to new position
        if self.is_playing:
            pygame.mixer.music.play(start=new_pos)
            self._playback_start = new_pos
            
        self.status_var.set(f"Jumped to {self.format_time(new_pos)}")
    
    def jump_forward(self):
        """Jump forward 1 second in the audio"""
        if self.y is None or self.audio_duration == 0:
            return
            
        # Calculate new position (1 second forward)
        new_pos = min(self.audio_duration, self.current_playback_position + 1.0)
        
        # Update position
        self.current_playback_position = new_pos
        self.position_var.set(self.format_time(new_pos))
        
        # Update slider
        self.position_slider.set((new_pos / self.audio_duration) * 100)
        
        # If playing, jump to new position
        if self.is_playing:
            pygame.mixer.music.play(start=new_pos)
            self._playback_start = new_pos
            
        self.status_var.set(f"Jumped to {self.format_time(new_pos)}")
    
    def setup_shortcuts(self):
        """Set up keyboard shortcuts for various functions"""
        # Playback shortcuts
        self.root.bind('<space>', lambda e: self.toggle_play())
        self.root.bind('s', lambda e: self.stop_playback())
        
        # Segment selection shortcuts
        self.root.bind('b', lambda e: self.mark_segment_start())  # 'b' for beginning
        self.root.bind('e', lambda e: self.mark_segment_end())    # 'e' for end
        self.root.bind('c', lambda e: self.clear_selection())     # 'c' for clear
        self.root.bind('a', lambda e: self.add_segment())         # 'a' for add
        
        # Navigation shortcuts
        self.root.bind('<Left>', lambda e: self.jump_back())
        self.root.bind('<Right>', lambda e: self.jump_forward())
        
        # Label selection shortcuts
        self.root.bind('<Control-s>', lambda e: self.save_tagged_data())

        # Tag type toggle
        self.root.bind('t', lambda e: self.toggle_tag_type())  # 't' for tag type
    
    def toggle_tag_type(self):
        """Toggle between word and line tag types"""
        if self.current_tag_type == "word":
            self.current_tag_type = "line"
        else:
            self.current_tag_type = "word"
        
        self.tag_type_var.set(self.current_tag_type)
        self.status_var.set(f"Tag type set to: {self.current_tag_type}")
    
    def load_gita_data(self):
        """Load Gita JSON data file"""
        json_file = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        
        if not json_file:
            return
            
        self.load_gita_data_file(json_file)
    
    def load_gita_data_file(self, json_file):
        """Load Gita data from specified file"""
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if isinstance(data, list):
                # It's a full Gita JSON with multiple verses
                self.all_verses = data
                self.status_var.set(f"Loaded {len(self.all_verses)} verses from Gita JSON")
                
                # Create lookup dictionary for chapter.verse
                self.verse_lookup = {}
                for i, verse in enumerate(self.all_verses):
                    if 'chapter' in verse and 'shloka' in verse:
                        key = f"{verse['chapter']}.{verse['shloka']}"
                        self.verse_lookup[key] = i
                
                # Display first verse
                if self.all_verses:
                    self.display_verse(self.all_verses[0])
            else:
                # Single verse data
                self.verse_data = data
                self.display_verse(data)
                self.status_var.set("Loaded single verse data")
        
        except Exception as e:
            self.status_var.set(f"Error loading Gita data: {str(e)}")
    
    def display_verse(self, verse_data):
        """Display verse data and populate word and line lists"""
        self.verse_data = verse_data
        
        # Update chapter and verse fields
        if 'chapter' in verse_data:
            self.chapter = verse_data['chapter']
            self.chapter_var.set(self.chapter)
        
        if 'shloka' in verse_data:
            self.verse = verse_data['shloka']
            self.verse_var.set(self.verse)
        
        # Clear verse display and update with new data
        self.verse_display.delete(1.0, tk.END)
        
        if 'sanskrit' in verse_data:
            self.verse_display.insert(tk.END, f"Sanskrit:\n{verse_data['sanskrit']}\n\n")
        
        if 'english' in verse_data:
            self.verse_display.insert(tk.END, f"English Transliteration:\n{verse_data['english']}\n\n")
        
        if 'translation' in verse_data:
            self.verse_display.insert(tk.END, f"Translation:\n{verse_data['translation']}\n\n")
        
        # Clear label entry
        self.label_var.set("")
        
        # Load segments if they exist
        if 'segments' in verse_data:
            self.segments = []
            for segment in verse_data['segments']:
                start = segment['start'] / 1000 if segment['start'] > 1000 else segment['start']
                end = segment['end'] / 1000 if segment['end'] > 1000 else segment['end']
                label = segment['label']
                tag_type = segment.get('tag', 'word')  # Default to 'word' if not specified
                
                self.segments.append((start, end, label, tag_type))
            
            self.update_segments_tree()
            self.status_var.set(f"Loaded {len(self.segments)} segments")
        else:
            # Clear segments
            self.segments = []
            self.update_segments_tree()
                    
        # Try to find and load corresponding audio file
        self.find_matching_audio()
    
    def find_matching_audio(self):
        """Try to find and load audio file matching current chapter and verse"""
        if not self.chapter or not self.verse:
            return
            
        pattern = f"{self.chapter}.{self.verse}"
        braja_dir = os.path.join(os.getcwd(), "BrajaBeats_Gita_MP3")
        
        if os.path.exists(braja_dir) and os.path.isdir(braja_dir):
            for filename in os.listdir(braja_dir):
                if pattern in filename and filename.lower().endswith(('.mp3', '.wav', '.ogg')):
                    audio_path = os.path.join(braja_dir, filename)
                    self.load_audio_file(audio_path)
                    return
    
    def go_to_verse(self):
        """Go to specific chapter and verse"""
        chapter = self.chapter_var.get()
        verse = self.verse_var.get()
        
        if not chapter or not verse:
            self.status_var.set("Please enter both chapter and verse numbers")
            return
        
        # Check if we have the verse lookup dictionary
        if hasattr(self, 'verse_lookup'):
            key = f"{chapter}.{verse}"
            if key in self.verse_lookup:
                index = self.verse_lookup[key]
                verse_data = self.all_verses[index]
                self.display_verse(verse_data)
                self.status_var.set(f"Displaying Chapter {chapter}, Verse {verse}")
                return
        
        # Fallback to linear search
        if hasattr(self, 'all_verses') and self.all_verses:
            for verse_data in self.all_verses:
                if str(verse_data.get('chapter', '')) == chapter and str(verse_data.get('shloka', '')) == verse:
                    self.display_verse(verse_data)
                    self.status_var.set(f"Displaying Chapter {chapter}, Verse {verse}")
                    return
            
            self.status_var.set(f"Chapter {chapter}, Verse {verse} not found")
        else:
            self.status_var.set("No verse data loaded")
    
    def extract_from_audio_filename(self):
        """Try to extract chapter and verse from audio filename"""
        if not self.audio_file:
            return
            
        filename = os.path.basename(self.audio_file)
        match = re.search(r'Bhagavad-gita\s+(\d+)\.(\d+)', filename)
        if match:
            chapter = match.group(1)
            verse = match.group(2)
            
            self.chapter_var.set(chapter)
            self.verse_var.set(verse)
            
            # Try to load corresponding verse data
            self.go_to_verse()
            self.status_var.set(f"Extracted Chapter {chapter}, Verse {verse} from filename")
    
    def save_tagged_data(self):
        """Save the tagged data to JSON"""
        if not self.verse_data:
            self.status_var.set("No verse data to save")
            return
            
        if not self.segments:
            self.status_var.set("No segments to save")
            return
        
        # Create simplified output data with only the required fields
        output_data = {
            "chapter": self.verse_data.get("chapter", ""),
            "shloka": self.verse_data.get("shloka", ""),
            "filename": os.path.basename(self.audio_file) if self.audio_file else "",
            "segments": []
        }
        
        # Add segments with timing and tag info
        for start, end, label, tag_type in self.segments:
            output_data['segments'].append({
                "start": int(start * 1000),  # Convert to milliseconds
                "end": int(end * 1000),
                "label": label,
                "tag": tag_type
            })
        
        # Save to file
        save_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
            initialfile=f"tagged_gita_{self.chapter}_{self.verse}.json" if self.chapter and self.verse else "tagged_gita.json"
        )
        
        if not save_path:
            return
            
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=4)
                
            self.status_var.set(f"Saved tagged data to {save_path}")
        except Exception as e:
            self.status_var.set(f"Error saving data: {str(e)}")
    
    def format_time(self, seconds, show_ms=True):
        """Format time in seconds to MM:SS.mmm format"""
        if seconds is None:
            return "00:00.000"
            
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        msecs = int((seconds - int(seconds)) * 1000)
        
        if show_ms:
            return f"{mins:02d}:{secs:02d}.{msecs:03d}"
        else:
            return f"{mins:02d}:{secs:02d}"

# Run the application
if __name__ == "__main__":
    root = tk.Tk()
    app = GitaWaveformTagger(root)
    root.mainloop()