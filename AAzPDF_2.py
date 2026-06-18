import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import threading
import io
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4, A3, legal, landscape
from reportlab.lib.units import inch, mm
from PyPDF2 import PageObject
from PIL import Image, ImageTk, ImageOps, ImageEnhance
import fitz  # PyMuPDF

class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.scrollable_frame.bind("<MouseWheel>", self._on_mousewheel)
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

class PDFToolApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AAzPDF")
        self.root.geometry("1000x700")
        self.root.resizable(True, True)

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        self.notebook.bind("<Tab>", self.next_tab)
        self.notebook.bind("<Control-Tab>", self.next_tab)
        self.notebook.bind("<Shift-Tab>", self.previous_tab)
        self.notebook.bind("<Control-Shift-Tab>", self.previous_tab)

        # Tabs
        self.main_scrollable = ScrollableFrame(self.notebook)
        self.notebook.add(self.main_scrollable, text="PDF Tool")
        self.main_frame = self.main_scrollable.scrollable_frame

        self.layout_scrollable = ScrollableFrame(self.notebook)
        self.notebook.add(self.layout_scrollable, text="Layout & Compression")
        self.layout_frame = self.layout_scrollable.scrollable_frame

        self.reader_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.reader_frame, text="Reader.PDF")

        self.code_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.code_frame, text="Code Editor")
        # NEW: Add Update.Code tab (mode selectable)
        self.update_frame = ttk.Frame(self.notebook)  # NEW
        self.notebook.add(self.update_frame, text="Update.Code")  # NEW


        # Build tabs
        self.setup_main_tab()
        self.setup_layout_tab()
        self.setup_reader_tab()   # UPDATED
        self.setup_code_tab()
        self.setup_update_tab()  # NEW

    # ================= Reader.PDF (Full-screen + Mouse/Touchpad) =================
    def setup_reader_tab(self):
        """Setup enhanced PDF Reader with clean UI + gesture controls"""  # UPDATED
        main_container = ttk.Frame(self.reader_frame)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Minimal top: Open + Recent
        top_frame = ttk.Frame(main_container)
        top_frame.pack(fill=tk.X, pady=(0, 6))

        file_frame = ttk.Frame(top_frame)
        file_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(file_frame, text="Open PDF", command=self.reader_open_pdf).pack(side=tk.LEFT, padx=5)

        self.recent_files_var = tk.StringVar()
        self.recent_files_combo = ttk.Combobox(file_frame, textvariable=self.recent_files_var, width=36, state="readonly")
        self.recent_files_combo.pack(side=tk.LEFT, padx=5)
        self.recent_files_combo.bind('<<ComboboxSelected>>', self.reader_open_recent)
        self.recent_files = []

        # Main split: sidebar (hidden) + viewer
        self.content_paned = ttk.PanedWindow(main_container, orient=tk.HORIZONTAL)  # NEW
        self.content_paned.pack(fill=tk.BOTH, expand=True)

        # Sidebar (hidden by default)
        self.left_panel = ttk.Frame(self.content_paned)  # NEW

        view_group = ttk.LabelFrame(self.left_panel, text="View Options", padding=10)
        view_group.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(view_group, text="Rotate Page ↻", command=self.reader_rotate_page).pack(fill=tk.X, pady=2)
        row = ttk.Frame(view_group); row.pack(fill=tk.X, pady=2)
        ttk.Button(row, text="Fit Width",  command=lambda: self.reader_set_zoom('width')).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
        ttk.Button(row, text="Fit Height", command=lambda: self.reader_set_zoom('height')).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
        ttk.Button(row, text="Actual",     command=lambda: self.reader_set_zoom('actual')).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
        self.dark_mode_var = tk.BooleanVar()
        ttk.Checkbutton(view_group, text="Dark Mode", variable=self.dark_mode_var, command=self.reader_toggle_dark_mode).pack(anchor=tk.W, pady=2)

        annot_group = ttk.LabelFrame(self.left_panel, text="Annotations", padding=10)
        annot_group.pack(fill=tk.X, padx=5, pady=5)
        self.annot_mode = tk.StringVar(value="none")
        ttk.Radiobutton(annot_group, text="None",      variable=self.annot_mode, value="none").pack(anchor=tk.W)
        ttk.Radiobutton(annot_group, text="Rectangle", variable=self.annot_mode, value="rectangle").pack(anchor=tk.W)
        ttk.Radiobutton(annot_group, text="Highlight", variable=self.annot_mode, value="highlight").pack(anchor=tk.W)
        ab = ttk.Frame(annot_group); ab.pack(fill=tk.X, pady=5)
        ttk.Button(ab, text="Add Note", command=self.reader_add_note).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
        ttk.Button(ab, text="Clear All", command=self.reader_clear_annotations).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)

        manage_group = ttk.LabelFrame(self.left_panel, text="Page Management", padding=10)
        manage_group.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(manage_group, text="Extract Current Page", command=self.reader_extract_page).pack(fill=tk.X, pady=2)
        ttk.Button(manage_group, text="Split from Current",   command=self.reader_split_from_current).pack(fill=tk.X, pady=2)
        bm = ttk.Frame(manage_group); bm.pack(fill=tk.X, pady=(6,0))
        ttk.Button(bm, text="Bookmark", command=self.reader_bookmark_page).pack(side=tk.LEFT)
        self.bookmark_var = tk.StringVar()
        self.bookmark_combo = ttk.Combobox(bm, textvariable=self.bookmark_var, state="readonly", width=22)
        self.bookmark_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.bookmark_combo.bind('<<ComboboxSelected>>', self.reader_goto_bookmark)
        self.bookmarks = []

        # Viewer area (thumbs drawer + canvas)
        right_panel = ttk.Frame(self.content_paned)
        self.content_paned.add(right_panel, weight=1)  # only viewer visible initially

        self.viewer_split = ttk.PanedWindow(right_panel, orient=tk.HORIZONTAL)
        self.viewer_split.pack(fill=tk.BOTH, expand=True)

        # Thumbnails drawer (hidden until toggled)
        self.thumbs_panel = ttk.Frame(self.viewer_split, width=140)
        tp_hdr = ttk.Label(self.thumbs_panel, text="Pages", anchor='w'); tp_hdr.pack(fill=tk.X, padx=6, pady=(6, 2))
        self.thumb_canvas = tk.Canvas(self.thumbs_panel, highlightthickness=0, bg="#fafafa", width=130)
        self.thumb_scroll = ttk.Scrollbar(self.thumbs_panel, orient="vertical", command=self.thumb_canvas.yview)
        self.thumb_inner = ttk.Frame(self.thumb_canvas)
        self.thumb_inner.bind("<Configure>", lambda e: self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all")))
        self.thumb_canvas.create_window((0, 0), window=self.thumb_inner, anchor="nw")
        self.thumb_canvas.configure(yscrollcommand=self.thumb_scroll.set)
        self.thumb_canvas.pack(side="left", fill="both", expand=True)
        self.thumb_scroll.pack(side="right", fill="y")

        # Viewer container
        viewer_container = ttk.Frame(self.viewer_split)
        self.viewer_split.add(viewer_container, weight=1)

        self.reader_canvas = tk.Canvas(viewer_container, bg='white', cursor="crosshair", highlightthickness=0)
        self.reader_canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.reader_canvas.bind("<Configure>", self.reader_on_canvas_configure)

        bottom_frame = ttk.Frame(viewer_container)
        bottom_frame.pack(fill=tk.X, pady=4)
        self.page_indicator = ttk.Label(bottom_frame, text="No document loaded")
        self.page_indicator.pack(side=tk.LEFT, padx=8)
        zoom_frame = ttk.Frame(bottom_frame); zoom_frame.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=10)
        ttk.Button(zoom_frame, text="-", width=2, command=self.reader_zoom_out).pack(side=tk.LEFT)
        self.zoom_scale = ttk.Scale(zoom_frame, from_=25, to=400, orient=tk.HORIZONTAL, command=self.reader_zoom_scale_changed)
        self.zoom_scale.set(100); self.zoom_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.zoom_label = ttk.Label(zoom_frame, text="100%", width=5); self.zoom_label.pack(side=tk.LEFT, padx=4)

        # Floating tiny toolbar (auto-hide)
        self.fab = tk.Frame(viewer_container, bg="#ffffff", bd=0, highlightthickness=0)
        self.fab.place(relx=1.0, rely=1.0, x=-14, y=-14, anchor="se")
        fi = ttk.Frame(self.fab); fi.pack()

        ttk.Button(fi, text="◀", width=2, command=self.reader_prev_page).grid(row=0, column=0, padx=1)
        ttk.Button(fi, text="▶", width=2, command=self.reader_next_page).grid(row=0, column=1, padx=1)
        ttk.Button(fi, text="+",  width=2, command=self.reader_zoom_in).grid(row=0, column=2, padx=1)
        ttk.Button(fi, text="−",  width=2, command=self.reader_zoom_out).grid(row=0, column=3, padx=1)
        ttk.Button(fi, text="⟳",  width=2, command=self.reader_rotate_page).grid(row=0, column=4, padx=1)
        ttk.Button(fi, text="🌙", width=2, command=lambda: self.dark_mode_var.set(not self.dark_mode_var.get()) or self.reader_toggle_dark_mode()).grid(row=0, column=5, padx=1)
        ttk.Button(fi, text="📑", width=2, command=self.reader_toggle_thumbs).grid(row=0, column=6, padx=1)
        ttk.Button(fi, text="🔎", width=2, command=self.reader_open_find_popup).grid(row=0, column=7, padx=1)
        ttk.Button(fi, text="🔢", width=2, command=self.reader_open_goto_popup).grid(row=0, column=8, padx=1)
        ttk.Button(fi, text="☰",  width=2, command=self.reader_toggle_sidebar).grid(row=0, column=9, padx=1)

        # Auto-hide toolbar on inactivity
        self._fab_after = None
        self.reader_canvas.bind("<Motion>", self.reader_on_mouse_move)
        self.fab_visible = True

        # === Gesture bindings ===  # NEW
        self.reader_canvas.bind("<Button-1>", self._on_left_down)           # start pan or annotation
        self.reader_canvas.bind("<B1-Motion>", self._on_left_drag)          # pan/annot drag
        self.reader_canvas.bind("<ButtonRelease-1>", self._on_left_up)      # end
        self.reader_canvas.bind("<Double-Button-1>", self._on_double_left)  # fit width reset
        self.reader_canvas.bind("<Button-3>", lambda e: self.reader_rotate_page())  # right-click rotate

        # Mouse wheel: Option 2 -> scroll for page nav, Ctrl+scroll for zoom
        self.reader_canvas.bind("<MouseWheel>", self._on_wheel_windows)     # Windows / Mac (delta multiple of 120)
        # X11 (Linux) wheel events:
        self.reader_canvas.bind("<Button-4>", lambda e: self._on_wheel_generic(e, 120))
        self.reader_canvas.bind("<Button-5>", lambda e: self._on_wheel_generic(e, -120))

        # State
        self.reader_doc = None
        self.current_page = 0
        self.total_pages = 0
        self.zoom_level = 1.0
        self.page_rotation = 0
        self.dark_mode = False
        self.current_image = None
        self.annotations = {}
        self.notes = {}
        self.temp_annotation = None
        self.drag_start = None
        self.search_var = tk.StringVar()
        self.search_hits = {}
        self.search_index = -1
        self.thumb_images = []

        # Panning offsets (in pixels on current canvas scale)  # NEW
        self.pan_x = 0
        self.pan_y = 0
        self._pan_anchor = None  # for dragging

        # Hidden by default
        self.sidebar_visible = False
        self.thumbs_visible = False

        # Shortcuts
        self.root.bind('<Left>', lambda e: self.reader_prev_page())
        self.root.bind('<Right>', lambda e: self.reader_next_page())
        self.root.bind('<Control-g>', lambda e: self.reader_open_goto_popup())
        self.root.bind('<Control-o>', lambda e: self.reader_open_pdf())
        self.root.bind('<Control-plus>', lambda e: self.reader_zoom_in())
        self.root.bind('<Control-minus>', lambda e: self.reader_zoom_out())
        self.root.bind('<Control-f>', lambda e: self.reader_open_find_popup())

    # ---- Sidebar / Thumbs toggles ----
    def reader_toggle_sidebar(self):
        if self.sidebar_visible:
            try:
                self.content_paned.forget(self.left_panel)
            except Exception:
                pass
            self.sidebar_visible = False
        else:
            try:
                self.content_paned.insert(0, self.left_panel, weight=0)
            except Exception:
                self.content_paned.add(self.left_panel, weight=0)
            self.sidebar_visible = True

    def reader_toggle_thumbs(self):
        if self.thumbs_visible:
            try:
                self.viewer_split.forget(self.thumbs_panel)
            except Exception:
                pass
            self.thumbs_visible = False
        else:
            try:
                self.viewer_split.insert(0, self.thumbs_panel, weight=0)
            except Exception:
                self.viewer_split.add(self.thumbs_panel, weight=0)
            self.thumbs_visible = True

    # ---- Auto-hide floating toolbar ----
    def reader_on_mouse_move(self, event=None):
        self.show_fab()
        self.schedule_hide_fab()

    def show_fab(self):
        if not self.fab_visible:
            self.fab.place(relx=1.0, rely=1.0, x=-14, y=-14, anchor="se")
            self.fab_visible = True

    def hide_fab(self):
        if self.fab_visible:
            self.fab.place_forget()
            self.fab_visible = False

    def schedule_hide_fab(self):
        if self._fab_after:
            self.root.after_cancel(self._fab_after)
        self._fab_after = self.root.after(2500, self.hide_fab)

    # ---- Resize helper ----
    def reader_on_canvas_configure(self, event):
        if self.reader_doc:
            self.reader_render_page()

    # ---- Thumbnails ----
    def reader_build_thumbnails(self):
        for w in getattr(self, 'thumb_inner', []).winfo_children():
            w.destroy()
        self.thumb_images.clear()
        if not self.reader_doc:
            return
        for i in range(self.total_pages):
            try:
                page = self.reader_doc[i]
                pix = page.get_pixmap(matrix=fitz.Matrix(0.25, 0.25))
                img = Image.open(io.BytesIO(pix.tobytes("ppm")))
                ph = ImageTk.PhotoImage(img)
                self.thumb_images.append(ph)
                f = ttk.Frame(self.thumb_inner); f.pack(fill="x", padx=6, pady=4)
                lbl = ttk.Label(f, image=ph); lbl.pack()
                cap = ttk.Label(f, text=f"{i+1}", anchor='center'); cap.pack(fill="x")
                lbl.bind("<Button-1>", lambda e, idx=i: self.reader_thumb_goto(idx))
                cap.bind("<Button-1>", lambda e, idx=i: self.reader_thumb_goto(idx))
            except Exception:
                pass

    def reader_thumb_goto(self, index):
        if 0 <= index < self.total_pages:
            self.current_page = index
            self.pan_x = self.pan_y = 0  # reset pan when jumping pages
            self.reader_render_page()

    # ---- File + recent ----
    def reader_open_pdf(self):
        filename = filedialog.askopenfilename(title="Open PDF", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
        if filename:
            self.reader_load_pdf(filename)

    def reader_open_recent(self, event=None):
        filename = self.recent_files_var.get()
        if filename and os.path.exists(filename):
            self.reader_load_pdf(filename)

    def reader_add_recent(self, filename):
        if not hasattr(self, 'recent_files'):
            self.recent_files = []
        if filename in self.recent_files:
            self.recent_files.remove(filename)
        self.recent_files.insert(0, filename)
        self.recent_files = self.recent_files[:5]
        self.recent_files_combo['values'] = self.recent_files
        if self.recent_files:
            self.recent_files_var.set(self.recent_files[0])

    def reader_load_pdf(self, filename):
        """Load PDF document"""
        try:
            if self.reader_doc:
                self.reader_doc.close()
            self.reader_doc = fitz.open(filename)
            self.current_page = 0
            self.total_pages = len(self.reader_doc)
            self.page_rotation = 0
            self.annotations = {}
            self.notes = {}
            self.bookmarks = []
            self.search_hits = {}
            self.search_index = -1
            self.pan_x = self.pan_y = 0
            self.update_bookmark_combo()
            self.reader_add_recent(filename)
            self.reader_build_thumbnails()
            self.reader_render_page()
        except Exception as e:
            messagebox.showerror("Error", f"Could not open PDF: {str(e)}")

    # ---- Rendering & overlays ----
    def reader_render_page(self):
        if not self.reader_doc or self.current_page >= self.total_pages:
            return
        try:
            page = self.reader_doc[self.current_page]
            mat = fitz.Matrix(self.zoom_level, self.zoom_level).prerotate(self.page_rotation)
            pix = page.get_pixmap(matrix=mat)
            img = Image.open(io.BytesIO(pix.tobytes("ppm")))
            if self.dark_mode:
                img = ImageOps.invert(img.convert('RGB'))
                img = ImageEnhance.Brightness(img).enhance(0.7)
            self.current_image = ImageTk.PhotoImage(img)

            self.reader_canvas.delete("all")
            c_w = max(1, self.reader_canvas.winfo_width())
            c_h = max(1, self.reader_canvas.winfo_height())
            # Base centered origin
            base_x = max(0, (c_w - self.current_image.width()) // 2)
            base_y = max(0, (c_h - self.current_image.height()) // 2)
            # Apply current pan offsets
            x = base_x + int(self.pan_x)
            y = base_y + int(self.pan_y)

            self.reader_canvas.create_image(x, y, anchor=tk.NW, image=self.current_image, tags="pdf_image")

            self.reader_draw_annotations(base_x, base_y)
            self.reader_draw_search_hits(base_x, base_y)
            self.page_indicator.config(text=f"Page {self.current_page + 1} of {self.total_pages}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not render page: {str(e)}")

    # ---- Annotations ----
    def reader_draw_annotations(self, base_x=0, base_y=0):
        if self.current_page in self.annotations:
            for annot in self.annotations[self.current_page]:
                color = "red" if annot['type'] == 'rectangle' else 'yellow'
                x1 = annot['x1'] * self.zoom_level + base_x + self.pan_x
                y1 = annot['y1'] * self.zoom_level + base_y + self.pan_y
                x2 = annot['x2'] * self.zoom_level + base_x + self.pan_x
                y2 = annot['y2'] * self.zoom_level + base_y + self.pan_y
                if annot['type'] == 'rectangle':
                    self.reader_canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2, tags="annotation")
                else:
                    self.reader_canvas.create_rectangle(x1, y1, x2, y2, fill=color, stipple="gray50", tags="annotation")

    def reader_on_click(self, event):
        # kept for compatibility (not used when panning); annotations use new handlers below
        self._on_left_down(event)

    def reader_on_drag(self, event):
        self._on_left_drag(event)

    def reader_on_release(self, event):
        self._on_left_up(event)

    def _on_left_down(self, event):
        """Start pan if no annotation mode; else start annotation."""
        if self.annot_mode.get() == "none":
            self._pan_anchor = (event.x, event.y)
            self.canvas_at_start = (self.pan_x, self.pan_y)
        else:
            # start annotation capture
            c_w = max(1, self.reader_canvas.winfo_width())
            c_h = max(1, self.reader_canvas.winfo_height())
            iw = self.current_image.width() if self.current_image else 0
            ih = self.current_image.height() if self.current_image else 0
            base_x = max(0, (c_w - iw) // 2)
            base_y = max(0, (c_h - ih) // 2)
            x_img = max(0, event.x - (base_x + self.pan_x))
            y_img = max(0, event.y - (base_y + self.pan_y))
            self.drag_start = (x_img, y_img)
            self.temp_annotation = {
                'type': self.annot_mode.get(),
                'x1': x_img / self.zoom_level,
                'y1': y_img / self.zoom_level,
                'x2': x_img / self.zoom_level,
                'y2': y_img / self.zoom_level
            }

    def _on_left_drag(self, event):
        """Pan or draw temp annotation depending on mode."""
        if self.annot_mode.get() == "none":
            if self._pan_anchor:
                dx = event.x - self._pan_anchor[0]
                dy = event.y - self._pan_anchor[1]
                self.pan_x = self.canvas_at_start[0] + dx
                self.pan_y = self.canvas_at_start[1] + dy
                self.reader_render_page()
        else:
            if self.drag_start and self.temp_annotation:
                c_w = max(1, self.reader_canvas.winfo_width())
                c_h = max(1, self.reader_canvas.winfo_height())
                iw = self.current_image.width() if self.current_image else 0
                ih = self.current_image.height() if self.current_image else 0
                base_x = max(0, (c_w - iw) // 2)
                base_y = max(0, (c_h - ih) // 2)
                x_img = max(0, event.x - (base_x + self.pan_x))
                y_img = max(0, event.y - (base_y + self.pan_y))
                self.temp_annotation['x2'] = x_img / self.zoom_level
                self.temp_annotation['y2'] = y_img / self.zoom_level
                self.reader_draw_temp_annotation(base_x, base_y)

    def _on_left_up(self, event):
        if self.annot_mode.get() == "none":
            self._pan_anchor = None
        else:
            if self.drag_start and self.temp_annotation:
                if self.current_page not in self.annotations:
                    self.annotations[self.current_page] = []
                self.annotations[self.current_page].append(self.temp_annotation.copy())
                self.drag_start = None
                self.temp_annotation = None

    def _on_double_left(self, event):
        """Double-click to Fit Width and reset pan offsets."""
        self.reader_set_zoom('width')
        self.pan_x = 0
        self.pan_y = 0
        self.reader_render_page()

    def reader_draw_temp_annotation(self, base_x=0, base_y=0):
        if not self.temp_annotation:
            return
        self.reader_canvas.delete("temp_annotation")
        color = "red" if self.temp_annotation['type'] == 'rectangle' else 'yellow'
        x1 = self.temp_annotation['x1'] * self.zoom_level + base_x + self.pan_x
        y1 = self.temp_annotation['y1'] * self.zoom_level + base_y + self.pan_y
        x2 = self.temp_annotation['x2'] * self.zoom_level + base_x + self.pan_x
        y2 = self.temp_annotation['y2'] * self.zoom_level + base_y + self.pan_y
        if self.temp_annotation['type'] == 'rectangle':
            self.reader_canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2, tags="temp_annotation")
        else:
            self.reader_canvas.create_rectangle(x1, y1, x2, y2, fill=color, stipple="gray50", tags="temp_annotation")

    def reader_clear_annotations(self):
        if self.current_page in self.annotations:
            del self.annotations[self.current_page]
        self.reader_render_page()

    def reader_add_note(self):
        if not self.reader_doc:
            return
        note = tk.simpledialog.askstring("Add Note", "Enter your note:")
        if note:
            if self.current_page not in self.notes:
                self.notes[self.current_page] = []
            self.notes[self.current_page].append(note)
            messagebox.showinfo("Note Added", f"Note added to page {self.current_page + 1}")

    # ---- Wheel handling (Option 2) ----
    def _wheel_common(self, delta, event):
        """If Ctrl pressed -> zoom under cursor. Else -> page navigation."""
        ctrl = (event.state & 0x0004) != 0  # Control mask on Windows/X11
        if ctrl:
            # zoom
            factor = 1.1 if delta > 0 else 1/1.1
            if not self.reader_doc or self.current_image is None:
                return
            old_zoom = self.zoom_level
            new_zoom = min(4.0, max(0.25, old_zoom * factor))

            # keep point under cursor stable
            c_w = max(1, self.reader_canvas.winfo_width())
            c_h = max(1, self.reader_canvas.winfo_height())
            iw = self.current_image.width()
            ih = self.current_image.height()
            base_x = max(0, (c_w - iw) // 2)
            base_y = max(0, (c_h - ih) // 2)
            # document coords at zoom 1 (approx)
            doc_x = (event.x - (base_x + self.pan_x)) / old_zoom
            doc_y = (event.y - (base_y + self.pan_y)) / old_zoom
            # predict new image size (approx)
            iw2 = int(iw * (new_zoom / old_zoom))
            ih2 = int(ih * (new_zoom / old_zoom))
            base_x2 = max(0, (c_w - iw2) // 2)
            base_y2 = max(0, (c_h - ih2) // 2)
            self.zoom_level = new_zoom
            self.zoom_scale.set(self.zoom_level * 100)
            # adjust pan so that cursor stays on same doc point
            self.pan_x = (event.x - doc_x * new_zoom) - base_x2
            self.pan_y = (event.y - doc_y * new_zoom) - base_y2
            self.reader_render_page()
        else:
            # page navigation
            if not self.reader_doc:
                return
            if delta > 0:
                self.reader_prev_page()
            else:
                self.reader_next_page()

    def _on_wheel_windows(self, event):
        self._wheel_common(event.delta, event)

    def _on_wheel_generic(self, event, delta):
        self._wheel_common(delta, event)

    # ---- Navigation & zoom (buttons/shortcuts) ----
    def reader_first_page(self):
        if self.reader_doc and self.total_pages > 0:
            self.current_page = 0; self.pan_x = self.pan_y = 0; self.reader_render_page()

    def reader_last_page(self):
        if self.reader_doc and self.total_pages > 0:
            self.current_page = self.total_pages - 1; self.pan_x = self.pan_y = 0; self.reader_render_page()

    def reader_prev_page(self):
        if self.reader_doc and self.current_page > 0:
            self.current_page -= 1; self.pan_x = self.pan_y = 0; self.reader_render_page()

    def reader_next_page(self):
        if self.reader_doc and self.current_page < self.total_pages - 1:
            self.current_page += 1; self.pan_x = self.pan_y = 0; self.reader_render_page()

    def reader_open_goto_popup(self):
        if not self.reader_doc:
            return
        w = tk.Toplevel(self.root); w.title("Go to page"); w.resizable(False, False)
        ttk.Label(w, text=f"Page (1–{self.total_pages}):").grid(row=0, column=0, padx=6, pady=6)
        self.goto_entry = ttk.Entry(w, width=6); self.goto_entry.grid(row=0, column=1, padx=4, pady=6); self.goto_entry.focus_set()
        ttk.Button(w, text="Go", command=self.reader_goto_page).grid(row=0, column=2, padx=4, pady=6)

    def reader_goto_page(self):
        if not self.reader_doc:
            return
        try:
            page_num = int(self.goto_entry.get()) - 1
            if 0 <= page_num < self.total_pages:
                self.current_page = page_num; self.pan_x = self.pan_y = 0; self.reader_render_page()
            else:
                messagebox.showerror("Error", f"Page number must be between 1 and {self.total_pages}")
        except Exception:
            messagebox.showerror("Error", "Please enter a valid page number")

    def reader_zoom_in(self):
        self.zoom_level = min(4.0, self.zoom_level * 1.2)
        self.zoom_scale.set(self.zoom_level * 100)
        self.reader_render_page()

    def reader_zoom_out(self):
        self.zoom_level = max(0.25, self.zoom_level / 1.2)
        self.zoom_scale.set(self.zoom_level * 100)
        self.reader_render_page()

    def reader_zoom_scale_changed(self, value):
        try:
            self.zoom_level = float(value) / 100.0
            self.zoom_label.config(text=f"{int(self.zoom_level * 100)}%")
            self.reader_render_page()
        except ValueError:
            pass

    def reader_set_zoom(self, mode):
        if not self.reader_doc:
            return
        if mode == 'width':
            canvas_w = max(1, self.reader_canvas.winfo_width())
            page_w = self.reader_doc[self.current_page].rect.width
            self.zoom_level = min(4.0, max(0.25, canvas_w / page_w))
        elif mode == 'height':
            canvas_h = max(1, self.reader_canvas.winfo_height())
            page_h = self.reader_doc[self.current_page].rect.height
            self.zoom_level = min(4.0, max(0.25, canvas_h / page_h))
        elif mode == 'actual':
            self.zoom_level = 1.0
        self.zoom_scale.set(self.zoom_level * 100)
        self.reader_render_page()

    def reader_rotate_page(self):
        self.page_rotation = (self.page_rotation + 90) % 360
        self.reader_render_page()

    def reader_toggle_dark_mode(self):
        self.dark_mode = self.dark_mode_var.get()
        self.reader_render_page()

    # ---- Search (popups) ----
    def reader_open_find_popup(self):
        if getattr(self, "_find_win", None) and tk.Toplevel.winfo_exists(self._find_win):
            self._find_win.lift(); return
        w = tk.Toplevel(self.root); w.title("Find"); w.resizable(False, False)
        ttk.Label(w, text="Find:").grid(row=0, column=0, padx=6, pady=6)
        e = ttk.Entry(w, textvariable=self.search_var, width=28); e.grid(row=0, column=1, padx=4, pady=6); e.focus_set()
        ttk.Button(w, text="Find", command=self.reader_search_start).grid(row=0, column=2, padx=2, pady=6)
        ttk.Button(w, text="◀", width=3, command=lambda: self.reader_search_step(-1)).grid(row=0, column=3, padx=1)
        ttk.Button(w, text="▶", width=3, command=lambda: self.reader_search_step(1)).grid(row=0, column=4, padx=1)
        self._find_win = w

    def reader_search_start(self):
        query = (self.search_var.get() or "").strip()
        if not self.reader_doc or not query:
            return
        self.search_hits = {}; self.search_index = -1
        for pno in range(self.total_pages):
            try:
                rects = list(self.reader_doc[pno].search_for(query, hit_max=500))
                if rects: self.search_hits[pno] = rects
            except Exception:
                continue
        pages = sorted(self.search_hits.keys())
        if pages:
            self.current_page = pages[0]; self.search_index = 0
        self.reader_render_page()

    def reader_search_step(self, step):
        if not self.search_hits: return
        flat = []
        for p in range(self.total_pages):
            if p in self.search_hits:
                flat.extend((p, i) for i in range(len(self.search_hits[p])))
        if not flat: return
        self.search_index = (0 if self.search_index < 0 else (self.search_index + step)) % len(flat)
        p, _ = flat[self.search_index]
        if p != self.current_page:
            self.current_page = p
        self.reader_render_page()

    def reader_draw_search_hits(self, base_x=0, base_y=0):
        if self.current_page not in self.search_hits:
            return
        for r in self.search_hits[self.current_page]:
            x1, y1, x2, y2 = r.x0*self.zoom_level, r.y0*self.zoom_level, r.x1*self.zoom_level, r.y1*self.zoom_level
            self.reader_canvas.create_rectangle(
                base_x + self.pan_x + x1, base_y + self.pan_y + y1,
                base_x + self.pan_x + x2, base_y + self.pan_y + y2,
                fill="yellow", stipple="gray50", outline="", tags="search_hit"
            )

    # ---- PDF ops ----
    def reader_extract_page(self):
        if not self.reader_doc:
            return
        filename = filedialog.asksaveasfilename(title="Save Current Page As", defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if filename:
            try:
                new_doc = fitz.open()
                new_doc.insert_pdf(self.reader_doc, from_page=self.current_page, to_page=self.current_page)
                new_doc.save(filename); new_doc.close()
                messagebox.showinfo("Success", f"Page saved as {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not save page: {str(e)}")

    def reader_split_from_current(self):
        if not self.reader_doc:
            return
        filename = filedialog.asksaveasfilename(title="Save Split PDF As", defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if filename:
            try:
                new_doc = fitz.open()
                new_doc.insert_pdf(self.reader_doc, from_page=self.current_page)
                new_doc.save(filename); new_doc.close()
                messagebox.showinfo("Success", f"PDF split and saved as {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not split PDF: {str(e)}")

    def reader_bookmark_page(self):
        if not self.reader_doc:
            return
        bookmark_name = tk.simpledialog.askstring("Bookmark Page", f"Enter bookmark name for page {self.current_page + 1}:")
        if bookmark_name:
            self.bookmarks.append({'name': bookmark_name, 'page': self.current_page, 'page_display': self.current_page + 1})
            self.update_bookmark_combo()
            messagebox.showinfo("Bookmark Added", f"Bookmark '{bookmark_name}' added for page {self.current_page + 1}")

    def reader_goto_bookmark(self, event=None):
        selected = self.bookmark_var.get()
        if selected:
            name_only = selected.split(" (Page")[0]
            for bm in self.bookmarks:
                if bm['name'] == name_only:
                    self.current_page = bm['page']
                    self.pan_x = self.pan_y = 0
                    self.reader_render_page()
                    break

    def update_bookmark_combo(self):
        values = [bm['name'] + f" (Page {bm['page_display']})" for bm in self.bookmarks]
        self.bookmark_combo['values'] = values
        if values:
            self.bookmark_var.set(values[0])

    # ================= PDF Tool tab =================
    def next_tab(self, event=None):
        current = self.notebook.index(self.notebook.select())
        next_tab = (current + 1) % self.notebook.index("end")
        self.notebook.select(next_tab)
        return "break"

    def previous_tab(self, event=None):
        current = self.notebook.index(self.notebook.select())
        prev_tab = (current - 1) % self.notebook.index("end")
        self.notebook.select(prev_tab)
        return "break"

    def setup_main_tab(self):
        title_label = ttk.Label(self.main_frame, text="AAzPDF", font=('Bodoni', 16, 'bold'))
        title_label.pack(pady=10)

        source_frame = ttk.Frame(self.main_frame)
        source_frame.pack(fill='x', padx=20, pady=10)
        ttk.Label(source_frame, text="Source File Path:").pack(anchor='w')
        source_subframe = ttk.Frame(source_frame); source_subframe.pack(fill='x', pady=5)
        self.source_path = tk.StringVar()
        self.source_entry = ttk.Entry(source_subframe, textvariable=self.source_path, width=50)
        self.source_entry.pack(side='left', fill='x', expand=True)
        ttk.Button(source_subframe, text="Browse", command=self.browse_source).pack(side='left', padx=5)
        ttk.Button(source_subframe, text="Add Multiple Files", command=self.browse_multiple_files).pack(side='left', padx=5)

        name_frame = ttk.Frame(self.main_frame); name_frame.pack(fill='x', padx=20, pady=10)
        ttk.Label(name_frame, text="Output PDF Name:").pack(anchor='w')
        self.pdf_name = tk.StringVar(value="output.pdf")
        ttk.Entry(name_frame, textvariable=self.pdf_name, width=50).pack(fill='x', pady=5)

        task_frame = ttk.Frame(self.main_frame); task_frame.pack(fill='x', padx=20, pady=10)
        ttk.Label(task_frame, text="Select Task:").pack(anchor='w')
        self.task_var = tk.StringVar(value="merge")
        task_subframe = ttk.Frame(task_frame); task_subframe.pack(fill='x', pady=5)
        ttk.Radiobutton(task_subframe, text="Merge PDFs", variable=self.task_var, value="merge").pack(side='left', padx=10)
        ttk.Radiobutton(task_subframe, text="Split PDF",  variable=self.task_var, value="split").pack(side='left', padx=10)

        self.split_frame = ttk.Frame(self.main_frame)
        self.split_instruction = ttk.Label(self.split_frame, text="💡 For splitting: Choose one of the options below", foreground="blue", font=('Arial', 9))
        self.split_instruction.pack(anchor='w', pady=(0, 10))
        method_frame = ttk.Frame(self.split_frame); method_frame.pack(fill='x', pady=5)
        self.split_method = tk.StringVar(value="pages_per_file")
        ttk.Radiobutton(method_frame, text="Pages per file",           variable=self.split_method, value="pages_per_file", command=self.on_split_method_change).pack(side='left', padx=10)
        ttk.Radiobutton(method_frame, text="Split at specific pages",  variable=self.split_method, value="split_at_pages",  command=self.on_split_method_change).pack(side='left', padx=10)
        ttk.Radiobutton(method_frame, text="Split by ranges",          variable=self.split_method, value="split_ranges",    command=self.on_split_method_change).pack(side='left', padx=10)
        ttk.Radiobutton(method_frame, text="Split Multiple PDFs",      variable=self.split_method, value="split_multiple",  command=self.on_split_method_change).pack(side='left', padx=10)

        # Pages per file
        self.pages_per_frame = ttk.Frame(self.split_frame)
        pages_per_subframe = ttk.Frame(self.pages_per_frame); pages_per_subframe.pack(fill='x', pady=5)
        ttk.Label(pages_per_subframe, text="Pages per file:").pack(side='left')
        self.pages_per_file = tk.StringVar(value="1")
        ttk.Entry(pages_per_subframe, textvariable=self.pages_per_file, width=10).pack(side='left', padx=5)

        # Split at pages
        self.split_at_frame = ttk.Frame(self.split_frame)
        split_at_subframe = ttk.Frame(self.split_at_frame); split_at_subframe.pack(fill='x', pady=5)
        ttk.Label(split_at_subframe, text="Split at pages (comma-separated):").pack(side='left')
        self.split_at_pages = tk.StringVar()
        ttk.Entry(split_at_subframe, textvariable=self.split_at_pages, width=30).pack(side='left', padx=5)
        ttk.Label(split_at_subframe, text="e.g., 5,10,15").pack(side='left')

        # Split ranges
        self.split_ranges_frame = ttk.Frame(self.split_frame)
        ranges_instruction = ttk.Label(self.split_ranges_frame, text="Add page ranges (e.g., 7-18, 19-28):", font=('Arial', 9))
        ranges_instruction.pack(anchor='w', pady=(5, 10))
        ranges_container = ttk.Frame(self.split_ranges_frame); ranges_container.pack(fill='x', pady=5)
        list_frame = ttk.Frame(ranges_container); list_frame.pack(fill='x', pady=5)
        self.ranges_canvas = tk.Canvas(list_frame, height=80)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.ranges_canvas.yview)
        self.scrollable_ranges_frame = ttk.Frame(self.ranges_canvas)
        self.scrollable_ranges_frame.bind("<Configure>", lambda e: self.ranges_canvas.configure(scrollregion=self.ranges_canvas.bbox("all")))
        self.ranges_canvas.create_window((0, 0), window=self.scrollable_ranges_frame, anchor="nw")
        self.ranges_canvas.configure(yscrollcommand=scrollbar.set)
        self.ranges_canvas.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")
        self.ranges_canvas.bind("<MouseWheel>", self._on_ranges_mousewheel)
        self.scrollable_ranges_frame.bind("<MouseWheel>", self._on_ranges_mousewheel)

        add_range_frame = ttk.Frame(ranges_container); add_range_frame.pack(fill='x', pady=5)
        ttk.Label(add_range_frame, text="From:").pack(side='left')
        self.range_from = tk.StringVar(); ttk.Entry(add_range_frame, textvariable=self.range_from, width=8).pack(side='left', padx=5)
        ttk.Label(add_range_frame, text="To:").pack(side='left')
        self.range_to = tk.StringVar(); ttk.Entry(add_range_frame, textvariable=self.range_to, width=8).pack(side='left', padx=5)
        ttk.Button(add_range_frame, text="+ Add Range", command=self.add_range).pack(side='left', padx=10)
        ttk.Button(add_range_frame, text="Clear All", command=self.clear_ranges).pack(side='left', padx=5)
        self.range_entries = []

        # Multi Split UI
        self.multi_split_frame = ttk.Frame(self.split_frame)
        ms_header = ttk.Label(self.multi_split_frame, text="Split Multiple PDFs by Custom Ranges", font=('Arial', 12, 'bold'))
        ms_header.pack(anchor='w', padx=2, pady=(8,6))
        ms_list_container = ttk.Frame(self.multi_split_frame); ms_list_container.pack(fill='x', padx=2)
        self.ms_canvas = tk.Canvas(ms_list_container, height=120)
        self.ms_scrollbar = ttk.Scrollbar(ms_list_container, orient="vertical", command=self.ms_canvas.yview)
        self.ms_inner = ttk.Frame(self.ms_canvas)
        self.ms_inner.bind("<Configure>", lambda e: self.ms_canvas.configure(scrollregion=self.ms_canvas.bbox("all")))
        self.ms_canvas.create_window((0,0), window=self.ms_inner, anchor='nw')
        self.ms_canvas.configure(yscrollcommand=self.ms_scrollbar.set)
        self.ms_canvas.pack(side='left', fill='both', expand=True); self.ms_scrollbar.pack(side='right', fill='y')
        ms_controls = ttk.Frame(self.multi_split_frame); ms_controls.pack(fill='x', pady=6)
        ttk.Button(ms_controls, text="+ Add PDF", command=self.ms_add_pdf_row).pack(side='left')
        ttk.Button(ms_controls, text="Clear All", command=self.ms_clear_all).pack(side='left', padx=6)
        self.ms_merge_output = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.multi_split_frame, text="Merge all split output files into one single PDF", variable=self.ms_merge_output).pack(anchor='w', pady=(2,0))

        # Page Numbering Option
        self.page_num_frame = ttk.Frame(self.main_frame); self.page_num_frame.pack(fill='x', padx=20, pady=10)
        self.add_page_numbers = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.page_num_frame, text="Add Page Numbers (Bottom Right, Font 9)", variable=self.add_page_numbers).pack(anchor='w')
        self.page_num_preview = ttk.Label(self.page_num_frame, text="Page numbers will be added at bottom right corner with font size 9", foreground="gray", font=('Arial', 8))
        self.page_num_preview.pack(anchor='w', pady=(2, 0))

        save_frame = ttk.Frame(self.main_frame); save_frame.pack(fill='x', padx=20, pady=10)
        ttk.Label(save_frame, text="Save Location:").pack(anchor='w')
        save_subframe = ttk.Frame(save_frame); save_subframe.pack(fill='x', pady=5)
        self.save_path = tk.StringVar()
        self.save_entry = ttk.Entry(save_subframe, textvariable=self.save_path, width=50)
        self.save_entry.pack(side='left', fill='x', expand=True)
        ttk.Button(save_subframe, text="Browse", command=self.browse_save).pack(side='left', padx=5)

        self.progress = ttk.Progressbar(self.main_frame, mode='determinate')
        self.progress.pack(fill='x', padx=20, pady=10)
        self.status_label = ttk.Label(self.main_frame, text="Ready")
        self.status_label.pack(pady=5)
        self.execute_button = ttk.Button(self.main_frame, text="Execute Task", command=self.execute_task)
        self.execute_button.pack(pady=20)
        self.task_var.trace('w', self.on_task_change)
        self.on_task_change()
        self.on_split_method_change()

    def _on_ranges_mousewheel(self, event):
        self.ranges_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def on_split_method_change(self):
        self.pages_per_frame.pack_forget()
        self.split_at_frame.pack_forget()
        self.split_ranges_frame.pack_forget()
        self.multi_split_frame.pack_forget()
        mode = self.split_method.get()
        if mode == "pages_per_file":
            self.pages_per_frame.pack(fill='x', pady=5)
        elif mode == "split_at_pages":
            self.split_at_frame.pack(fill='x', pady=5)
        elif mode == "split_ranges":
            self.split_ranges_frame.pack(fill='x', pady=5)
        elif mode == "split_multiple":
            self.multi_split_frame.pack(fill='x', pady=5)

    def add_range(self):
        from_page = self.range_from.get().strip()
        to_page = self.range_to.get().strip()
        if not from_page or not to_page:
            messagebox.showwarning("Warning", "Please enter both 'From' and 'To' page numbers")
            return
        try:
            from_num = int(from_page)
            to_num = int(to_page)
            if from_num <= 0 or to_num <= 0:
                raise ValueError("Page numbers must be positive")
            if from_num > to_num:
                raise ValueError("'From' page must be less than or equal to 'To' page")
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid page numbers: {str(e)}")
            return
        range_str = f"{from_num}-{to_num}"
        range_frame = ttk.Frame(self.scrollable_ranges_frame); range_frame.pack(fill='x', pady=2)
        ttk.Label(range_frame, text=range_str, width=15).pack(side='left')
        ttk.Button(range_frame, text="✕", width=3, command=lambda f=range_frame, r=range_str: self.remove_range(f, r)).pack(side='left', padx=5)
        self.range_entries.append(range_str)
        self.range_from.set(""); self.range_to.set("")
        self.ranges_canvas.configure(scrollregion=self.ranges_canvas.bbox("all"))

    def remove_range(self, frame, range_str):
        frame.destroy()
        if range_str in self.range_entries:
            self.range_entries.remove(range_str)
        self.ranges_canvas.configure(scrollregion=self.ranges_canvas.bbox("all"))

    def clear_ranges(self):
        for widget in self.scrollable_ranges_frame.winfo_children():
            widget.destroy()
        self.range_entries.clear()
        self.ranges_canvas.configure(scrollregion=self.ranges_canvas.bbox("all"))

    # ===== Multi Split helpers inside main app =====
    def ms_add_pdf_row(self):
        row = ttk.Frame(self.ms_inner); row.pack(fill='x', pady=3)
        path_var = tk.StringVar(); range_var = tk.StringVar()
        ttk.Entry(row, textvariable=path_var, width=50).pack(side='left', padx=5)
        ttk.Button(row, text="Browse", command=lambda: self.ms_select_pdf(path_var)).pack(side='left', padx=5)
        ttk.Entry(row, textvariable=range_var, width=30).pack(side='left', padx=5)
        ttk.Label(row, text="e.g. 2-4,6-7,9-9").pack(side='left')
        ttk.Button(row, text="✕", width=3, command=lambda: self.ms_remove_row(row, path_var, range_var)).pack(side='left', padx=5)
        if not hasattr(self, 'ms_pdf_entries'):
            self.ms_pdf_entries = []
        self.ms_pdf_entries.append((path_var, range_var, row))

    def ms_remove_row(self, row, path_var, range_var):
        row.destroy()
        if hasattr(self, 'ms_pdf_entries'):
            self.ms_pdf_entries = [e for e in self.ms_pdf_entries if e[0] != path_var or e[1] != range_var]

    def ms_clear_all(self):
        if hasattr(self, 'ms_pdf_entries'):
            for _, _, r in self.ms_pdf_entries:
                r.destroy()
            self.ms_pdf_entries.clear()

    def ms_select_pdf(self, var):
        file = filedialog.askopenfilename(title="Select PDF", filetypes=[("PDF Files", "*.pdf")])
        if file:
            var.set(file)

    # ===== Layout Tab =====
    def setup_layout_tab(self):
        title_label = ttk.Label(self.layout_frame, text="PDF Layout & Compression", font=('Arial', 16, 'bold'))
        title_label.pack(pady=10)
        source_frame = ttk.Frame(self.layout_frame)
        source_frame.pack(fill='x', padx=20, pady=10)
        ttk.Label(source_frame, text="Source PDF File:").pack(anchor='w')
        source_subframe = ttk.Frame(source_frame); source_subframe.pack(fill='x', pady=5)
        self.layout_source_path = tk.StringVar()
        self.layout_source_entry = ttk.Entry(source_subframe, textvariable=self.layout_source_path, width=50)
        self.layout_source_entry.pack(side='left', fill='x', expand=True)
        ttk.Button(source_subframe, text="Browse", command=self.browse_layout_source).pack(side='left', padx=5)
        output_frame = ttk.Frame(self.layout_frame)
        output_frame.pack(fill='x', padx=20, pady=10)
        ttk.Label(output_frame, text="Output PDF Name:").pack(anchor='w')
        self.layout_output_name = tk.StringVar(value="layout_output.pdf")
        ttk.Entry(output_frame, textvariable=self.layout_output_name, width=50).pack(fill='x', pady=5)
        view_frame = ttk.LabelFrame(self.layout_frame, text="Page View", padding=10)
        view_frame.pack(fill='x', padx=20, pady=10)
        self.page_view = tk.StringVar(value="single")
        view_subframe = ttk.Frame(view_frame); view_subframe.pack(fill='x', pady=5)
        ttk.Radiobutton(view_subframe, text="Single page", variable=self.page_view, value="single").pack(side='left', padx=10)
        ttk.Radiobutton(view_subframe, text="Two pages",   variable=self.page_view, value="two").pack(side='left', padx=10)
        self.separate_cover = tk.BooleanVar(value=False)
        ttk.Checkbutton(view_frame, text="Show cover page separately", variable=self.separate_cover).pack(anchor='w', pady=5)
        multi_frame = ttk.LabelFrame(self.layout_frame, text="Multiple Pages per Sheet", padding=10)
        multi_frame.pack(fill='x', padx=20, pady=10)
        pages_per_sheet_frame = ttk.Frame(multi_frame); pages_per_sheet_frame.pack(fill='x', pady=5)
        ttk.Label(pages_per_sheet_frame, text="Pages per sheet:").pack(side='left')
        self.pages_per_sheet = tk.StringVar(value="2")
        pages_combo = ttk.Combobox(pages_per_sheet_frame, textvariable=self.pages_per_sheet, values=["1", "2", "4", "6", "8"], width=10, state="readonly")
        pages_combo.pack(side='left', padx=5)
        self.add_border = tk.BooleanVar(value=True)
        ttk.Checkbutton(multi_frame, text="Add border around pages", variable=self.add_border).pack(anchor='w', pady=5)
        direction_frame = ttk.Frame(multi_frame); direction_frame.pack(fill='x', pady=5)
        ttk.Label(direction_frame, text="Reading direction:").pack(side='left')
        self.reading_direction = tk.StringVar(value="row_left_right")
        ttk.Combobox(direction_frame, textvariable=self.reading_direction,
                     values=["Row by row, Left to right","Row by row, Right to left","Column by column, Left to right","Column by column, Right to left"],
                     width=30, state="readonly").pack(side='left', padx=5)
        layout_frame = ttk.LabelFrame(self.layout_frame, text="Page Layout", padding=10)
        layout_frame.pack(fill='x', padx=20, pady=10)
        size_frame = ttk.Frame(layout_frame); size_frame.pack(fill='x', pady=5)
        ttk.Label(size_frame, text="Page size:").pack(side='left')
        self.page_size = tk.StringVar(value="A4")
        ttk.Combobox(size_frame, textvariable=self.page_size, values=["A4", "A3", "Letter", "Legal"], width=15, state="readonly").pack(side='left', padx=5)
        orientation_frame = ttk.Frame(layout_frame); orientation_frame.pack(fill='x', pady=5)
        ttk.Label(orientation_frame, text="Orientation:").pack(side='left')
        self.orientation = tk.StringVar(value="auto")
        ttk.Radiobutton(orientation_frame, text="Automatic", variable=self.orientation, value="auto").pack(side='left', padx=10)
        ttk.Radiobutton(orientation_frame, text="Portrait",   variable=self.orientation, value="portrait").pack(side='left', padx=10)
        ttk.Radiobutton(orientation_frame, text="Landscape",  variable=self.orientation, value="landscape").pack(side='left', padx=10)
        margins_frame = ttk.LabelFrame(self.layout_frame, text="Margins", padding=10)
        margins_frame.pack(fill='x', padx=20, pady=10)
        ttk.Label(margins_frame, text="Outer margins (space between content and page edge):").pack(anchor='w', pady=(0,5))
        outer_frame = ttk.Frame(margins_frame); outer_frame.pack(fill='x', pady=5)
        ttk.Label(outer_frame, text="Top:").pack(side='left')
        self.margin_top = tk.StringVar(value="15"); ttk.Entry(outer_frame, textvariable=self.margin_top, width=8).pack(side='left', padx=5); ttk.Label(outer_frame, text="mm").pack(side='left', padx=2)
        ttk.Label(outer_frame, text="Left:").pack(side='left', padx=(20,0))
        self.margin_left = tk.StringVar(value="15"); ttk.Entry(outer_frame, textvariable=self.margin_left, width=8).pack(side='left', padx=5); ttk.Label(outer_frame, text="mm").pack(side='left', padx=2)
        ttk.Label(outer_frame, text="Right:").pack(side='left', padx=(20,0))
        self.margin_right = tk.StringVar(value="15"); ttk.Entry(outer_frame, textvariable=self.margin_right, width=8).pack(side='left', padx=5); ttk.Label(outer_frame, text="mm").pack(side='left', padx=2)
        ttk.Label(outer_frame, text="Bottom:").pack(side='left', padx=(20,0))
        self.margin_bottom = tk.StringVar(value="15"); ttk.Entry(outer_frame, textvariable=self.margin_bottom, width=8).pack(side='left', padx=5); ttk.Label(outer_frame, text="mm").pack(side='left', padx=2)
        line_frame = ttk.Frame(margins_frame); line_frame.pack(fill='x', pady=5)
        ttk.Label(line_frame, text="Line margin (space between pages):").pack(side='left')
        self.line_margin = tk.StringVar(value="5")
        ttk.Entry(line_frame, textvariable=self.line_margin, width=8).pack(side='left', padx=5); ttk.Label(line_frame, text="mm").pack(side='left', padx=2)
        save_layout_frame = ttk.Frame(self.layout_frame); save_layout_frame.pack(fill='x', padx=20, pady=10)
        ttk.Label(save_layout_frame, text="Save Location:").pack(anchor='w')
        save_layout_subframe = ttk.Frame(save_layout_frame); save_layout_subframe.pack(fill='x', pady=5)
        self.layout_save_path = tk.StringVar()
        self.layout_save_entry = ttk.Entry(save_layout_subframe, textvariable=self.layout_save_path, width=50)
        self.layout_save_entry.pack(side='left', fill='x', expand=True)
        ttk.Button(save_layout_subframe, text="Browse", command=self.browse_layout_save).pack(side='left', padx=5)
        self.layout_progress = ttk.Progressbar(self.layout_frame, mode='determinate')
        self.layout_progress.pack(fill='x', padx=20, pady=10)
        self.layout_status_label = ttk.Label(self.layout_frame, text="Ready")
        self.layout_status_label.pack(pady=5)
        ttk.Button(self.layout_frame, text="Apply Layout & Compression", command=self.execute_layout).pack(pady=20)

    # ===== Code tab =====
    def setup_code_tab(self):
        title_label = ttk.Label(self.code_frame, text="Apdf - Application Code Editor", font=('Arial', 14, 'bold'))
        title_label.pack(pady=10)
        instructions = """Paste your updated Python code here and click 'Update Application' to modify the application.
        This will replace the current application code with the new code."""
        instruction_label = ttk.Label(self.code_frame, text=instructions, wraplength=650)
        instruction_label.pack(pady=10, padx=20)
        self.code_text = scrolledtext.ScrolledText(self.code_frame, width=80, height=20)
        self.code_text.pack(fill='both', expand=True, padx=20, pady=10)
        self.load_current_code()
        ttk.Button(self.code_frame, text="Update Application", command=self.update_application).pack(pady=10)


    # === Update.Code TAB (Append / Replace) ===  # NEW
    def setup_update_tab(self):  # NEW
        """Create the Update.Code tab UI with mode selector and actions."""  # NEW
        title_label = ttk.Label(self.update_frame, text="Update.Code - Patch Manager", font=('Arial', 14, 'bold'))  # NEW
        title_label.pack(pady=10)  # NEW
        tips = "Paste your new feature/patch here. Choose mode below, then click Apply Update."  # NEW
        ttk.Label(self.update_frame, text=tips, wraplength=650).pack(pady=6, padx=20)  # NEW
        # Mode selector  # NEW
        mode_frame = ttk.Frame(self.update_frame)  # NEW
        mode_frame.pack(pady=4)  # NEW
        ttk.Label(mode_frame, text="Select Update Mode:").pack(side=tk.LEFT, padx=(0,8))  # NEW
        self.update_mode = tk.StringVar(value="Append")  # NEW
        ttk.Combobox(mode_frame, textvariable=self.update_mode, values=["Append", "Replace"], width=18, state="readonly").pack(side=tk.LEFT)  # NEW
        self.update_code_text = scrolledtext.ScrolledText(self.update_frame, width=80, height=18)  # NEW
        self.update_code_text.pack(fill='both', expand=True, padx=20, pady=10)  # NEW
        btns = ttk.Frame(self.update_frame)  # NEW
        btns.pack(pady=6)  # NEW
        ttk.Button(btns, text="Apply Update", command=self.apply_update_mode).pack(side=tk.LEFT, padx=6)  # NEW
        ttk.Button(btns, text="Clear", command=lambda: self.update_code_text.delete(1.0, tk.END)).pack(side=tk.LEFT, padx=6)  # NEW

    def apply_update_mode(self):  # NEW
        """Run appropriate update method based on dropdown selection."""  # NEW
        mode = (self.update_mode.get() or "Append").strip().lower()  # NEW
        if mode == "replace":  # NEW
            self.apply_update_replace()  # NEW
        else:  # NEW
            self.apply_update_append()  # NEW

    def apply_update_append(self):  # NEW
        """Append the Update.Code text to the end of the Code Editor content (in-app only)."""  # NEW
        try:  # NEW
            if not hasattr(self, "code_text"):  # NEW
                messagebox.showerror("Error", "Code Editor not initialized.")  # NEW
                return  # NEW
            patch = self.update_code_text.get(1.0, tk.END)  # NEW
            if not patch.strip():  # NEW
                messagebox.showwarning("Warning", "No patch code to append!")  # NEW
                return  # NEW
            main_code = self.code_text.get(1.0, tk.END)  # NEW
            merged = main_code.rstrip() + "\n\n# === PATCH APPENDED (Update.Code) ===  # NEW\n" + patch  # NEW
            self.code_text.delete(1.0, tk.END)  # NEW
            self.code_text.insert(1.0, merged)  # NEW
            messagebox.showinfo("Success", "Patch appended to Code Editor. Review, then use 'Update Application' to apply it to the file.")  # NEW
        except Exception as e:  # NEW
            messagebox.showerror("Error", f"Failed to append patch: {str(e)}")  # NEW

    def apply_update_replace(self):  # NEW
        """Replace existing def/class blocks by name; append if not found."""  # NEW
        try:  # NEW
            import re  # NEW
            if not hasattr(self, "code_text"):  # NEW
                messagebox.showerror("Error", "Code Editor not initialized.")  # NEW
                return  # NEW
            patch = self.update_code_text.get(1.0, tk.END)  # NEW
            if not patch.strip():  # NEW
                messagebox.showwarning("Warning", "No patch code to apply!")  # NEW
                return  # NEW
            main_code = self.code_text.get(1.0, tk.END)  # NEW
            updated_code = main_code  # NEW
            # Find top-level def/class names in the patch  # NEW
            header_re = re.compile(r"^(def|class)\s+(\w+)", re.MULTILINE)  # NEW
            for m in header_re.finditer(patch):  # NEW
                name = m.group(2)  # NEW
                start = m.start()  # NEW
                # Slice the block in patch from this header to the next header or end  # NEW
                next_m = header_re.search(patch, m.end())  # NEW
                block_code = patch[start:(next_m.start() if next_m else len(patch))]  # NEW
                # Replace the corresponding block in main code if present  # NEW
                target_re = re.compile(rf"^(def|class)\s+{name}\b[\s\S]*?(?=^def\s+|^class\s+|\Z)", re.MULTILINE)  # NEW
                if target_re.search(updated_code):  # NEW
                    updated_code = target_re.sub(block_code, updated_code)  # NEW
                else:  # NEW
                    updated_code = updated_code.rstrip() + "\n\n# === PATCH ADDED (new section) ===  # NEW\n" + block_code  # NEW
            self.code_text.delete(1.0, tk.END)  # NEW
            self.code_text.insert(1.0, updated_code)  # NEW
            messagebox.showinfo("Success", "Patch (Replace Mode) applied to Code Editor!")  # NEW
        except Exception as e:  # NEW
            messagebox.showerror("Error", f"Failed to replace code: {str(e)}")  # NEW

    def load_current_code(self):
        try:
            with open(__file__, 'r', encoding='utf-8') as f:
                current_code = f.read()
            self.code_text.delete(1.0, tk.END)
            self.code_text.insert(1.0, current_code)
        except Exception as e:
            messagebox.showerror("Error", f"Could not load current code: {str(e)}")

    def update_application(self):
        new_code = self.code_text.get(1.0, tk.END)
        if not new_code.strip():
            messagebox.showwarning("Warning", "No code to update!"); return
        try:
            compile(new_code, '<string>', 'exec')
            backup_file = __file__ + ".backup"
            with open(backup_file, 'w', encoding='utf-8') as f:
                with open(__file__, 'r', encoding='utf-8') as original:
                    f.write(original.read())
            with open(__file__, 'w', encoding='utf-8') as f:
                f.write(new_code)
            messagebox.showinfo("Success", "Application updated successfully! The application will now restart.")
            python = sys.executable
            os.execl(python, python, *sys.argv)
        except SyntaxError as e:
            messagebox.showerror("Syntax Error", f"The code contains syntax errors:\n{str(e)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update application: {str(e)}")

    def on_task_change(self, *args):
        if self.task_var.get() == "split":
            self.split_frame.pack(fill='x', padx=20, pady=10, before=self.page_num_frame)
        else:
            self.split_frame.pack_forget()

    def browse_source(self):
        if self.task_var.get() == "merge":
            files = filedialog.askopenfilenames(title="Select PDF files to merge", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
            if files:
                self.source_path.set(";".join(files))
        else:
            file = filedialog.askopenfilename(title="Select PDF file to split", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
            if file:
                self.source_path.set(file)

    def browse_layout_source(self):
        file = filedialog.askopenfilename(title="Select PDF file for layout", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
        if file:
            self.layout_source_path.set(file)

    def browse_multiple_files(self):
        files = filedialog.askopenfilenames(title="Select PDF files to merge", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
        if files:
            self.source_path.set(";".join(files))

    def browse_save(self):
        if self.task_var.get() == "merge":
            file = filedialog.asksaveasfilename(title="Save merged PDF as", defaultextension=".pdf", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
            if file:
                self.save_path.set(file)
                if not self.pdf_name.get() or self.pdf_name.get() == "output.pdf":
                    self.pdf_name.set(os.path.basename(file))
        else:
            folder = filedialog.askdirectory(title="Select folder to save split PDFs")
            if folder:
                self.save_path.set(folder)

    def browse_layout_save(self):
        file = filedialog.asksaveasfilename(title="Save layout PDF as", defaultextension=".pdf", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
        if file:
            self.layout_save_path.set(file)
            if not self.layout_output_name.get() or self.layout_output_name.get() == "layout_output.pdf":
                self.layout_output_name.set(os.path.basename(file))

    def validate_inputs(self):
        if not hasattr(self, 'source_path'):
            self.source_path = tk.StringVar(value="")
        if not self.source_path.get() and self.task_var.get() == 'merge':
            messagebox.showerror("Error", "Please select source file(s)"); return False
        if not self.pdf_name.get():
            messagebox.showerror("Error", "Please enter output PDF name"); return False
        if not self.save_path.get():
            messagebox.showerror("Error", "Please select save location"); return False
        if self.task_var.get() == "split":
            mode = self.split_method.get()
            if mode == "pages_per_file":
                if not self.pages_per_file.get():
                    messagebox.showerror("Error", "Please specify pages per file"); return False
                try:
                    pages = int(self.pages_per_file.get())
                    if pages <= 0: raise ValueError
                except ValueError:
                    messagebox.showerror("Error", "Pages per file must be a positive integer"); return False
            elif mode == "split_at_pages":
                if not self.split_at_pages.get():
                    messagebox.showerror("Error", "Please specify split pages"); return False
                try:
                    pages = [int(p.strip()) for p in self.split_at_pages.get().split(',')]
                    if any(p <= 0 for p in pages): raise ValueError
                except ValueError:
                    messagebox.showerror("Error", "Split pages must be positive integers separated by commas"); return False
            elif mode == "split_ranges":
                if not self.range_entries:
                    messagebox.showerror("Error", "Please add at least one page range"); return False
            elif mode == "split_multiple":
                if not hasattr(self, 'ms_pdf_entries') or len(self.ms_pdf_entries) == 0:
                    messagebox.showerror("Error", "Please add at least one PDF and ranges in Multi Split"); return False
                for pvar, rvar, _ in self.ms_pdf_entries:
                    if not pvar.get() or not rvar.get():
                        messagebox.showerror("Error", "Every Multi Split row must have a PDF and ranges"); return False
        return True

    def validate_layout_inputs(self):
        if not self.layout_source_path.get():
            messagebox.showerror("Error", "Please select source PDF file"); return False
        if not self.layout_output_name.get():
            messagebox.showerror("Error", "Please enter output PDF name"); return False
        if not self.layout_save_path.get():
            messagebox.showerror("Error", "Please select save location"); return False
        try:
            margin_top = float(self.margin_top.get())
            margin_left = float(self.margin_left.get())
            margin_right = float(self.margin_right.get())
            margin_bottom = float(self.margin_bottom.get())
            line_margin = float(self.line_margin.get())
            if any(m < 0 for m in [margin_top, margin_left, margin_right, margin_bottom, line_margin]):
                raise ValueError("Margins cannot be negative")
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid margin values: {str(e)}"); return False
        return True

    def execute_task(self):
        if not self.validate_inputs(): return
        self.progress['value'] = 0
        self.status_label.config(text="Processing...")
        thread = threading.Thread(target=self._execute_task_thread)
        thread.daemon = True; thread.start()

    def execute_layout(self):
        if not self.validate_layout_inputs(): return
        self.layout_progress['value'] = 0
        self.layout_status_label.config(text="Processing layout...")
        thread = threading.Thread(target=self._execute_layout_thread)
        thread.daemon = True; thread.start()

    def _execute_task_thread(self):
        try:
            if self.task_var.get() == "merge":
                self.merge_pdfs()
            else:
                mode = self.split_method.get()
                if mode == 'split_multiple':
                    self.split_multiple_pdfs()
                else:
                    self.split_pdf()
            self.root.after(0, lambda: self.status_label.config(text="Task completed successfully!"))
            self.root.after(0, lambda: messagebox.showinfo("Success", "Task completed successfully!"))
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda: self.status_label.config(text="Error occurred"))
            self.root.after(0, lambda: messagebox.showerror("Error", f"An error occurred: {error_msg}"))
        finally:
            self.root.after(0, lambda: self.progress.config(value=0))

    def _execute_layout_thread(self):
        try:
            self.apply_layout()
            self.root.after(0, lambda: self.layout_status_label.config(text="Layout applied successfully!"))
            self.root.after(0, lambda: messagebox.showinfo("Success", "Layout applied successfully!"))
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda: self.layout_status_label.config(text="Error occurred"))
            self.root.after(0, lambda: messagebox.showerror("Error", f"An error occurred: {error_msg}"))
        finally:
            self.root.after(0, lambda: self.layout_progress.config(value=0))

    def add_page_numbers_to_pdf(self, input_pdf_path, output_pdf_path):
        try:
            with open(input_pdf_path, 'rb') as file:
                reader = PdfReader(file)
                writer = PdfWriter()
                for page_num, page in enumerate(reader.pages, 1):
                    packet = io.BytesIO()
                    can = canvas.Canvas(packet, pagesize=letter)
                    can.setFont("Helvetica", 9)
                    can.drawRightString(letter[0] - 0.5*inch, 0.5*inch, str(page_num))
                    can.save()
                    packet.seek(0)
                    number_pdf = PdfReader(packet)
                    number_page = number_pdf.pages[0]
                    page.merge_page(number_page)
                    writer.add_page(page)
                with open(output_pdf_path, 'wb') as output_file:
                    writer.write(output_file)
        except Exception as e:
            raise Exception(f"Error adding page numbers: {str(e)}")

    def merge_pdfs(self):
        source_files = self.source_path.get().split(';')
        output_file = os.path.join(self.save_path.get(), self.pdf_name.get())
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        temp_output = output_file
        merger = PdfMerger()
        total_files = len(source_files)
        for i, file_path in enumerate(source_files):
            try:
                merger.append(file_path)
                progress = (i + 1) / total_files * 100
                self.root.after(0, lambda p=progress: self.progress.config(value=p))
                self.root.after(0, lambda f=file_path: self.status_label.config(text=f"Merging: {os.path.basename(f)}"))
            except Exception as e:
                raise Exception(f"Error merging {file_path}: {str(e)}")
        with open(temp_output, 'wb') as output:
            merger.write(output)
        merger.close()
        if self.add_page_numbers.get():
            self.root.after(0, lambda: self.status_label.config(text="Adding page numbers..."))
            final_output = output_file.replace('.pdf', '_numbered.pdf')
            self.add_page_numbers_to_pdf(temp_output, final_output)
            try:
                os.remove(temp_output)
            except Exception:
                pass
        else:
            final_output = temp_output

    def split_pdf(self):
        input_file = self.source_path.get()
        output_dir = self.save_path.get()
        os.makedirs(output_dir, exist_ok=True)
        with open(input_file, 'rb') as file:
            reader = PdfReader(file)
            total_pages = len(reader.pages)
            if self.split_method.get() == "pages_per_file":
                pages_per_file = int(self.pages_per_file.get())
                split_files = self._split_by_pages(reader, output_dir, pages_per_file, total_pages)
            elif self.split_method.get() == "split_at_pages":
                split_points = [int(p.strip()) for p in self.split_at_pages.get().split(',')]
                split_files = self._split_at_pages(reader, output_dir, split_points, total_pages)
            else:
                split_files = self._split_by_ranges(reader, output_dir, total_pages)
            if self.add_page_numbers.get():
                self.root.after(0, lambda: self.status_label.config(text="Adding page numbers to split files..."))
                for split_file in split_files:
                    numbered_file = split_file.replace('.pdf', '_numbered.pdf')
                    self.add_page_numbers_to_pdf(split_file, numbered_file)
                    try:
                        os.remove(split_file)
                    except Exception:
                        pass

    def split_multiple_pdfs(self):
        output_dir = self.save_path.get()
        os.makedirs(output_dir, exist_ok=True)
        all_output_files = []
        rows = getattr(self, 'ms_pdf_entries', [])
        total_rows = len(rows) if rows else 1
        for idx_row, (pdf_var, range_var, _) in enumerate(rows):
            pdf_path = pdf_var.get()
            ranges_str = range_var.get()
            if not pdf_path or not ranges_str:
                continue
            with open(pdf_path, 'rb') as f:
                reader = PdfReader(f)
                total_pages = len(reader.pages)
                base_name = os.path.splitext(os.path.basename(pdf_path))[0]
                parts = [r.strip() for r in ranges_str.split(',') if r.strip()]
                for p_idx, rng in enumerate(parts):
                    if '-' not in rng:
                        continue
                    start, end = map(int, rng.split('-'))
                    start, end = max(1, start), min(total_pages, end)
                    writer = PdfWriter()
                    for page_num in range(start - 1, end):
                        writer.add_page(reader.pages[page_num])
                    out_file = os.path.join(output_dir, f"{base_name}_part_{p_idx+1}_{start}-{end}.pdf")
                    with open(out_file, 'wb') as out:
                        writer.write(out)
                    all_output_files.append(out_file)
            progress = (idx_row + 1) / total_rows * 100
            self.root.after(0, lambda p=progress: self.progress.config(value=p))
            self.root.after(0, lambda f=os.path.basename(pdf_path): self.status_label.config(text=f"Processed: {f}"))
        if getattr(self, 'ms_merge_output', None) and self.ms_merge_output.get() and all_output_files:
            merged_file = os.path.join(output_dir, "Merged_Output.pdf")
            merger = PdfMerger()
            for f in all_output_files:
                merger.append(f)
            with open(merged_file, 'wb') as out:
                merger.write(out)
            merger.close()
            for f in all_output_files:
                try:
                    os.remove(f)
                except Exception:
                    pass

    def _split_by_pages(self, reader, output_dir, pages_per_file, total_pages):
        base_name = os.path.splitext(self.pdf_name.get())[0]
        split_files = []
        for start_page in range(0, total_pages, pages_per_file):
            end_page = min(start_page + pages_per_file, total_pages)
            output_file = os.path.join(output_dir, f"{base_name}_pages_{start_page+1}-{end_page}.pdf")
            split_files.append(output_file)
            writer = PdfWriter()
            for page_num in range(start_page, end_page):
                writer.add_page(reader.pages[page_num])
            with open(output_file, 'wb') as output:
                writer.write(output)
            progress = (end_page / total_pages) * 100
            self.root.after(0, lambda p=progress: self.progress.config(value=p))
            self.root.after(0, lambda: self.status_label.config(text=f"Split: {os.path.basename(output_file)}"))
        return split_files

    def _split_at_pages(self, reader, output_dir, split_points, total_pages):
        base_name = os.path.splitext(self.pdf_name.get())[0]
        split_points = [0] + split_points + [total_pages]
        split_points.sort()
        split_files = []
        for i in range(len(split_points) - 1):
            start_page = split_points[i]
            end_page = split_points[i + 1]
            if start_page == end_page:
                continue
            output_file = os.path.join(output_dir, f"{base_name}_part_{i+1}.pdf")
            split_files.append(output_file)
            writer = PdfWriter()
            for page_num in range(start_page, end_page):
                writer.add_page(reader.pages[page_num])
            with open(output_file, 'wb') as output:
                writer.write(output)
            progress = ((i + 1) / (len(split_points) - 1)) * 100
            self.root.after(0, lambda p=progress: self.progress.config(value=p))
            self.root.after(0, lambda: self.status_label.config(text=f"Split: {os.path.basename(output_file)}"))
        return split_files

    def _split_by_ranges(self, reader, output_dir, total_pages):
        base_name = os.path.splitext(self.pdf_name.get())[0]
        split_files = []
        for i, range_str in enumerate(self.range_entries):
            try:
                start_page, end_page = map(int, range_str.split('-'))
                if start_page < 1 or end_page > total_pages or start_page > end_page:
                    raise ValueError(f"Invalid range: {range_str}")
                output_file = os.path.join(output_dir, f"{base_name}_range_{i+1}_{start_page}-{end_page}.pdf")
                split_files.append(output_file)
                writer = PdfWriter()
                for page_num in range(start_page-1, end_page):
                    writer.add_page(reader.pages[page_num])
                with open(output_file, 'wb') as output:
                    writer.write(output)
                progress = ((i + 1) / len(self.range_entries)) * 100
                self.root.after(0, lambda p=progress: self.progress.config(value=p))
                self.root.after(0, lambda: self.status_label.config(text=f"Split: {os.path.basename(output_file)}"))
            except Exception as e:
                raise Exception(f"Error processing range {range_str}: {str(e)}")
        return split_files

    def apply_layout(self):
        input_file = self.layout_source_path.get()
        output_file = os.path.join(self.layout_save_path.get(), self.layout_output_name.get())
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        pages_per_sheet = int(self.pages_per_sheet.get())
        margin_top = float(self.margin_top.get()) * mm
        margin_left = float(self.margin_left.get()) * mm
        margin_right = float(self.margin_right.get()) * mm
        margin_bottom = float(self.margin_bottom.get()) * mm
        line_margin = float(self.line_margin.get()) * mm
        page_sizes = {"A4": A4, "A3": A3, "Letter": letter, "Legal": legal}
        base_page_size = page_sizes.get(self.page_size.get(), A4)
        if self.orientation.get() == "landscape":
            page_size = landscape(base_page_size)
        elif self.orientation.get() == "portrait":
            page_size = base_page_size
        else:
            page_size = landscape(base_page_size) if pages_per_sheet > 2 else base_page_size
        if pages_per_sheet == 1:
            cols, rows = 1, 1
        elif pages_per_sheet == 2:
            cols, rows = 2, 1
        elif pages_per_sheet == 4:
            cols, rows = 2, 2
        elif pages_per_sheet == 6:
            cols, rows = 3, 2
        elif pages_per_sheet == 8:
            cols, rows = 4, 2
        else:
            cols, rows = 2, 2
        usable_width = page_size[0] - margin_left - margin_right
        usable_height = page_size[1] - margin_top - margin_bottom
        page_width = (usable_width - (cols - 1) * line_margin) / cols
        page_height = (usable_height - (rows - 1) * line_margin) / rows
        with open(input_file, 'rb') as file:
            reader = PdfReader(file)
            total_pages = len(reader.pages)
            writer = PdfWriter()
            for sheet_num in range(0, total_pages, pages_per_sheet):
                blank_page = PageObject.create_blank_page(width=page_size[0], height=page_size[1])
                page_index = 0
                for row in range(rows):
                    for col in range(cols):
                        if sheet_num + page_index >= total_pages:
                            break
                        x = margin_left + col * (page_width + line_margin)
                        y = margin_bottom + (rows - row - 1) * (page_height + line_margin)
                        source_page = reader.pages[sheet_num + page_index]
                        source_width = float(source_page.mediabox.width)
                        source_height = float(source_page.mediabox.height)
                        scale_x = page_width / source_width
                        scale_y = page_height / source_height
                        scale = min(scale_x, scale_y)
                        scaled_width = source_width * scale
                        scaled_height = source_height * scale
                        x_centered = x + (page_width - scaled_width) / 2
                        y_centered = y + (page_height - scaled_height) / 2
                        source_page = source_page.scale(scale, scale)
                        source_page = source_page.copy()
                        source_page.add_transformation([1, 0, 0, 1, x_centered, y_centered])
                        blank_page.merge_page(source_page)
                        if self.add_border.get():
                            border_packet = io.BytesIO()
                            border_canvas = canvas.Canvas(border_packet, pagesize=page_size)
                            border_canvas.setStrokeColorRGB(0, 0, 0)
                            border_canvas.setLineWidth(0.5)
                            border_canvas.rect(x, y, page_width, page_height)
                            border_canvas.save()
                            border_packet.seek(0)
                            border_pdf = PdfReader(border_packet)
                            border_page = border_pdf.pages[0]
                            blank_page.merge_page(border_page)
                        page_index += 1
                writer.add_page(blank_page)
                progress = min(100, (sheet_num + pages_per_sheet) / total_pages * 100)
                self.root.after(0, lambda p=progress: self.layout_progress.config(value=p))
                self.root.after(0, lambda: self.layout_status_label.config(text=f"Processing sheet {(sheet_num // pages_per_sheet) + 1}"))
            with open(output_file, 'wb') as output:
                writer.write(output)

def main():
    root = tk.Tk()
    app = PDFToolApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
