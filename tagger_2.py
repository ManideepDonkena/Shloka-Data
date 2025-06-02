import tkinter as tk
from tkinter import filedialog, ttk, messagebox, scrolledtext
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.patches as patches
import librosa
import librosa.display
import numpy as np
import pygame
import matplotlib.lines as mlines
import math
import json
import os
import re
import time

class AudacityInspiredGitaTagger:
    def __init__(self, root):
        self.root = root
        self.root.title("Gita Audio Tagger - Audacity Style")
        self.root.geometry("1600x900")
        
        # Initialize pygame for audio
        pygame.init()
        pygame.mixer.init()
        
        # Initialize variables
        self.audio_file = None
        self.y = None  # Audio time series
        self.sr = None  # Sample rate
        self.verse_data = None
        self.all_verses = []
        self.current_verse_index = 0
        self.current_word = None
        self.current_position = 0
        self.is_playing = False
        self.current_selection = [None, None]  # [start, end] in seconds
        self.audio_directory = None
        self.audio_files = []
        self.zoom_level = 1.0
        self.view_start = 0  # start position for zoomed view in seconds
        self.audio_duration = 0  # total duration in seconds
        self.view_window = 10  # visible window in seconds
        self.waveform_patches = []  # Store references to colored patches
        self.tagged_regions = {}  # Store already tagged regions
        
        # Setup UI
        self.setup_ui()
        
        # Configure keyboard shortcuts
        self.setup_shortcuts()
        
        # Start update loop for playback tracking
        self.update_playback_position()
        
        # Auto-load resources if available
        self.auto_load_resources()
    
    def auto_load_resources(self):
        """Try to automatically load Gita data and audio files if available"""
        current_dir = os.getcwd()
        
        # Try to load gita.json
        gita_json_path = os.path.join(current_dir, "gita.json")
        if os.path.exists(gita_json_path):
            self.load_gita_data_file(gita_json_path)
            
        # Try to load audio directory
        audio_dir = os.path.join(current_dir, "BrajaBeats_Gita_MP3")
        if os.path.exists(audio_dir) and os.path.isdir(audio_dir):
            self.load_audio_directory_path(audio_dir)
    
    def setup_ui(self):
        """Set up the main user interface"""
        # Create main frames
        self.create_menu()
        
        # Top section with controls
        self.top_frame = tk.Frame(self.root)
        self.top_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Waveform display in the middle
        self.waveform_frame = tk.Frame(self.root)
        self.waveform_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Transport controls below waveform
        self.transport_frame = tk.Frame(self.root)
        self.transport_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Split bottom section into two panels
        self.bottom_frame = tk.Frame(self.root)
        self.bottom_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left panel for audio files list
        self.files_frame = tk.Frame(self.bottom_frame, width=300)
        self.files_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5, pady=5)
        
        # Right panel for word tagging
        self.tag_frame = tk.Frame(self.bottom_frame)
        self.tag_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Status bar at the bottom
        self.statusbar = tk.Frame(self.root, height=20, bd=1, relief=tk.SUNKEN)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(self.statusbar, textvariable=self.status_var, anchor=tk.W).pack(side=tk.LEFT, fill=tk.X)
        
        # Position display
        self.position_var = tk.StringVar(value="00:00.000")
        tk.Label(self.statusbar, textvariable=self.position_var, width=10).pack(side=tk.RIGHT)
        
        # Set up specific content for each frame
        self.setup_top_controls()
        self.setup_waveform_display()
        self.setup_transport_controls()
        self.setup_files_panel()
        self.setup_tag_panel()
    
    def create_menu(self):
        """Create application menu"""
        menubar = tk.Menu(self.root)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Audio File", command=self.load_audio, accelerator="Ctrl+O")
        file_menu.add_command(label="Open Audio Directory", command=self.list_audio_directory)
        file_menu.add_command(label="Load Gita Data", command=self.load_gita_data)
        file_menu.add_separator()
        file_menu.add_command(label="Save Tags", command=self.save_tagged_data, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Mark Start", command=self.mark_segment_start, accelerator="B")
        edit_menu.add_command(label="Mark End", command=self.mark_segment_end, accelerator="E")
        edit_menu.add_command(label="Clear Selection", command=self.clear_selection, accelerator="C")
        edit_menu.add_command(label="Tag Selected Region", command=self.tag_selected_region, accelerator="T")
        menubar.add_cascade(label="Edit", menu=edit_menu)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Zoom In", command=self.zoom_in, accelerator="+")
        view_menu.add_command(label="Zoom Out", command=self.zoom_out, accelerator="-")
        view_menu.add_command(label="Reset Zoom", command=self.reset_zoom, accelerator="0")
        view_menu.add_separator()
        view_menu.add_command(label="Show All Tags", command=self.show_all_tags)
        menubar.add_cascade(label="View", menu=view_menu)
        
        # Playback menu
        playback_menu = tk.Menu(menubar, tearoff=0)
        playback_menu.add_command(label="Play/Pause", command=self.toggle_play, accelerator="Space")
        playback_menu.add_command(label="Stop", command=self.stop_playback, accelerator="S")
        playback_menu.add_command(label="Play Selection", command=self.play_selection, accelerator="P")
        menubar.add_cascade(label="Playback", menu=playback_menu)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Shortcuts", command=self.show_shortcuts)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.root.config(menu=menubar)
    
    def setup_top_controls(self):
        """Set up the top control panel"""
        # Left side - file controls
        file_frame = tk.Frame(self.top_frame)
        file_frame.pack(side=tk.LEFT, fill=tk.X, padx=5)
        
        tk.Button(file_frame, text="Open Audio", command=self.load_audio).pack(side=tk.LEFT, padx=2)
        tk.Button(file_frame, text="Directory", command=self.list_audio_directory).pack(side=tk.LEFT, padx=2)
        tk.Button(file_frame, text="Gita Data", command=self.load_gita_data).pack(side=tk.LEFT, padx=2)
        
        # Middle - chapter and verse selection
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
        
        # Right side - file info
        info_frame = tk.Frame(self.top_frame)
        info_frame.pack(side=tk.RIGHT, fill=tk.X, padx=5)
        
        self.file_info_var = tk.StringVar(value="No file loaded")
        tk.Label(info_frame, textvariable=self.file_info_var, anchor=tk.E).pack(side=tk.RIGHT)
    
    def setup_waveform_display(self):
        """Set up the waveform display area"""
        # Create matplotlib figure and axes
        self.fig, self.ax = plt.subplots(figsize=(14, 4), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.waveform_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Configure axes for waveform display
        self.ax.set_xlabel('Time (s)')
        self.ax.set_ylabel('Amplitude')
        self.ax.grid(True, alpha=0.3)
        
        # Placeholder text
        self.ax.text(0.5, 0.5, 'No audio loaded', 
                     ha='center', va='center', transform=self.ax.transAxes, 
                     fontsize=14, alpha=0.7)
        
        # Set up mouse events
        self.canvas.mpl_connect('button_press_event', self.on_waveform_click)
        self.canvas.mpl_connect('button_release_event', self.on_waveform_release)
        self.canvas.mpl_connect('motion_notify_event', self.on_waveform_motion)
        
        # Initialize playback position line
        self.playback_line = self.ax.axvline(x=0, color='r', linewidth=1.5, visible=False)
        
        # Add horizontal scrollbar for waveform
        self.waveform_scrollbar = ttk.Scale(
            self.waveform_frame, 
            from_=0, to=100, 
            orient=tk.HORIZONTAL,
            command=self.on_waveform_scroll
        )
        self.waveform_scrollbar.pack(fill=tk.X, padx=5)
        
        self.canvas.draw()
    
    def setup_transport_controls(self):
        """Set up playback transport controls"""
        # Time scale above transport controls
        timescale_frame = tk.Frame(self.transport_frame)
        timescale_frame.pack(fill=tk.X, pady=2)
        
        self.time_scale = tk.Canvas(timescale_frame, height=15, bg='white')
        self.time_scale.pack(fill=tk.X, padx=5)
        
        # Main transport buttons
        btn_frame = tk.Frame(self.transport_frame)
        btn_frame.pack(fill=tk.X, pady=2)
        
        # Play controls
        tk.Button(btn_frame, text="⏮", width=3, command=self.goto_start).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="◀", width=3, command=self.jump_back).pack(side=tk.LEFT, padx=2)
        self.play_btn = tk.Button(btn_frame, text="▶", width=5, command=self.toggle_play)
        self.play_btn.pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="■", width=3, command=self.stop_playback).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="▶", width=3, command=self.jump_forward).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="⏭", width=3, command=self.goto_end).pack(side=tk.LEFT, padx=2)
        
        # Middle section - Selection controls
        selection_frame = tk.Frame(btn_frame)
        selection_frame.pack(side=tk.LEFT, padx=20)
        
        tk.Button(selection_frame, text="Mark Start (B)", 
                  bg="#ffcccc", command=self.mark_segment_start).pack(side=tk.LEFT, padx=2)
        tk.Button(selection_frame, text="Mark End (E)", 
                  bg="#ccffcc", command=self.mark_segment_end).pack(side=tk.LEFT, padx=2)
        tk.Button(selection_frame, text="Clear (C)", 
                  command=self.clear_selection).pack(side=tk.LEFT, padx=2)
        tk.Button(selection_frame, text="Play Selection (P)", 
                  command=self.play_selection).pack(side=tk.LEFT, padx=2)
        
        # Right section - Zoom controls
        zoom_frame = tk.Frame(btn_frame)
        zoom_frame.pack(side=tk.RIGHT, padx=10)
        
        tk.Button(zoom_frame, text="🔍+", command=self.zoom_in).pack(side=tk.LEFT, padx=2)
        tk.Button(zoom_frame, text="🔍-", command=self.zoom_out).pack(side=tk.LEFT, padx=2)
        tk.Button(zoom_frame, text="Reset", command=self.reset_zoom).pack(side=tk.LEFT, padx=2)
    
    def setup_files_panel(self):
        """Set up the files panel with audio file list"""
        # Panel label
        tk.Label(self.files_frame, text="Audio Files", font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=5)
        
        # Search/filter controls
        filter_frame = tk.Frame(self.files_frame)
        filter_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT, padx=2)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", self.filter_audio_files)
        tk.Entry(filter_frame, textvariable=self.filter_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        tk.Button(filter_frame, text="×", command=self.clear_filter).pack(side=tk.RIGHT)
        
        # Chapter/Verse specific filter
        cv_frame = tk.Frame(self.files_frame)
        cv_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(cv_frame, text="Ch:").pack(side=tk.LEFT, padx=2)
        self.ch_filter_var = tk.StringVar()
        self.ch_filter_var.trace_add("write", self.filter_audio_files)
        tk.Entry(cv_frame, textvariable=self.ch_filter_var, width=5).pack(side=tk.LEFT, padx=2)
        
        tk.Label(cv_frame, text="Verse:").pack(side=tk.LEFT, padx=2)
        self.verse_filter_var = tk.StringVar()
        self.verse_filter_var.trace_add("write", self.filter_audio_files)
        tk.Entry(cv_frame, textvariable=self.verse_filter_var, width=5).pack(side=tk.LEFT, padx=2)
        
        # Audio files listbox with scrollbar
        listbox_frame = tk.Frame(self.files_frame)
        listbox_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        scrollbar = tk.Scrollbar(listbox_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.audio_listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set, 
                                     selectbackground="#a6a6a6", selectforeground="black",
                                     activestyle="none")
        self.audio_listbox.pack(fill=tk.BOTH, expand=True)
        self.audio_listbox.bind('<<ListboxSelect>>', self.on_audio_select)
        scrollbar.config(command=self.audio_listbox.yview)
        
        # Navigation buttons
        nav_frame = tk.Frame(self.files_frame)
        nav_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(nav_frame, text="Previous", command=self.load_previous_audio).pack(side=tk.LEFT, padx=2)
        tk.Button(nav_frame, text="Next", command=self.load_next_audio).pack(side=tk.LEFT, padx=2)
    
    def setup_tag_panel(self):
        """Set up the word tagging panel"""
        # Verse information at the top
        verse_frame = tk.LabelFrame(self.tag_frame, text="Verse Information")
        verse_frame.pack(fill=tk.X, pady=5)
        
        # Verse text display
        self.verse_text = scrolledtext.ScrolledText(verse_frame, height=5, wrap=tk.WORD)
        self.verse_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Word selection and tagging
        word_frame = tk.LabelFrame(self.tag_frame, text="Word Tagging")
        word_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Split into two columns
        word_columns = tk.Frame(word_frame)
        word_columns.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left column - word list
        word_list_frame = tk.Frame(word_columns)
        word_list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        tk.Label(word_list_frame, text="Sanskrit Words:").pack(anchor=tk.W)
        
        word_scrollbar = tk.Scrollbar(word_list_frame)
        word_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.word_listbox = tk.Listbox(word_list_frame, yscrollcommand=word_scrollbar.set,
                                     selectbackground="#a6a6a6", selectforeground="black")
        self.word_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.word_listbox.bind('<<ListboxSelect>>', self.on_word_select)
        word_scrollbar.config(command=self.word_listbox.yview)
        
        # Right column - word details and tagging
        word_details_frame = tk.Frame(word_columns)
        word_details_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)
        
        tk.Label(word_details_frame, text="Word Details:").pack(anchor=tk.W)
        
        self.word_details = scrolledtext.ScrolledText(word_details_frame, height=8, wrap=tk.WORD)
        self.word_details.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Add custom label entry
        label_frame = tk.Frame(word_frame)
        label_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(label_frame, text="Custom Label:").pack(side=tk.LEFT, padx=2)
        self.custom_label_var = tk.StringVar()
        self.custom_label_entry = tk.Entry(label_frame, textvariable=self.custom_label_var, width=30)
        self.custom_label_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        
        # Add segment type selection
        type_frame = tk.Frame(word_frame)
        type_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(type_frame, text="Segment Type:").pack(side=tk.LEFT, padx=2)
        self.segment_type_var = tk.StringVar(value="word")
        self.type_word_radio = tk.Radiobutton(type_frame, text="Word", variable=self.segment_type_var, value="word")
        self.type_word_radio.pack(side=tk.LEFT, padx=5)
        self.type_line_radio = tk.Radiobutton(type_frame, text="Line", variable=self.segment_type_var, value="line")
        self.type_line_radio.pack(side=tk.LEFT, padx=5)
        
        # Tagging controls at bottom
        tag_buttons_frame = tk.Frame(word_frame)
        tag_buttons_frame.pack(fill=tk.X, pady=5)
        
        # Main tagging button
        tk.Button(tag_buttons_frame, text="Tag Selection with Selected Word (T)", 
                  bg="#4CAF50", fg="white", 
                  command=self.tag_selected_region).pack(side=tk.LEFT, padx=2)
        
        # Add button for tagging with custom label
        tk.Button(tag_buttons_frame, text="Tag with Custom Label", 
                  bg="#4CAF50", fg="white", 
                  command=self.tag_with_custom_label).pack(side=tk.LEFT, padx=2)
                  
        # Button to play the tagged segment for selected word
        tk.Button(tag_buttons_frame, text="Play Segment", 
                  command=self.play_tagged_segment).pack(side=tk.LEFT, padx=2)
                  
        # Buttons to jump to timestamps
        tk.Button(tag_buttons_frame, text="Jump to Start", 
                  command=lambda: self.jump_to_timestamp("start")).pack(side=tk.LEFT, padx=2)
        tk.Button(tag_buttons_frame, text="Jump to End", 
                  command=lambda: self.jump_to_timestamp("end")).pack(side=tk.LEFT, padx=2)
        
        # Save all tagged data
        tk.Button(self.tag_frame, text="Save All Tagged Data", 
                  bg="#4CAF50", fg="white", 
                  command=self.save_tagged_data).pack(fill=tk.X, pady=10, padx=5)
    
    def setup_shortcuts(self):
        """Configure keyboard shortcuts"""
        # File operations
        self.root.bind('<Control-o>', lambda e: self.load_audio())
        self.root.bind('<Control-s>', lambda e: self.save_tagged_data())
        
        # Playback
        self.root.bind('<space>', lambda e: self.toggle_play())
        self.root.bind('s', lambda e: self.stop_playback())
        self.root.bind('p', lambda e: self.play_selection())
        
        # Navigation
        self.root.bind('<Left>', lambda e: self.jump_back())
        self.root.bind('<Right>', lambda e: self.jump_forward())
        self.root.bind('0', lambda e: self.reset_zoom())
        self.root.bind('h', lambda e: self.goto_start())  # Home
        self.root.bind('j', lambda e: self.goto_end())    # End (j is next to h)
        
        # Selection
        self.root.bind('b', lambda e: self.mark_segment_start())  # Begin
        self.root.bind('e', lambda e: self.mark_segment_end())    # End
        self.root.bind('c', lambda e: self.clear_selection())     # Clear
        
        # Tagging
        self.root.bind('t', lambda e: self.tag_selected_region())  # Tag
        
        # Zoom
        self.root.bind('<plus>', lambda e: self.zoom_in())
        self.root.bind('<minus>', lambda e: self.zoom_out())
    
    # ====== Audio file management functions ======
    
    def load_audio(self):
        """Open file dialog to select an audio file"""
        filetypes = [("Audio Files", "*.mp3 *.wav *.ogg")]
        audio_file = filedialog.askopenfilename(title="Select Audio File", filetypes=filetypes)
        if audio_file:
            self.load_audio_file(audio_file)
    
    def list_audio_directory(self):
        """Open directory dialog to select folder with audio files"""
        audio_dir = filedialog.askdirectory(title="Select Directory with Audio Files")
        if audio_dir:
            self.load_audio_directory_path(audio_dir)
    
    def load_audio_directory_path(self, audio_dir):
        """Load audio files from the specified directory"""
        self.audio_directory = audio_dir
        try:
            # Find MP3 files in directory
            self.audio_files = []
            for root, dirs, files in os.walk(audio_dir):
                for file in files:
                    if file.lower().endswith(('.mp3', '.wav', '.ogg')):
                        self.audio_files.append(os.path.join(root, file))
            
            # Sort files by chapter and verse if possible
            self.audio_files.sort(key=self.sort_by_chapter_verse)
            
            # Update listbox
            self.update_audio_listbox()
            
            self.status_var.set(f"Loaded {len(self.audio_files)} audio files from directory")
            
            # Load the first file if available
            if self.audio_files:
                self.load_audio_file(self.audio_files[0])
                
        except Exception as e:
            self.status_var.set(f"Error loading audio directory: {str(e)}")
    
    def sort_by_chapter_verse(self, file_path):
        """Sort key function for audio files based on chapter and verse"""
        filename = os.path.basename(file_path)
        match = re.search(r'(\d+)\.(\d+)', filename)
        if match:
            chapter = int(match.group(1))
            verse = int(match.group(2))
            return (chapter, verse)
        return (999, 999)  # Default for files that don't match pattern
    
    def update_audio_listbox(self):
        """Update the audio files listbox with filtered items"""
        self.audio_listbox.delete(0, tk.END)
        
        # Get filter values
        text_filter = self.filter_var.get().lower()
        ch_filter = self.ch_filter_var.get()
        verse_filter = self.verse_filter_var.get()
        
        # Apply filters
        filtered_files = []
        for file in self.audio_files:
            filename = os.path.basename(file)
            
            # Apply text filter
            if text_filter and text_filter not in filename.lower():
                continue
                
            # Apply chapter/verse filter if specified
            if ch_filter or verse_filter:
                match = re.search(r'(\d+)\.(\d+)', filename)
                if match:
                    chapter = match.group(1)
                    verse = match.group(2)
                    
                    if ch_filter and chapter != ch_filter:
                        continue
                    if verse_filter and verse != verse_filter:
                        continue
                else:
                    # If looking for specific chapter/verse but file doesn't match pattern
                    if ch_filter or verse_filter:
                        continue
            
            filtered_files.append(file)
            self.audio_listbox.insert(tk.END, os.path.basename(file))
        
        # Update status with filter results
        if len(filtered_files) < len(self.audio_files):
            self.status_var.set(f"Showing {len(filtered_files)} of {len(self.audio_files)} audio files")
    
    def filter_audio_files(self, *args):
        """Callback for when filter values change"""
        if hasattr(self, 'audio_listbox'):
            self.update_audio_listbox()
    
    def clear_filter(self):
        """Clear all filters"""
        self.filter_var.set("")
        self.ch_filter_var.set("")
        self.verse_filter_var.set("")
        self.update_audio_listbox()
    
    def on_audio_select(self, event):
        """Handle selection of audio file from listbox"""
        selection = self.audio_listbox.curselection()
        if selection:
            index = selection[0]
            filename = self.audio_listbox.get(index)
            
            # Find the full path in our list
            for file in self.audio_files:
                if os.path.basename(file) == filename:
                    self.load_audio_file(file)
                    break
    
    def load_audio_file(self, file_path):
        """Load an audio file and display its waveform"""
        try:
            # Load audio data with librosa
            self.y, self.sr = librosa.load(file_path, sr=None)
            self.audio_file = file_path
            self.audio_duration = len(self.y) / self.sr
            
            # Reset playback state
            pygame.mixer.music.load(file_path)
            self.is_playing = False
            self.current_position = 0
            self.view_start = 0
            self.view_window = min(self.audio_duration, 10)  # Show 10 seconds or full file
            
            # Update display
            self.plot_waveform()
            self.draw_time_scale()
            
            # Update file info
            filename = os.path.basename(file_path)
            duration_str = self.format_time(self.audio_duration)
            self.file_info_var.set(f"{filename} ({duration_str})")
            
            # Try to extract chapter/verse from filename and load corresponding data
            self.extract_chapter_verse_from_filename(filename)
            
            self.status_var.set(f"Loaded audio file: {filename}")
            
        except Exception as e:
            self.status_var.set(f"Error loading audio file: {str(e)}")
            messagebox.showerror("Error", f"Could not load audio file: {str(e)}")
    
    def extract_chapter_verse_from_filename(self, filename):
        """Extract chapter and verse numbers from filename and load verse data"""
        match = re.search(r'(\d+)\.(\d+)', filename)
        if match:
            chapter = match.group(1)
            verse = match.group(2)
            
            # Update chapter/verse entries
            self.chapter_var.set(chapter)
            self.verse_var.set(verse)
            
            # Try to load verse data
            self.go_to_verse()
    
    def load_previous_audio(self):
        """Load the previous audio file in the list"""
        if not self.audio_file or not self.audio_files:
            return
            
        current_index = self.audio_files.index(self.audio_file)
        if current_index > 0:
            self.load_audio_file(self.audio_files[current_index - 1])
            
            # Update selection in listbox
            self.audio_listbox.selection_clear(0, tk.END)
            filename = os.path.basename(self.audio_files[current_index - 1])
            
            # Find the item in the displayed listbox
            for i in range(self.audio_listbox.size()):
                if self.audio_listbox.get(i) == filename:
                    self.audio_listbox.selection_set(i)
                    self.audio_listbox.see(i)
                    break
    
    def load_next_audio(self):
        """Load the next audio file in the list"""
        if not self.audio_file or not self.audio_files:
            return
            
        current_index = self.audio_files.index(self.audio_file)
        if current_index < len(self.audio_files) - 1:
            self.load_audio_file(self.audio_files[current_index + 1])
            
            # Update selection in listbox
            self.audio_listbox.selection_clear(0, tk.END)
            filename = os.path.basename(self.audio_files[current_index + 1])
            
            # Find the item in the displayed listbox
            for i in range(self.audio_listbox.size()):
                if self.audio_listbox.get(i) == filename:
                    self.audio_listbox.selection_set(i)
                    self.audio_listbox.see(i)
                    break
    
    # ====== Gita data management functions ======
    
    def load_gita_data(self):
        """Open file dialog to select Gita JSON data file"""
        filetypes = [("JSON Files", "*.json")]
        json_file = filedialog.askopenfilename(title="Select Gita JSON File", filetypes=filetypes)
        if json_file:
            self.load_gita_data_file(json_file)
    
    def load_gita_data_file(self, json_file):
        """Load Gita verse data from JSON file"""
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                self.all_verses = json.load(f)
            
            # Create lookup dictionary for quick access by chapter and verse
            self.verse_lookup = {}
            for i, verse in enumerate(self.all_verses):
                if 'chapter' in verse and 'shloka' in verse:
                    key = f"{verse['chapter']}.{verse['shloka']}"
                    self.verse_lookup[key] = i
            
            self.status_var.set(f"Loaded {len(self.all_verses)} verses from Gita JSON")
            
            # If chapter and verse are already set, try to load that verse
            if self.chapter_var.get() and self.verse_var.get():
                self.go_to_verse()
                
        except Exception as e:
            self.status_var.set(f"Error loading Gita data: {str(e)}")
            messagebox.showerror("Error", f"Could not load Gita data: {str(e)}")
    
    def go_to_verse(self):
        """Navigate to specific chapter and verse"""
        if not self.all_verses:
            self.status_var.set("No Gita data loaded")
            return
            
        chapter = self.chapter_var.get().strip()
        verse = self.verse_var.get().strip()
        
        if not chapter or not verse:
            self.status_var.set("Please enter both chapter and verse numbers")
            return
        
        # Try to find the verse
        key = f"{chapter}.{verse}"
        if key in self.verse_lookup:
            self.current_verse_index = self.verse_lookup[key]
            self.display_verse_data()
            return
            
        # Fallback to linear search
        for i, verse_data in enumerate(self.all_verses):
            if str(verse_data.get('chapter', '')) == chapter and str(verse_data.get('shloka', '')) == verse:
                self.current_verse_index = i
                self.display_verse_data()
                return
                
        self.status_var.set(f"Chapter {chapter}, Verse {verse} not found")
    
    def display_verse_data(self):
        """Display the current verse data"""
        if not self.all_verses or self.current_verse_index >= len(self.all_verses):
            return
            
        # Get the verse data
        self.verse_data = self.all_verses[self.current_verse_index]
        
        # Initialize segments section if not present
        if 'segments' not in self.verse_data:
            self.verse_data['segments'] = []
            
        # Clear word list
        self.word_listbox.delete(0, tk.END)
        
        # Populate word list
        if 'synonyms' in self.verse_data:
            for word in self.verse_data['synonyms']:
                self.word_listbox.insert(tk.END, word)
                
        # Update verse text display
        self.verse_text.delete(1.0, tk.END)
        
        if 'sanskrit' in self.verse_data:
            self.verse_text.insert(tk.END, f"Sanskrit:\n{self.verse_data['sanskrit']}\n\n")
            
        if 'english' in self.verse_data:
            self.verse_text.insert(tk.END, f"Transliteration:\n{self.verse_data['english']}\n\n")
            
        if 'translation' in self.verse_data:
            self.verse_text.insert(tk.END, f"Translation:\n{self.verse_data['translation']}")
            
        # Show status
        self.status_var.set(
            f"Displaying verse {self.current_verse_index + 1}/{len(self.all_verses)}: " +
            f"Chapter {self.verse_data.get('chapter', '?')}, " +
            f"Verse {self.verse_data.get('shloka', '?')}"
        )
        
        # Look for corresponding audio file if not already loaded
        self.find_corresponding_audio()
        
        # Update waveform to show tagged regions for this verse
        self.show_tagged_regions()
    
    def find_corresponding_audio(self):
        """Try to find and load the audio file for the current verse"""
        if not self.audio_files or not self.verse_data:
            return
            
        chapter = self.verse_data.get('chapter')
        verse = self.verse_data.get('shloka')
        
        if not chapter or not verse:
            return
            
        # Look for pattern in filenames
        pattern = f"{chapter}.{verse}"
        for file in self.audio_files:
            filename = os.path.basename(file)
            if pattern in filename:
                # Only load if different from current file
                if self.audio_file != file:
                    self.load_audio_file(file)
                    
                    # Update selection in listbox
                    self.audio_listbox.selection_clear(0, tk.END)
                    for i in range(self.audio_listbox.size()):
                        if self.audio_listbox.get(i) == filename:
                            self.audio_listbox.selection_set(i)
                            self.audio_listbox.see(i)
                            break
                            
                return
                
        self.status_var.set(f"No matching audio found for Chapter {chapter}, Verse {verse}")
    
    def on_word_select(self, event):
        """Handle selection of a Sanskrit word from the word list"""
        if not self.verse_data:
            return
            
        selection = self.word_listbox.curselection()
        if not selection:
            return
            
        word_index = selection[0]
        word_text = self.word_listbox.get(word_index)
        self.current_word = word_text
        
        # Update word details
        if 'synonyms' in self.verse_data and word_text in self.verse_data['synonyms']:
            word_data = self.verse_data['synonyms'][word_text]
            
            # Clear and update word details
            self.word_details.delete(1.0, tk.END)
            
            details = f"Sanskrit: {word_text}\n"
            
            if 'meaning' in word_data:
                details += f"Meaning: {word_data['meaning']}\n"
                
            if 'versetext' in word_data:
                details += f"Verse text: {word_data['versetext']}\n"
                
            # Add timestamp info if available
            if 'timestamp' in word_data:
                start = word_data['timestamp'].get('start')
                end = word_data['timestamp'].get('end')
                
                if start is not None:
                    details += f"Start: {self.format_time(start)}\n"
                else:
                    details += "Start: Not marked\n"
                    
                if end is not None:
                    details += f"End: {self.format_time(end)}\n"
                else:
                    details += "End: Not marked\n"
            else:
                details += "No timestamps marked yet"
                
            self.word_details.insert(tk.END, details)
            
            # If word has timestamps, update selection
            if 'timestamp' in word_data:
                start = word_data['timestamp'].get('start')
                end = word_data['timestamp'].get('end')
                
                if start is not None and end is not None:
                    self.current_selection = [start, end]
                    self.plot_waveform()  # Redraw with selection
    
    # ====== Waveform display and interaction functions ======
    
    def plot_waveform(self):
        """Plot the audio waveform with current view settings"""
        if self.y is None or self.sr is None:
            return
            
        # Clear previous plot
        self.ax.clear()
        
        # Calculate visible range based on zoom level
        if self.view_window < self.audio_duration:
            visible_end = min(self.view_start + self.view_window, self.audio_duration)
            start_sample = int(self.view_start * self.sr)
            end_sample = int(visible_end * self.sr)
            
            # Plot visible portion of waveform
            time = np.arange(start_sample, end_sample) / self.sr
            self.ax.plot(time, self.y[start_sample:end_sample], linewidth=0.5)
            
            # Set axis limits
            self.ax.set_xlim(self.view_start, visible_end)
        else:
            # Plot entire waveform
            time = np.arange(0, len(self.y)) / self.sr
            self.ax.plot(time, self.y, linewidth=0.5)
            
            # Set axis limits
            self.ax.set_xlim(0, self.audio_duration)
            
        # Set y-axis limit to be symmetric around zero
        y_max = max(0.05, np.max(np.abs(self.y)) * 1.1)  # Add 10% margin and min value
        self.ax.set_ylim(-y_max, y_max)
        
        # Add labels and grid
        self.ax.set_xlabel('Time (s)')
        self.ax.set_ylabel('Amplitude')
        self.ax.grid(True, alpha=0.3)
        
        # Draw selection if exists
        if self.current_selection[0] is not None and self.current_selection[1] is not None:
            start, end = self.current_selection
            if start <= end:  # Valid selection
                selection_width = end - start
                rect = patches.Rectangle(
                    (start, -y_max), selection_width, 2 * y_max,
                    linewidth=0, facecolor='#4CAF50', alpha=0.2
                )
                self.ax.add_patch(rect)
                
                # Add vertical lines at selection boundaries
                self.ax.axvline(x=start, color='#4CAF50', linestyle='--', linewidth=1)
                self.ax.axvline(x=end, color='#4CAF50', linestyle='--', linewidth=1)
        
        # Draw tagged regions
        self.draw_tagged_regions()
        
        # Ensure playback line is on top
        if hasattr(self, 'playback_line'):
            self.playback_line = self.ax.axvline(
                x=self.current_position, color='r', linewidth=1.5, 
                visible=self.is_playing
            )
        
        # Update scrollbar position
        if self.audio_duration > 0:
            scrollbar_pos = (self.view_start / self.audio_duration) * 100
            self.waveform_scrollbar.set(scrollbar_pos)
        
        # Redraw the canvas
        self.canvas.draw()
    
    def on_waveform_click(self, event):
        """Handle mouse click on waveform"""
        if event.inaxes != self.ax or self.y is None:
            return
            
        # Get the time position from click
        click_time = event.xdata
        
        if click_time is not None and 0 <= click_time <= self.audio_duration:
            # If shift is held, update the selection end point
            if event.key == 'shift' and self.current_selection[0] is not None:
                self.current_selection[1] = click_time
                self.status_var.set(f"Selection: {self.format_time(self.current_selection[0])} - {self.format_time(click_time)}")
            else:
                # Otherwise start a new selection
                self.current_selection[0] = click_time
                self.current_selection[1] = click_time  # Initialize with same point
                self.status_var.set(f"Selection started at {self.format_time(click_time)}")
            
            # Update the plot
            self.plot_waveform()
    
    def on_waveform_release(self, event):
        """Handle mouse release on waveform"""
        if event.inaxes != self.ax or self.y is None:
            return
            
        # Get the time position from release
        release_time = event.xdata
        
        if release_time is not None and 0 <= release_time <= self.audio_duration:
            if self.current_selection[0] is not None:
                # Update selection end
                self.current_selection[1] = release_time
                
                # Ensure start <= end
                if self.current_selection[0] > self.current_selection[1]:
                    self.current_selection[0], self.current_selection[1] = self.current_selection[1], self.current_selection[0]
                
                start, end = self.current_selection
                self.status_var.set(f"Selection: {self.format_time(start)} - {self.format_time(end)} ({self.format_time(end-start)})")
                
                # Update the plot
                self.plot_waveform()
    
    def on_waveform_motion(self, event):
        """Handle mouse motion on waveform (for dragging selection)"""
        if event.inaxes != self.ax or self.y is None:
            return
            
        # Only update if mouse button is held down
        if not hasattr(event, 'button') or event.button != 1:
            return
            
        # Get the time position
        motion_time = event.xdata
        
        if motion_time is not None and 0 <= motion_time <= self.audio_duration:
            if self.current_selection[0] is not None:
                # Update selection end while dragging
                self.current_selection[1] = motion_time
                
                # Update status bar but don't redraw plot on every motion event for performance
                start, end = self.current_selection
                dur = abs(end - start)
                self.status_var.set(f"Dragging: {self.format_time(start)} - {self.format_time(end)} ({self.format_time(dur)})")
    
    def on_waveform_scroll(self, value):
        """Handle scrollbar movement for waveform view"""
        if self.y is None or self.sr is None:
            return
            
        # Calculate new view start based on scrollbar position
        value_float = float(value)
        self.view_start = (value_float / 100) * max(0, self.audio_duration - self.view_window)
        
        # Update waveform
        self.plot_waveform()
        self.draw_time_scale()
    
    def draw_time_scale(self):
        """Draw the time scale beneath the waveform"""
        if self.y is None or self.sr is None:
            return
            
        # Clear time scale
        self.time_scale.delete("all")
        
        # Get canvas width
        width = self.time_scale.winfo_width()
        if width <= 1:  # Not yet properly initialized
            self.root.after(100, self.draw_time_scale)
            return
            
        # Calculate visible time range
        visible_end = min(self.view_start + self.view_window, self.audio_duration)
        visible_duration = visible_end - self.view_start
        
        # Determine appropriate tick interval based on zoom level
        if visible_duration <= 2:  # Very zoomed in, use 0.1s ticks
            tick_interval = 0.1
        elif visible_duration <= 10:  # Zoomed in, use 0.5s ticks
            tick_interval = 0.5
        elif visible_duration <= 60:  # Normal view, use 1s ticks
            tick_interval = 1.0
        elif visible_duration <= 300:  # Zoomed out, use 5s ticks
            tick_interval = 5.0
        else:  # Very zoomed out, use 10s ticks
            tick_interval = 10.0
        
        # Calculate first tick position
        first_tick = math.ceil(self.view_start / tick_interval) * tick_interval
        
        # Draw ticks and labels
        height = self.time_scale.winfo_height()
        tick_height = height // 2
        
        # Draw ticks
        for t in np.arange(first_tick, visible_end, tick_interval):
            # Calculate x position
            x_pos = int(width * (t - self.view_start) / visible_duration)
            
            # Draw tick
            self.time_scale.create_line(x_pos, 0, x_pos, tick_height, fill="black")
            
            # Draw label
            time_str = self.format_time(t, show_ms=(tick_interval < 1.0))
            self.time_scale.create_text(x_pos, height - 5, text=time_str, font=("Arial", 7))
    
    def draw_tagged_regions(self):
        """Draw colored regions for tagged words on the waveform"""
        if self.y is None or not self.verse_data:
            return
            
        # Clear existing region references
        self.waveform_patches = []
        
        # Get y-axis limits for rectangle height
        y_lim = self.ax.get_ylim()
        y_min, y_max = y_lim
        
        # Assign different colors to each tag type
        colors = {
            'word': '#FFD700',  # Gold for words
            'line': '#87CEEB',  # Sky blue for lines
        }
        
        # Alternate colors for multiple segments of the same type
        alt_colors = [
            '#FF6347', '#98FB98', '#FFA500', 
            '#9370DB', '#FF69B4', '#20B2AA', '#F08080', '#7B68EE'
        ]
        
        # Store tagged regions for quick access
        self.tagged_regions = {}
        
        # Track color index for each type
        color_index = {'word': 0, 'line': 0}
        
        # Draw segments from the segments section first
        if 'segments' in self.verse_data:
            for i, segment in enumerate(self.verse_data['segments']):
                start = segment.get('start')
                end = segment.get('end')
                label = segment.get('label')
                segment_type = segment.get('type', 'word')  # Default to word if not specified
                
                if start is not None and end is not None and start != end and label:
                    # Store for quick lookup
                    self.tagged_regions[label] = (start, end)
                    
                    # Choose base color by type, then alternate if multiple of the same type
                    base_color = colors.get(segment_type, colors['word'])
                    if color_index[segment_type] > 0:
                        color = alt_colors[color_index[segment_type] % len(alt_colors)]
                    else:
                        color = base_color
                    
                    color_index[segment_type] += 1
                    
                    # Create rectangle for the region
                    rect = patches.Rectangle(
                        (start, y_min), end - start, y_max - y_min,
                        linewidth=0, facecolor=color, alpha=0.3
                    )
                    self.ax.add_patch(rect)
                    self.waveform_patches.append(rect)
                    
                    # Add tag/type indicator
                    text_x = start + (end - start) / 2
                    text_y = y_max * 0.9
                    self.ax.text(text_x, text_y, f"[{segment_type}]", 
                              ha='center', va='bottom', fontsize=6,
                              bbox=dict(facecolor='white', alpha=0.7, boxstyle='round,pad=0.1'))
                    
                    # Add label above the region
                    text_y = y_max * 0.8
                    self.ax.text(text_x, text_y, label, 
                              ha='center', va='bottom', fontsize=8,
                              bbox=dict(facecolor='white', alpha=0.7, boxstyle='round,pad=0.2'))
        
        # For backwards compatibility, also draw timestamps from synonyms
        # (these will eventually be migrated to segments)
        if 'synonyms' in self.verse_data:
            for word, data in self.verse_data['synonyms'].items():
                if 'timestamp' in data:
                    start = data['timestamp'].get('start')
                    end = data['timestamp'].get('end')
                    
                    if start is not None and end is not None and start != end:
                        # Convert to seconds if stored in milliseconds
                        if start > 1000:  # Assume milliseconds
                            start = start / 1000
                            end = end / 1000
                            
                        # Skip if this word is already in the segments section
                        if word in self.tagged_regions:
                            continue
                        
                        # Store for quick lookup
                        self.tagged_regions[word] = (start, end)
                        
                        # Choose color (legacy format is always "word" type)
                        color = colors['word']
                        if color_index['word'] > 0:
                            color = alt_colors[color_index['word'] % len(alt_colors)]
                        color_index['word'] += 1
                        
                        # Create rectangle for the region
                        rect = patches.Rectangle(
                            (start, y_min), end - start, y_max - y_min,
                            linewidth=0, facecolor=color, alpha=0.3
                        )
                        self.ax.add_patch(rect)
                        self.waveform_patches.append(rect)
                        
                        # Add legacy indicator
                        text_x = start + (end - start) / 2
                        text_y = y_max * 0.9
                        self.ax.text(text_x, text_y, "[legacy]", 
                                  ha='center', va='bottom', fontsize=6,
                                  bbox=dict(facecolor='white', alpha=0.7, boxstyle='round,pad=0.1'))
                        
                        # Add word label above the region
                        text_y = y_max * 0.8
                        self.ax.text(text_x, text_y, word, 
                                  ha='center', va='bottom', fontsize=8,
                                  bbox=dict(facecolor='white', alpha=0.7, boxstyle='round,pad=0.2'))
    
    def show_tagged_regions(self):
        """Highlight regions in waveform that have been tagged"""
        if self.y is not None:
            self.plot_waveform()  # Redraw with tagged regions
    
    def show_all_tags(self):
        """Show a dialog with all tagged words and their timestamps"""
        if not self.verse_data:
            messagebox.showinfo("No Tags", "No verse data loaded.")
            return
            
        # Count tagged items
        legacy_tagged_count = 0
        if 'synonyms' in self.verse_data:
            for word, data in self.verse_data['synonyms'].items():
                if 'timestamp' in data:
                    start = data['timestamp'].get('start')
                    end = data['timestamp'].get('end')
                    if start is not None and end is not None:
                        legacy_tagged_count += 1
        
        segment_count = 0
        if 'segments' in self.verse_data:
            segment_count = len(self.verse_data['segments'])
        
        total_tags = legacy_tagged_count + segment_count
        
        if total_tags == 0:
            messagebox.showinfo("No Tags", "No segments have been tagged with timestamps yet.")
            return
            
        # Create dialog with all tags
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Tagged Segments - Chapter {self.verse_data.get('chapter')}, Verse {self.verse_data.get('shloka')}")
        dialog.geometry("500x600")
        
        # Create frame with scrollbar
        frame = tk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Create text widget to display the tags
        text = tk.Text(frame, yscrollcommand=scrollbar.set, wrap=tk.WORD)
        text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=text.yview)
        
        # Add verse information
        text.insert(tk.END, f"Sanskrit: {self.verse_data.get('sanskrit', '')}\n\n")
        
        # Add segments section
        if segment_count > 0:
            text.insert(tk.END, f"Tagged Segments ({segment_count}):\n\n")
            
            # Display segments sorted by start time
            sorted_segments = sorted(self.verse_data['segments'], key=lambda x: x.get('start', 0))
            
            for i, segment in enumerate(sorted_segments):
                start = segment.get('start')
                end = segment.get('end')
                label = segment.get('label')
                segment_type = segment.get('type', 'word')
                
                if start is not None and end is not None and label:
                    # Format times
                    start_str = self.format_time(start)
                    end_str = self.format_time(end)
                    dur_str = self.format_time(end-start)
                    
                    text.insert(tk.END, f"{i+1}. \"{label}\" [{segment_type}]:\n")
                    text.insert(tk.END, f"   Start: {start_str}\n")
                    text.insert(tk.END, f"   End: {end_str}\n")
                    text.insert(tk.END, f"   Duration: {dur_str}\n\n")
        
        # Add legacy tagged words section (if any)
        if legacy_tagged_count > 0:
            text.insert(tk.END, f"\nLegacy Tagged Words ({legacy_tagged_count}):\n\n")
            
            for word, data in sorted(self.verse_data['synonyms'].items()):
                if 'timestamp' in data:
                    start = data['timestamp'].get('start')
                    end = data['timestamp'].get('end')
                    if start is not None and end is not None:
                        # Convert to seconds if stored in milliseconds
                        if start > 1000:
                            start_str = self.format_time(start/1000)
                            end_str = self.format_time(end/1000)
                            dur_str = self.format_time((end-start)/1000)
                        else:
                            start_str = self.format_time(start)
                            end_str = self.format_time(end)
                            dur_str = self.format_time(end-start)
                        
                        text.insert(tk.END, f"{word} [legacy]:\n")
                        text.insert(tk.END, f"   Start: {start_str}\n")
                        text.insert(tk.END, f"   End: {end_str}\n")
                        text.insert(tk.END, f"   Duration: {dur_str}\n")
                        if 'meaning' in data:
                            text.insert(tk.END, f"   Meaning: {data['meaning']}\n")
                        text.insert(tk.END, "\n")
            
            # Add note about migration
            text.insert(tk.END, "\nNote: Legacy tags will be shown for backward compatibility. "
                             "Consider using the new segment tagging system instead.\n")
        
        # Make text widget read-only
        text.config(state=tk.DISABLED)
    
    # ====== Playback control functions ======
    
    def toggle_play(self):
        """Play or pause the audio"""
        if not self.audio_file:
            self.status_var.set("No audio file loaded")
            return
            
        if self.is_playing:
            pygame.mixer.music.pause()
            self.is_playing = False
            self.play_btn.config(text="▶")
            self.status_var.set("Playback paused")
        else:
            # If at the end, go back to beginning
            if self.current_position >= self.audio_duration - 0.1:
                self.current_position = 0
                
            # Store start time for position calculation
            self._playback_start_time = self.current_position
                
            # Start playback
            pygame.mixer.music.play(start=self.current_position)
            self.is_playing = True
            self.play_btn.config(text="⏸")
            self.status_var.set("Playing audio")
            
            # Make playback line visible
            if hasattr(self, 'playback_line'):
                self.playback_line.set_visible(True)
                self.canvas.draw_idle()
    
    def stop_playback(self):
        """Stop audio playback and reset position"""
        if not self.audio_file:
            return
            
        pygame.mixer.music.stop()
        self.is_playing = False
        self.current_position = 0
        self.play_btn.config(text="▶")
        
        # Update position display
        self.position_var.set(self.format_time(0))
        
        # Update playback line
        if hasattr(self, 'playback_line'):
            self.playback_line.set_xdata([0])
            self.playback_line.set_visible(False)
            self.canvas.draw_idle()
            
        self.status_var.set("Playback stopped")
    
    def play_selection(self):
        """Play only the selected region"""
        if not self.audio_file:
            self.status_var.set("No audio file loaded")
            return
            
        if self.current_selection[0] is None or self.current_selection[1] is None:
            self.status_var.set("No region selected")
            return
            
        start, end = self.current_selection
        if start >= end:
            self.status_var.set("Invalid selection (start >= end)")
            return
            
        # Store start time for position calculation
        self._playback_start_time = start
        
        # Start playing from selection start
        pygame.mixer.music.play(start=start)
        self.current_position = start
        self.is_playing = True
        self.play_btn.config(text="⏸")
        
        # Make playback line visible
        if hasattr(self, 'playback_line'):
            self.playback_line.set_xdata([start])
            self.playback_line.set_visible(True)
            self.canvas.draw_idle()
            
        # Schedule stopping at selection end
        duration = end - start
        self.root.after(int(duration * 1000), self.stop_at_selection_end)
        
        self.status_var.set(f"Playing selection: {self.format_time(start)} - {self.format_time(end)}")
    
    def stop_at_selection_end(self):
        """Stop playback when selection end is reached"""
        if self.is_playing and self.current_selection[1] is not None:
            end = self.current_selection[1]
            if abs(self.current_position - end) < 0.1:  # Within 100ms of the end
                pygame.mixer.music.pause()
                self.is_playing = False
                self.play_btn.config(text="▶")
                self.current_position = end
                
                # Update playback line
                if hasattr(self, 'playback_line'):
                    self.playback_line.set_xdata([end])
                    self.canvas.draw_idle()
                    
                self.status_var.set("Playback of selection complete")
    
    def play_tagged_segment(self):
        """Play the audio segment for the selected word"""
        if not self.audio_file or not self.current_word or not self.verse_data:
            self.status_var.set("No audio file, word selection, or verse data")
            return
        
        if 'synonyms' not in self.verse_data or self.current_word not in self.verse_data['synonyms']:
            self.status_var.set(f"Word '{self.current_word}' not found in verse data")
            return
            
        word_data = self.verse_data['synonyms'][self.current_word]
        if 'timestamp' not in word_data:
            self.status_var.set(f"No timestamp data for '{self.current_word}'")
            return
            
        start = word_data['timestamp'].get('start')
        end = word_data['timestamp'].get('end')
        
        if start is None or end is None:
            self.status_var.set(f"Incomplete timestamp data for '{self.current_word}'")
            return
            
        # Convert to seconds if stored in milliseconds
        if start > 1000:
            start = start / 1000
            end = end / 1000
            
        # Update selection to match the word's timestamps
        self.current_selection = [start, end]
        self.plot_waveform()  # Update display
        
        # Play the segment
        self.play_selection()
    
    def jump_to_timestamp(self, mark_type):
        """Jump to the start or end timestamp of the selected word"""
        if not self.audio_file or not self.current_word or not self.verse_data:
            self.status_var.set("No audio file, word selection, or verse data")
            return
        
        if 'synonyms' not in self.verse_data or self.current_word not in self.verse_data['synonyms']:
            self.status_var.set(f"Word '{self.current_word}' not found in verse data")
            return
            
        word_data = self.verse_data['synonyms'][self.current_word]
        if 'timestamp' not in word_data:
            self.status_var.set(f"No timestamp data for '{self.current_word}'")
            return
            
        timestamp = word_data['timestamp'].get(mark_type)
        
        if timestamp is None:
            self.status_var.set(f"No {mark_type} timestamp for '{self.current_word}'")
            return
            
        # Convert to seconds if stored in milliseconds
        if timestamp > 1000:
            timestamp = timestamp / 1000
            
        # Set position and update display
        self.current_position = timestamp
        
        # Ensure the timestamp is visible in current view
        if timestamp < self.view_start or timestamp > self.view_start + self.view_window:
            self.view_start = max(0, min(timestamp - self.view_window * 0.1, self.audio_duration - self.view_window))
            self.plot_waveform()
            self.draw_time_scale()
        
        # Update playback line
        if hasattr(self, 'playback_line'):
            self.playback_line.set_xdata([self.current_position])
            self.canvas.draw_idle()
            
        self.status_var.set(f"Jumped to {mark_type} position for '{self.current_word}': {self.format_time(timestamp)}")
    
    # ====== Segment marking functions ======
    
    def mark_segment_start(self):
        """Mark the start of a segment at the current position"""
        if self.y is None:
            return
            
        # Set selection start to current position
        self.current_selection[0] = self.current_position
        
        # If end is not set or is before start, set it to the same position
        if self.current_selection[1] is None or self.current_selection[1] < self.current_selection[0]:
            self.current_selection[1] = self.current_position
        
        # Update display
        self.plot_waveform()
        
        self.status_var.set(f"Marked segment start at {self.format_time(self.current_position)}")
    
    def mark_segment_end(self):
        """Mark the end of a segment at the current position"""
        if self.y is None:
            return
            
        # Set selection end to current position
        self.current_selection[1] = self.current_position
        
        # If start is not set or is after end, set it to the same position
        if self.current_selection[0] is None or self.current_selection[0] > self.current_selection[1]:
            self.current_selection[0] = self.current_position
        
        # Update display
        self.plot_waveform()
        
        self.status_var.set(f"Marked segment end at {self.format_time(self.current_position)}")
    
    def clear_selection(self):
        """Clear the current selection"""
        if self.current_selection[0] is not None or self.current_selection[1] is not None:
            self.current_selection = [None, None]
            self.plot_waveform()
            self.status_var.set("Selection cleared")
    
    def tag_selected_region(self):
        """Tag the selected region with the current word"""
        if self.y is None or not self.verse_data or not self.current_word:
            self.status_var.set("Cannot tag: No audio, verse data, or word selected")
            return
            
        if self.current_selection[0] is None or self.current_selection[1] is None:
            self.status_var.set("No region selected")
            return
            
        start, end = self.current_selection
        if start >= end:
            self.status_var.set("Invalid selection (start >= end)")
            return
            
        # Ensure the word exists in verse data
        if 'synonyms' not in self.verse_data or self.current_word not in self.verse_data['synonyms']:
            self.status_var.set(f"Word '{self.current_word}' not found in verse data")
            return
        
        # Get segment type
        segment_type = self.segment_type_var.get()
            
        # Add to segments list
        segment = {
            "label": self.current_word,
            "start": start,
            "end": end,
            "type": segment_type,
            "word_ref": self.current_word  # Reference to the original word
        }
        
        # Initialize segments if not already present
        if 'segments' not in self.verse_data:
            self.verse_data['segments'] = []
            
        self.verse_data['segments'].append(segment)
        
        # Update display
        self.plot_waveform()
        
        self.status_var.set(
            f"Tagged '{self.current_word}' ({segment_type}) with {self.format_time(start)} - {self.format_time(end)} " +
            f"({self.format_time(end-start)})"
        )
    
    def tag_with_custom_label(self):
        """Tag the selected region with a custom label"""
        if self.y is None or not self.verse_data:
            self.status_var.set("Cannot tag: No audio or verse data loaded")
            return
            
        if self.current_selection[0] is None or self.current_selection[1] is None:
            self.status_var.set("No region selected")
            return
            
        start, end = self.current_selection
        if start >= end:
            self.status_var.set("Invalid selection (start >= end)")
            return
            
        # Get custom label
        custom_label = self.custom_label_var.get().strip()
        if not custom_label:
            self.status_var.set("Please enter a custom label")
            return
            
        # Get segment type
        segment_type = self.segment_type_var.get()
        
        # Add to segments list
        segment = {
            "label": custom_label,
            "start": start,
            "end": end,
            "type": segment_type
        }
        
        # Initialize segments if not already present
        if 'segments' not in self.verse_data:
            self.verse_data['segments'] = []
            
        self.verse_data['segments'].append(segment)
        
        # Update display
        self.plot_waveform()
        
        self.status_var.set(
            f"Tagged '{custom_label}' ({segment_type}) with {self.format_time(start)} - {self.format_time(end)} " +
            f"({self.format_time(end-start)})"
        )
        
        # Clear the custom label entry
        self.custom_label_var.set("")
    
    # ====== Update functions ======
    
    def update_playback_position(self):
        """Update the playback position during audio playback"""
        # Update if playing and mixer is active
        if self.is_playing and pygame.mixer.get_init() and pygame.mixer.music.get_busy():
            # Get position from pygame (returns ms)
            pos_ms = pygame.mixer.music.get_pos()
            
            if pos_ms > 0:  # Valid position
                # Add to starting position (pos_ms is time since playback started)
                current_time = self._playback_start_time + (pos_ms / 1000)
                
                # Update position
                self.current_position = current_time
                
                # Update position display
                self.position_var.set(self.format_time(current_time))
                
                # Move playback line if visible in current view
                if self.view_start <= current_time <= self.view_start + self.view_window:
                    if hasattr(self, 'playback_line'):
                        self.playback_line.set_xdata([current_time])
                        self.canvas.draw_idle()  # Only update the line, not the whole plot
                
                # Scroll view if playback position is outside visible area
                if current_time > self.view_start + self.view_window * 0.9:
                    self.view_start = min(
                        self.audio_duration - self.view_window,
                        current_time - self.view_window * 0.1
                    )
                    self.plot_waveform()
                    self.draw_time_scale()
        
        # Schedule next update (40ms for ~25 fps)
        self.root.after(40, self.update_playback_position)
    
    # ====== Utility functions ======
    
    def format_time(self, seconds, show_ms=True):
        """Format time in seconds to string display"""
        if seconds is None:
            return "00:00.000"
            
        minutes = int(seconds) // 60
        seconds_remainder = int(seconds) % 60
        milliseconds = int((seconds - int(seconds)) * 1000)
        
        if show_ms:
            return f"{minutes:02d}:{seconds_remainder:02d}.{milliseconds:03d}"
        else:
            return f"{minutes:02d}:{seconds_remainder:02d}"
    
    def save_tagged_data(self):
        """Save the updated verse data with tags to a JSON file"""
        if not self.verse_data or not self.all_verses:
            messagebox.showinfo("No Data", "No verse data to save.")
            return
            
        # Update the current verse in all_verses
        if 0 <= self.current_verse_index < len(self.all_verses):
            self.all_verses[self.current_verse_index] = self.verse_data
            
        # Ask for save location
        save_file = filedialog.asksaveasfilename(
            title="Save Tagged Gita Data",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")]
        )
        
        if not save_file:
            return
            
        try:
            # Migrate any legacy timestamps to segments format
            self.migrate_timestamps_to_segments()
            
            # Get the current verse data
            verse = self.verse_data
            
            # Create a simplified output with only the required fields
            output_data = {
                "chapter": verse.get("chapter", ""),
                "shloka": verse.get("shloka", ""),
                "filename": os.path.basename(self.audio_file) if self.audio_file else "",
                "segments": []
            }
            
            # Add segments with timing and tag info
            if 'segments' in verse:
                for segment in verse['segments']:
                    output_data['segments'].append({
                        "start": int(segment.get("start", 0) * 1000),  # Convert to milliseconds
                        "end": int(segment.get("end", 0) * 1000),
                        "label": segment.get("label", ""),
                        "tag": segment.get("type", "word")  # Rename 'type' to 'tag'
                    })
            
            # Save to file
            with open(save_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=4)
                
            self.status_var.set(f"Tagged data saved to {save_file}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Could not save file: {str(e)}")
            self.status_var.set(f"Error saving data: {str(e)}")
    
    def migrate_timestamps_to_segments(self):
        """Migrate legacy timestamp format to new segments format"""
        for verse_index, verse in enumerate(self.all_verses):
            if 'synonyms' in verse:
                # Initialize segments if not already present
                if 'segments' not in verse:
                    verse['segments'] = []
                    
                # Get existing segment labels to avoid duplicates
                existing_labels = set()
                for segment in verse['segments']:
                    if 'label' in segment:
                        existing_labels.add(segment['label'])
                
                # Migrate timestamps from synonyms to segments
                for word, data in verse['synonyms'].items():
                    if 'timestamp' in data and word not in existing_labels:
                        start = data['timestamp'].get('start')
                        end = data['timestamp'].get('end')
                        
                        if start is not None and end is not None:
                            # Convert to seconds if stored in milliseconds
                            if start > 1000:
                                start = start / 1000
                                end = end / 1000
                                
                            # Create segment entry
                            segment = {
                                "label": word,
                                "start": start,
                                "end": end,
                                "type": "word",
                                "word_ref": word  # Reference to the original word
                            }
                            
                            verse['segments'].append(segment)
                            
                            # Optionally, remove timestamp data from synonyms
                            # Commented out for backward compatibility
                            # del data['timestamp']
            
            # Update the verse in all_verses
            self.all_verses[verse_index] = verse
if __name__ == "__main__":
    root = tk.Tk()
    app = AudacityInspiredGitaTagger(root)
    app.save_tagged_data()
    app.save_tagged_data()