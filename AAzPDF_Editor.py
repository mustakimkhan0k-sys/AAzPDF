import sys
import fitz  # PyMuPDF
import os
import shutil

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QToolBar,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsRectItem, QGraphicsItem, QColorDialog,
    QToolButton, QMenu, QLabel, QDialog, QVBoxLayout,
    QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QComboBox, QSpinBox, QStatusBar, 
    QGraphicsEllipseItem, QFrame, QWidget, QLineEdit,
    QGraphicsTextItem, QTextEdit, QGraphicsProxyWidget,
    QFontDialog, QInputDialog
)
from PySide6.QtGui import (
    QPixmap, QImage, QPen, QColor, QAction, QPainter, 
    QBrush, QCursor, QFont, QLinearGradient, QRadialGradient,
    QPalette, QIcon, QTextCursor
)
from PySide6.QtCore import Qt, QRectF, QPointF, QSize


# =====================================================
# STEP 1: STABLE GRAPHICS VIEW
# =====================================================
class PDFGraphicsView(QGraphicsView):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        
        # Basic settings - keep it simple for stability
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        
        # Disable drag mode by default to prevent conflicts
        self.setDragMode(QGraphicsView.NoDrag)

    def wheelEvent(self, event):
        bar = self.verticalScrollBar()
        super().wheelEvent(event)

        if event.angleDelta().y() < 0 and bar.value() == bar.maximum():
            self.editor.next_page()
        elif event.angleDelta().y() > 0 and bar.value() == bar.minimum():
            self.editor.prev_page()

    def mousePressEvent(self, event):
        # Safe shape creation - catch any exceptions
        try:
            if self.editor.tool == "rect" and event.button() == Qt.LeftButton:
                pos = self.mapToScene(event.position().toPoint())
                self.editor.create_shape_at_position(pos.x(), pos.y())
                event.accept()
                return
            elif self.editor.tool == "text" and event.button() == Qt.LeftButton:
                pos = self.mapToScene(event.position().toPoint())
                self.editor.create_text_at_position(pos.x(), pos.y())
                event.accept()
                return
        except Exception as e:
            print(f"Error creating shape: {e}")
        super().mousePressEvent(event)


# =====================================================
# STEP 2: ENHANCED SHAPE ITEM WITH INTERACTIVE RESIZE CONTROLS
# =====================================================
class ResizeHandle(QGraphicsEllipseItem):
    """Interactive resize handle (control point)"""
    def __init__(self, parent_shape, position_index):
        super().__init__(-6, -6, 12, 12)  # 12x12 circle
        self.parent_shape = parent_shape
        self.position_index = position_index
        
        # Styling
        self.setPen(QPen(QColor(0, 0, 0), 1))
        self.setBrush(QBrush(QColor(255, 255, 255)))
        
        # Make it selectable and movable
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        
        # Store original position
        self.original_pos = QPointF(0, 0)
        
        # Set cursor based on position
        self.set_cursor()
        self.setZValue(1000)  # Make sure handles are on top
    
    def set_cursor(self):
        """Set appropriate cursor based on handle position"""
        cursors = [
            Qt.SizeFDiagCursor,    # 0: Top-left
            Qt.SizeVerCursor,      # 1: Top
            Qt.SizeBDiagCursor,    # 2: Top-right
            Qt.SizeHorCursor,      # 3: Right
            Qt.SizeFDiagCursor,    # 4: Bottom-right
            Qt.SizeVerCursor,      # 5: Bottom
            Qt.SizeBDiagCursor,    # 6: Bottom-left
            Qt.SizeHorCursor       # 7: Left
        ]
        # Set cursor directly without using setProperty to avoid warning
        self.setCursor(QCursor(cursors[self.position_index % 8]))
    
    def mousePressEvent(self, event):
        """Handle mouse press on resize handle"""
        if event.button() == Qt.LeftButton:
            self.parent_shape.resizing = True
            self.parent_shape.resize_handle = self.position_index
            self.original_pos = event.scenePos()
            event.accept()
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse drag on resize handle"""
        if self.parent_shape.resizing:
            new_pos = event.scenePos()
            self.parent_shape.resize_shape(new_pos, self.position_index)
            event.accept()
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release on resize handle"""
        if event.button() == Qt.LeftButton:
            self.parent_shape.resizing = False
            self.parent_shape.resize_handle = None
            event.accept()
        super().mouseReleaseEvent(event)


class ShapeData:
    """Simple data class to store shape information without QGraphicsItem"""
    def __init__(self, x, y, width, height, border_color, fill_color, page_num):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.border_color = border_color
        self.fill_color = fill_color
        self.page_num = page_num
        self.selected = False
        self.control_points = []
        self.resizing = False
        self.resize_handle = None
        self.current_scale = 1.0
        self.original_width = width
        self.original_height = height


class TextData:
    """Simple data class to store text information without QGraphicsItem"""
    def __init__(self, x, y, width, height, text, font_family, font_size, text_color, page_num):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.text = text
        self.font_family = font_family
        self.font_size = font_size
        self.text_color = text_color
        self.page_num = page_num
        self.selected = False
        self.control_points = []
        self.resizing = False
        self.resize_handle = None
        self.current_scale = 1.0
        self.original_width = width
        self.original_height = height


class ShapeItem(QGraphicsRectItem):
    def __init__(self, shape_data, scene=None):
        x, y, width, height = shape_data.x, shape_data.y, shape_data.width, shape_data.height
        super().__init__(x, y, width, height)
        self.shape_data = shape_data
        self.scene_ref = scene
        
        # Apply styling from shape data
        self.setPen(QPen(QColor(shape_data.border_color), 2))
        self.setBrush(QBrush(QColor(shape_data.fill_color)))
        
        # Enable moving and selection
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        
        # NEW: Resize control points
        self.control_points = []
        self.resizing = False
        self.resize_handle = None
        
        # NEW: Store original rect for resize calculations
        self.original_rect = QRectF(x, y, width, height)
        
        # NEW: Create control points (will be created when added to scene)
        self.controls_created = False

    def create_control_points(self):
        """Create 8 control points around the shape"""
        if self.controls_created:
            return
            
        rect = self.rect()
        
        # Define 8 handle positions (corners and edges)
        positions = [
            (rect.left(), rect.top()),        # 0: Top-left
            (rect.center().x(), rect.top()),  # 1: Top
            (rect.right(), rect.top()),       # 2: Top-right
            (rect.right(), rect.center().y()), # 3: Right
            (rect.right(), rect.bottom()),    # 4: Bottom-right
            (rect.center().x(), rect.bottom()), # 5: Bottom
            (rect.left(), rect.bottom()),     # 6: Bottom-left
            (rect.left(), rect.center().y())  # 7: Left
        ]
        
        for i, (x, y) in enumerate(positions):
            handle = ResizeHandle(self, i)
            handle.setPos(x, y)
            self.control_points.append(handle)
            # Add to scene if we have a scene reference
            if self.scene():
                self.scene().addItem(handle)
                handle.setParentItem(self)
        
        self.controls_created = True
    
    def update_control_points(self):
        """Update control point positions after shape changes"""
        if not self.control_points:
            return
            
        rect = self.rect()
        positions = [
            (rect.left(), rect.top()),
            (rect.center().x(), rect.top()),
            (rect.right(), rect.top()),
            (rect.right(), rect.center().y()),
            (rect.right(), rect.bottom()),
            (rect.center().x(), rect.bottom()),
            (rect.left(), rect.bottom()),
            (rect.left(), rect.center().y())
        ]
        
        for i, handle in enumerate(self.control_points):
            if i < len(positions):
                handle.setPos(positions[i][0], positions[i][1])
    
    def show_control_points(self):
        """Show all control points"""
        if not self.controls_created:
            self.create_control_points()
            
        for handle in self.control_points:
            handle.show()
    
    def hide_control_points(self):
        """Hide all control points"""
        for handle in self.control_points:
            handle.hide()
    
    def resize_shape(self, new_pos, handle_index):
        """Resize shape based on dragged control point"""
        rect = self.rect()
        old_rect = QRectF(rect)
        
        # Calculate delta from original mouse position
        if handle_index == 0:  # Top-left
            rect.setTopLeft(new_pos)
        elif handle_index == 1:  # Top
            rect.setTop(new_pos.y())
        elif handle_index == 2:  # Top-right
            rect.setTopRight(new_pos)
        elif handle_index == 3:  # Right
            rect.setRight(new_pos.x())
        elif handle_index == 4:  # Bottom-right
            rect.setBottomRight(new_pos)
        elif handle_index == 5:  # Bottom
            rect.setBottom(new_pos.y())
        elif handle_index == 6:  # Bottom-left
            rect.setBottomLeft(new_pos)
        elif handle_index == 7:  # Left
            rect.setLeft(new_pos.x())
        
        # Ensure minimum size
        if rect.width() < 20:
            if handle_index in [0, 6, 7]:  # Left handles
                rect.setLeft(old_rect.right() - 20)
            else:  # Right handles
                rect.setRight(old_rect.left() + 20)
        
        if rect.height() < 20:
            if handle_index in [0, 1, 2]:  # Top handles
                rect.setTop(old_rect.bottom() - 20)
            else:  # Bottom handles
                rect.setBottom(old_rect.top() + 20)
        
        # Update the shape
        self.setRect(rect.normalized())
        
        # Update the shape data
        self.shape_data.x = rect.x()
        self.shape_data.y = rect.y()
        self.shape_data.width = rect.width()
        self.shape_data.height = rect.height()
        
        # Update control points positions
        self.update_control_points()
        
        # Update scale
        self.shape_data.current_scale = rect.width() / self.shape_data.original_width
    
    def itemChange(self, change, value):
        """Handle item changes (like selection)"""
        if change == QGraphicsItem.ItemSelectedChange:
            self.shape_data.selected = bool(value)
            if value:  # Selected
                self.show_control_points()
            else:  # Deselected
                self.hide_control_points()
        elif change == QGraphicsItem.ItemPositionHasChanged:
            # Update shape data when shape moves
            rect = self.rect()
            self.shape_data.x = rect.x()
            self.shape_data.y = rect.y()
            # Update control points when shape moves
            self.update_control_points()
        elif change == QGraphicsItem.ItemSceneHasChanged:
            # Scene has changed, recreate control points if needed
            if value and not self.controls_created:
                self.create_control_points()
        
        return super().itemChange(change, value)
    
    def resize(self, scale_factor):
        """Resize the shape by scale factor (for toolbar buttons)"""
        self.shape_data.current_scale = max(0.2, min(5.0, self.shape_data.current_scale * scale_factor))
        
        # Calculate new size based on original size and current scale
        new_width = self.shape_data.original_width * self.shape_data.current_scale
        new_height = self.shape_data.original_height * self.shape_data.current_scale
        
        # Get current position
        current_pos = self.rect().topLeft()
        
        # Update rectangle size
        self.setRect(current_pos.x(), current_pos.y(), new_width, new_height)
        
        # Update shape data
        self.shape_data.width = new_width
        self.shape_data.height = new_height
        
        # Update control points
        self.update_control_points()
    
    def set_border_color(self, color):
        """Set border color"""
        self.shape_data.border_color = color.name()
        self.setPen(QPen(QColor(color), 2))
    
    def set_fill_color(self, color):
        """Set fill color"""
        self.shape_data.fill_color = color.name()
        self.setBrush(QBrush(QColor(color)))


class EditableTextItem(QGraphicsTextItem):
    """Editable text item with resize handles"""
    def __init__(self, text_data, scene=None):
        super().__init__("Text")
        self.text_data = text_data
        self.scene_ref = scene
        
        # Set initial text and position
        self.setPlainText(text_data.text)
        self.setPos(text_data.x, text_data.y)
        
        # Apply styling from text data
        font = QFont(text_data.font_family, text_data.font_size)
        self.setFont(font)
        self.setDefaultTextColor(QColor(text_data.text_color))
        
        # Enable moving and selection
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsFocusable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        
        # Text editing flag
        self.editing = False
        
        # NEW: Resize control points
        self.control_points = []
        self.resizing = False
        self.resize_handle = None
        
        # NEW: Store original rect for resize calculations
        self.original_rect = QRectF(text_data.x, text_data.y, text_data.width, text_data.height)
        
        # NEW: Create control points (will be created when added to scene)
        self.controls_created = False
    
    def create_control_points(self):
        """Create 8 control points around the text item"""
        if self.controls_created:
            return
            
        rect = self.boundingRect()
        
        # Define 8 handle positions (corners and edges)
        positions = [
            (rect.left(), rect.top()),        # 0: Top-left
            (rect.center().x(), rect.top()),  # 1: Top
            (rect.right(), rect.top()),       # 2: Top-right
            (rect.right(), rect.center().y()), # 3: Right
            (rect.right(), rect.bottom()),    # 4: Bottom-right
            (rect.center().x(), rect.bottom()), # 5: Bottom
            (rect.left(), rect.bottom()),     # 6: Bottom-left
            (rect.left(), rect.center().y())  # 7: Left
        ]
        
        for i, (x, y) in enumerate(positions):
            handle = ResizeHandle(self, i)
            handle.setPos(x, y)
            self.control_points.append(handle)
            # Add to scene if we have a scene reference
            if self.scene():
                self.scene().addItem(handle)
                handle.setParentItem(self)
        
        self.controls_created = True
    
    def update_control_points(self):
        """Update control point positions after text changes"""
        if not self.control_points:
            return
            
        rect = self.boundingRect()
        positions = [
            (rect.left(), rect.top()),
            (rect.center().x(), rect.top()),
            (rect.right(), rect.top()),
            (rect.right(), rect.center().y()),
            (rect.right(), rect.bottom()),
            (rect.center().x(), rect.bottom()),
            (rect.left(), rect.bottom()),
            (rect.left(), rect.center().y())
        ]
        
        for i, handle in enumerate(self.control_points):
            if i < len(positions):
                handle.setPos(positions[i][0], positions[i][1])
    
    def show_control_points(self):
        """Show all control points"""
        if not self.controls_created:
            self.create_control_points()
            
        for handle in self.control_points:
            handle.show()
    
    def hide_control_points(self):
        """Hide all control points"""
        for handle in self.control_points:
            handle.hide()
    
    def resize_shape(self, new_pos, handle_index):
        """Resize text item based on dragged control point"""
        # For text items, we adjust font size based on resize
        current_font = self.font()
        current_size = current_font.pointSize()
        
        if handle_index in [0, 2, 4, 6]:  # Corner handles - scale font
            # Calculate distance from center to determine scale
            center = self.boundingRect().center()
            old_distance = center.manhattanLength()
            new_distance = QPointF(new_pos).manhattanLength()
            
            if old_distance > 0:
                scale_factor = new_distance / old_distance
                new_size = max(8, min(72, int(current_size * scale_factor)))
                current_font.setPointSize(new_size)
                self.setFont(current_font)
                self.text_data.font_size = new_size
        
        # Update text data position
        self.text_data.x = self.pos().x()
        self.text_data.y = self.pos().y()
        
        # Update control points positions
        self.update_control_points()
    
    def itemChange(self, change, value):
        """Handle item changes (like selection)"""
        if change == QGraphicsItem.ItemSelectedChange:
            self.text_data.selected = bool(value)
            if value:  # Selected
                self.show_control_points()
                if not self.editing:
                    self.setFocus(Qt.MouseFocusReason)
                    self.setTextInteractionFlags(Qt.TextEditorInteraction)
                    self.editing = True
            else:  # Deselected
                self.hide_control_points()
                if self.editing:
                    self.setTextInteractionFlags(Qt.NoTextInteraction)
                    self.editing = False
                    # Update text data
                    self.text_data.text = self.toPlainText()
        elif change == QGraphicsItem.ItemPositionHasChanged:
            # Update text data when text moves
            self.text_data.x = self.pos().x()
            self.text_data.y = self.pos().y()
            # Update control points when text moves
            self.update_control_points()
        elif change == QGraphicsItem.ItemSceneHasChanged:
            # Scene has changed, recreate control points if needed
            if value and not self.controls_created:
                self.create_control_points()
        
        return super().itemChange(change, value)
    
    def focusOutEvent(self, event):
        """Handle focus out event"""
        self.text_data.text = self.toPlainText()
        super().focusOutEvent(event)
    
    def set_font_family(self, font_family):
        """Set font family"""
        font = self.font()
        font.setFamily(font_family)
        self.setFont(font)
        self.text_data.font_family = font_family
    
    def set_font_size(self, font_size):
        """Set font size"""
        font = self.font()
        font.setPointSize(font_size)
        self.setFont(font)
        self.text_data.font_size = font_size
    
    def set_text_color(self, color):
        """Set text color"""
        self.setDefaultTextColor(color)
        self.text_data.text_color = color.name()


# =====================================================
# STEP 3: SIMPLE PAGE VIEW DIALOG
# =====================================================
class PageViewDialog(QDialog):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setWindowTitle("Page View")
        self.resize(300, 120)

        layout = QVBoxLayout(self)

        btn_single = QPushButton("📄")
        btn_double = QPushButton("📄📄")

        btn_single.clicked.connect(self.single)
        btn_double.clicked.connect(self.double)

        layout.addWidget(btn_single)
        layout.addWidget(btn_double)

    def single(self):
        self.editor.page_view = "single"
        self.editor.render()
        self.accept()

    def double(self):
        self.editor.page_view = "double"
        self.editor.render()
        self.accept()


# =====================================================
# STEP 4: SIMPLE ADD / REPLACE PAGE DIALOG
# =====================================================
class AddReplaceDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Add / Replace Page")
        self.resize(800, 300)

        layout = QVBoxLayout(self)
        self.table = QTableWidget(1, 5)
        self.table.setHorizontalHeaderLabels(
            ["Page No", "From", "Action", "PDF", "Times"]
        )
        layout.addWidget(self.table)

        self._add_row(0)

        btns = QHBoxLayout()
        add_row = QPushButton("+")
        add_row.clicked.connect(self.add_row)
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        btns.addWidget(add_row)
        btns.addStretch()
        btns.addWidget(ok)
        layout.addLayout(btns)

    def _add_row(self, r):
        self.table.setItem(r, 0, QTableWidgetItem("1"))
        from_box = QComboBox()
        from_box.addItems(["Prev", "On", "Next"])
        self.table.setCellWidget(r, 1, from_box)
        act = QComboBox()
        act.addItems(["Insert", "Replace"])
        self.table.setCellWidget(r, 2, act)
        btn = QPushButton("Browse")
        btn.clicked.connect(lambda: self.select_pdf(r))
        self.table.setCellWidget(r, 3, btn)
        spin = QSpinBox()
        spin.setMinimum(1)
        self.table.setCellWidget(r, 4, spin)

    def add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._add_row(r)

    def select_pdf(self, r):
        path, _ = QFileDialog.getOpenFileName(self, "Select PDF", "", "*.pdf")
        if path:
            self.table.item(r, 0).setData(Qt.UserRole, path)

    def get_data(self):
        rows = []
        for r in range(self.table.rowCount()):
            rows.append({
                "page": int(self.table.item(r, 0).text()) - 1,
                "action": self.table.cellWidget(r, 2).currentText(),
                "pdf": self.table.item(r, 0).data(Qt.UserRole),
                "times": self.table.cellWidget(r, 4).value()
            })
        return rows


# =====================================================
# STEP 5: CUSTOM PAGE LABEL WITH JUMP-TO-PAGE FEATURE
# =====================================================
class PageLabel(QLabel):
    def __init__(self, editor):
        super().__init__("Page 0 / 0")
        self.editor = editor
        self.setStyleSheet("""
            QLabel {
                background-color: #0078d7;
                color: white;
                padding: 8px 15px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #005a9e;
                min-width: 120px;
                text-align: center;
            }
            QLabel:hover {
                background-color: #0088e8;
                cursor: pointer;
            }
        """)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setToolTip("Double-click to jump to specific page")
        
    def mouseDoubleClickEvent(self, event):
        """Show input dialog to jump to specific page"""
        if event.button() == Qt.LeftButton:
            self.editor.show_page_jump_dialog()
        super().mouseDoubleClickEvent(event)


# =====================================================
# STEP 6: MAIN EDITOR WITH INTERACTIVE SHAPES AND TEXT
# =====================================================
class PDFEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AAzPDF Editor with Interactive Shapes & Text")
        self.resize(1400, 900)
        
        # Theme management
        self.dark_mode = True
        
        self.doc = None
        self.original_doc_path = None
        self.page = 0
        self.zoom = 1.0
        self.tool = "select"
        self.page_view = "single"
        
        # Shape storage - store shape DATA for each page (not QGraphicsItems)
        self.page_shapes = {}  # page_num: [list of ShapeData objects]
        self.page_texts = {}   # page_num: [list of TextData objects]
        
        # Store active QGraphicsItems
        self.active_shape_items = []  # List of currently displayed ShapeItem objects
        self.active_text_items = []   # List of currently displayed EditableTextItem objects
        
        # NEW: Store PDF pixmap items separately
        self.pdf_pixmaps = {}  # page_num: QGraphicsPixmapItem
        
        # NEW: Store original PDF for saving
        self.original_pdf_bytes = None
        
        # Setup UI
        self.scene = QGraphicsScene(self)
        self.view = PDFGraphicsView(self)
        self.view.setScene(self.scene)
        self.setCentralWidget(self.view)
        
        # Status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        
        # Custom page label with jump-to-page feature
        self.page_label = PageLabel(self)
        self.build_toolbar()
        
        # Set initial theme
        self.apply_theme()
        self.update_tool_ui()
        
        # Set focus to view for keyboard events
        self.view.setFocus()

    # =================================================
    # STEP 6.1: BUILD TOOLBAR WITH RESIZE CONTROLS AND TEXT TOOLS
    # =================================================
    def build_toolbar(self):
        tb = QToolBar()
        self.addToolBar(tb)

        # File operations
        tb.addAction("📂", self.open_pdf)
        tb.addAction("💾", self.save_pdf)
        tb.addSeparator()

        # Navigation
        tb.addAction("◀ 📄", self.prev_page)
        tb.addAction("📄 ▶", self.next_page)
        tb.addWidget(self.page_label)
        tb.addSeparator()

        # View controls
        tb.addAction("🔍+", lambda: self.zoom_by(1.2))
        tb.addAction("🔍-", lambda: self.zoom_by(0.8))
        tb.addAction("🔄", self.rotate_page)
        tb.addAction("📄 View", self.page_view_dialog)
        tb.addSeparator()

        # Tools
        select_btn = QPushButton("🖱️ Select")
        select_btn.clicked.connect(self.activate_select_tool)
        tb.addWidget(select_btn)
        
        rect_btn = QPushButton("🟦")
        rect_btn.clicked.connect(self.activate_rect_tool)
        tb.addWidget(rect_btn)
        
        # NEW: Text tool
        text_btn = QPushButton("📝 Text")
        text_btn.clicked.connect(self.activate_text_tool)
        tb.addWidget(text_btn)
        
        # NEW: Text font controls
        tb.addSeparator()
        tb.addAction("🔤 Font", self.change_text_font)
        tb.addAction("🎨 Text Color", self.change_text_color)
        tb.addSeparator()
        
        # NEW: Resize controls
        tb.addSeparator()
        tb.addAction("➕ 🟦", self.enlarge_shape)
        tb.addAction("➖ 🟦", self.shrink_shape)
        tb.addSeparator()
        
        # Theme toggle button
        self.theme_btn = QPushButton("🌙")
        self.theme_btn.clicked.connect(self.toggle_theme)
        tb.addWidget(self.theme_btn)
        
        tb.addSeparator()
        tb.addAction("🗑", self.delete_selected)
        tb.addSeparator()

        # Color controls
        tb.addAction("🎨 Fill", self.fill_color)
        tb.addAction("🖊️ Border", self.border_color)
        tb.addSeparator()

        # Page management
        tb.addAction("📄 Add Blank", self.add_blank_page)
        tb.addAction("📋 Add/Replace", self.add_replace_page)

    # =================================================
    # STEP 6.2: THEME MANAGEMENT - FIXED
    # =================================================
    def apply_theme(self):
        """Apply current theme (dark or light)"""
        if self.dark_mode:
            # Dark theme
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #2b2b2b;
                }
                QToolBar {
                    background-color: #353535;
                    border-bottom: 1px solid #555;
                    spacing: 5px;
                    padding: 5px;
                }
                QToolBar QPushButton {
                    background-color: #454545;
                    color: white;
                    border: 1px solid #555;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-size: 11px;
                }
                QToolBar QPushButton:hover {
                    background-color: #505050;
                    border: 1px solid #666;
                }
                QToolBar QPushButton:pressed {
                    background-color: #353535;
                }
                QLabel {
                    color: white;
                    font-weight: bold;
                    padding: 5px;
                }
                QStatusBar {
                    background-color: #353535;
                    color: #aaaaaa;
                    border-top: 1px solid #555;
                }
                QGraphicsView {
                    background-color: #1e1e1e;
                    border: none;
                }
                QDialog {
                    background-color: #353535;
                    color: white;
                }
                QTableWidget {
                    background-color: #2b2b2b;
                    color: white;
                    gridline-color: #555;
                }
                QHeaderView::section {
                    background-color: #454545;
                    padding: 8px;
                    border: 1px solid #555;
                }
            """)
            self.view.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
            self.theme_btn.setText("🌙 Dark")
            self.statusBar.showMessage("Dark mode enabled")
        else:
            # Light theme
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #f0f0f0;
                }
                QToolBar {
                    background-color: #e0e0e0;
                    border-bottom: 1px solid #ccc;
                    spacing: 5px;
                    padding: 5px;
                }
                QToolBar QPushButton {
                    background-color: #ffffff;
                    color: #333333;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-size: 11px;
                }
                QToolBar QPushButton:hover {
                    background-color: #f5f5f5;
                    border: 1px solid #999;
                }
                QToolBar QPushButton:pressed {
                    background-color: #e0e0e0;
                }
                QLabel {
                    color: #333333;
                    font-weight: bold;
                    padding: 5px;
                }
                QStatusBar {
                    background-color: #e0e0e0;
                    color: #666666;
                    border-top: 1px solid #ccc;
                }
                QGraphicsView {
                    background-color: #f8f8f8;
                    border: none;
                }
                QDialog {
                    background-color: #ffffff;
                    color: #333333;
                }
                QTableWidget {
                    background-color: #ffffff;
                    color: #333333;
                    gridline-color: #ddd;
                }
                QHeaderView::section {
                    background-color: #f0f0f0;
                    padding: 8px;
                    border: 1px solid #ddd;
                }
            """)
            self.view.setBackgroundBrush(QBrush(QColor(248, 248, 248)))
            self.theme_btn.setText("☀️ Light")
            self.statusBar.showMessage("Light mode enabled")
        
        # DON'T re-render when changing theme - just update the background
        # The shapes are already in the scene

    def toggle_theme(self):
        """Toggle between dark and light mode"""
        self.dark_mode = not self.dark_mode
        self.apply_theme()
        # Don't call render() here - it clears the scene!

    # =================================================
    # STEP 6.3: KEYBOARD NAVIGATION
    # =================================================
    def keyPressEvent(self, event):
        try:
            # Arrow keys for page navigation
            if event.key() == Qt.Key_Right or event.key() == Qt.Key_Down:
                self.next_page()
                event.accept()
                return
            elif event.key() == Qt.Key_Left or event.key() == Qt.Key_Up:
                self.prev_page()
                event.accept()
                return
            
            # ESC key to exit shape mode
            elif event.key() == Qt.Key_Escape:
                if self.tool == "rect":
                    self.activate_select_tool()
                    print("ESC pressed: Switched to select mode")
                elif self.tool == "text":
                    self.activate_select_tool()
                    print("ESC pressed: Switched to select mode")
            
            # Resize shortcuts
            elif event.key() == Qt.Key_Plus and event.modifiers() & Qt.ControlModifier:
                self.enlarge_shape()
            elif event.key() == Qt.Key_Minus and event.modifiers() & Qt.ControlModifier:
                self.shrink_shape()
            
            # Delete key
            elif event.key() == Qt.Key_Delete:
                self.delete_selected()
            
            # Home/End keys for navigation
            elif event.key() == Qt.Key_Home:
                self.jump_to_page(1)
            elif event.key() == Qt.Key_End:
                if self.doc:
                    self.jump_to_page(len(self.doc))
            
            # Page Up/Down for navigation
            elif event.key() == Qt.Key_PageUp:
                self.prev_page()
            elif event.key() == Qt.Key_PageDown:
                self.next_page()
            
        except Exception as e:
            print(f"Error handling key press: {e}")
        super().keyPressEvent(event)

    # =================================================
    # STEP 6.4: PAGE JUMP FEATURE
    # =================================================
    def show_page_jump_dialog(self):
        """Show dialog to jump to specific page"""
        if not self.doc:
            self.statusBar.showMessage("Please open a PDF first!")
            return
        
        # Create simple input dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Jump to Page")
        dialog.resize(300, 120)
        
        layout = QVBoxLayout(dialog)
        
        # Instruction label
        instruction = QLabel(f"Enter page number (1 - {len(self.doc)}):")
        instruction.setAlignment(Qt.AlignCenter)
        layout.addWidget(instruction)
        
        # Page number input
        page_input = QSpinBox()
        page_input.setMinimum(1)
        page_input.setMaximum(len(self.doc))
        page_input.setValue(self.page + 1)
        page_input.selectAll()  # Select all text for easy typing
        layout.addWidget(page_input)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        jump_btn = QPushButton("Jump")
        cancel_btn = QPushButton("Cancel")
        
        jump_btn.clicked.connect(lambda: self.jump_to_page(page_input.value()))
        jump_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        
        buttons_layout.addWidget(jump_btn)
        buttons_layout.addWidget(cancel_btn)
        layout.addLayout(buttons_layout)
        
        # Set focus to input field
        page_input.setFocus()
        
        # Show dialog
        if dialog.exec():
            self.statusBar.showMessage(f"Jumped to page {page_input.value()}")

    def jump_to_page(self, page_number):
        """Jump to specific page number"""
        if not self.doc:
            return
        
        # Convert to zero-based index
        page_index = max(0, min(len(self.doc) - 1, page_number - 1))
        
        if page_index != self.page:
            self.page = page_index
            self.render()
            self.statusBar.showMessage(f"Page {self.page + 1} / {len(self.doc)}")

    # =================================================
    # STEP 6.5: SIMPLE TOOL ACTIVATION
    # =================================================
    def activate_select_tool(self):
        try:
            self.tool = "select"
            self.view.setCursor(QCursor(Qt.ArrowCursor))
            self.view.setDragMode(QGraphicsView.RubberBandDrag)
            self.statusBar.showMessage("Selection Tool: Drag to select shapes/text")
            print("SELECT tool activated")
        except Exception as e:
            print(f"Error activating select tool: {e}")
            self.statusBar.showMessage("Error activating tool")

    def activate_rect_tool(self):
        try:
            self.tool = "rect"
            self.view.setCursor(QCursor(Qt.CrossCursor))
            self.view.setDragMode(QGraphicsView.NoDrag)
            self.statusBar.showMessage("Rectangle Tool: Click to add rectangle")
            print("RECTANGLE tool activated")
        except Exception as e:
            print(f"Error activating rect tool: {e}")
            self.statusBar.showMessage("Error activating tool")

    def activate_text_tool(self):
        """Activate text tool"""
        try:
            self.tool = "text"
            self.view.setCursor(QCursor(Qt.IBeamCursor))
            self.view.setDragMode(QGraphicsView.NoDrag)
            self.statusBar.showMessage("Text Tool: Click to add text box")
            print("TEXT tool activated")
        except Exception as e:
            print(f"Error activating text tool: {e}")
            self.statusBar.showMessage("Error activating text tool")

    # =================================================
    # STEP 6.6: FIXED SHAPE CREATION WITH CONTROL POINTS
    # =================================================
    def create_shape_at_position(self, x, y):
        """Create a new shape at the specified position"""
        try:
            if not self.doc or self.tool != "rect":
                return
            
            print(f"Creating shape at: x={x}, y={y}")
            
            # Calculate position for centered shape
            shape_width = 160
            shape_height = 100
            shape_x = x - (shape_width / 2)
            shape_y = y - (shape_height / 2)
            
            # Create shape data (not QGraphicsItem yet)
            shape_data = ShapeData(
                shape_x, shape_y, shape_width, shape_height,
                "#ff0000", "#66ffff", self.page
            )
            
            # Create QGraphicsItem from the data
            shape_item = ShapeItem(shape_data, self.scene)
            
            # Add to scene
            self.scene.addItem(shape_item)
            
            # Store shape data for current page
            if self.page not in self.page_shapes:
                self.page_shapes[self.page] = []
            self.page_shapes[self.page].append(shape_data)
            
            # Add to active items
            self.active_shape_items.append(shape_item)
            
            # Select the new shape (this will trigger creation of control points)
            shape_item.setSelected(True)
            
            # Update status
            self.statusBar.showMessage(f"Rectangle added at ({int(x)}, {int(y)})")
            print(f"Shape created successfully on page {self.page}")
            
        except Exception as e:
            print(f"Error creating shape: {e}")
            import traceback
            traceback.print_exc()
            self.statusBar.showMessage(f"Error creating shape: {str(e)[:50]}")

    def create_text_at_position(self, x, y):
        """Create a new text box at the specified position"""
        try:
            if not self.doc or self.tool != "text":
                return
            
            print(f"Creating text at: x={x}, y={y}")
            
            # Calculate position for text
            text_x = x
            text_y = y
            
            # Create text data
            text_data = TextData(
                text_x, text_y, 200, 50,
                "Double-click to edit text",
                "Arial", 12, "#000000", self.page
            )
            
            # Create QGraphicsItem from the data
            text_item = EditableTextItem(text_data, self.scene)
            
            # Add to scene
            self.scene.addItem(text_item)
            
            # Store text data for current page
            if self.page not in self.page_texts:
                self.page_texts[self.page] = []
            self.page_texts[self.page].append(text_data)
            
            # Add to active items
            self.active_text_items.append(text_item)
            
            # Select the new text (this will trigger creation of control points)
            text_item.setSelected(True)
            
            # Update status
            self.statusBar.showMessage(f"Text box added at ({int(x)}, {int(y)})")
            print(f"Text created successfully on page {self.page}")
            
        except Exception as e:
            print(f"Error creating text: {e}")
            import traceback
            traceback.print_exc()
            self.statusBar.showMessage(f"Error creating text: {str(e)[:50]}")

    # =================================================
    # STEP 6.7: RESIZE FUNCTIONS
    # =================================================
    def enlarge_shape(self):
        """Enlarge selected shapes"""
        selected_shapes = [item for item in self.active_shape_items if item.isSelected()]
        selected_texts = [item for item in self.active_text_items if item.isSelected()]
        
        if not selected_shapes and not selected_texts:
            self.statusBar.showMessage("No items selected")
            return
        
        enlarged_count = 0
        for item in selected_shapes:
            item.resize(1.2)  # Enlarge by 20%
            enlarged_count += 1
        
        for item in selected_texts:
            # For text, increase font size
            current_font = item.font()
            current_size = current_font.pointSize()
            new_size = min(72, int(current_size * 1.2))
            if new_size > current_size:
                current_font.setPointSize(new_size)
                item.setFont(current_font)
                item.text_data.font_size = new_size
                enlarged_count += 1
        
        if enlarged_count > 0:
            self.statusBar.showMessage(f"Enlarged {enlarged_count} item(s)")
            self.scene.update()

    def shrink_shape(self):
        """Shrink selected shapes"""
        selected_shapes = [item for item in self.active_shape_items if item.isSelected()]
        selected_texts = [item for item in self.active_text_items if item.isSelected()]
        
        if not selected_shapes and not selected_texts:
            self.statusBar.showMessage("No items selected")
            return
        
        shrunk_count = 0
        for item in selected_shapes:
            item.resize(0.8)  # Shrink by 20%
            shrunk_count += 1
        
        for item in selected_texts:
            # For text, decrease font size
            current_font = item.font()
            current_size = current_font.pointSize()
            new_size = max(8, int(current_size * 0.8))
            if new_size < current_size:
                current_font.setPointSize(new_size)
                item.setFont(current_font)
                item.text_data.font_size = new_size
                shrunk_count += 1
        
        if shrunk_count > 0:
            self.statusBar.showMessage(f"Shrunk {shrunk_count} item(s)")
            self.scene.update()

    # =================================================
    # STEP 6.8: UPDATE TOOL UI
    # =================================================
    def update_tool_ui(self):
        try:
            if self.tool == "select":
                self.activate_select_tool()
            elif self.tool == "rect":
                self.activate_rect_tool()
            elif self.tool == "text":
                self.activate_text_tool()
        except Exception as e:
            print(f"Error updating tool UI: {e}")

    # =================================================
    # STEP 6.9: DELETE FUNCTION
    # =================================================
    def delete_selected(self):
        """Delete selected shapes/text from current page"""
        try:
            # Get selected items
            selected_shapes = [item for item in self.active_shape_items if item.isSelected()]
            selected_texts = [item for item in self.active_text_items if item.isSelected()]
            
            if not selected_shapes and not selected_texts:
                self.statusBar.showMessage("No items selected")
                return
            
            # Remove shapes from scene and storage
            for item in selected_shapes:
                if item.shape_data in self.page_shapes.get(self.page, []):
                    # Remove control points first
                    for handle in item.control_points:
                        if handle in self.scene.items():
                            self.scene.removeItem(handle)
                    # Remove shape
                    self.scene.removeItem(item)
                    self.page_shapes[self.page].remove(item.shape_data)
                    self.active_shape_items.remove(item)
            
            # Remove texts from scene and storage
            for item in selected_texts:
                if item.text_data in self.page_texts.get(self.page, []):
                    # Remove control points first
                    for handle in item.control_points:
                        if handle in self.scene.items():
                            self.scene.removeItem(handle)
                    # Remove text
                    self.scene.removeItem(item)
                    self.page_texts[self.page].remove(item.text_data)
                    self.active_text_items.remove(item)
                
            total_deleted = len(selected_shapes) + len(selected_texts)
            if total_deleted > 0:
                self.statusBar.showMessage(f"Deleted {total_deleted} item(s)")
                print(f"Deleted {total_deleted} item(s)")
                
        except Exception as e:
            print(f"Error deleting items: {e}")
            self.statusBar.showMessage("Error deleting items")

    # =================================================
    # STEP 6.10: COLOR FUNCTIONS
    # =================================================
    def fill_color(self):
        """Change fill color of selected shapes"""
        try:
            selected_items = [item for item in self.active_shape_items if item.isSelected()]
            if not selected_items:
                self.statusBar.showMessage("No shapes selected")
                return
                
            color = QColorDialog.getColor(initial=QColor("#66ffff"))
            if color.isValid():
                for item in selected_items:
                    item.set_fill_color(color)
                
                self.statusBar.showMessage(f"Fill color changed to {color.name()}")
                self.scene.update()
        except Exception as e:
            print(f"Error changing fill color: {e}")

    def border_color(self):
        """Change border color of selected shapes"""
        try:
            selected_items = [item for item in self.active_shape_items if item.isSelected()]
            if not selected_items:
                self.statusBar.showMessage("No shapes selected")
                return
                
            color = QColorDialog.getColor(initial=QColor("#ff0000"))
            if color.isValid():
                for item in selected_items:
                    item.set_border_color(color)
                
                self.statusBar.showMessage(f"Border color changed to {color.name()}")
                self.scene.update()
        except Exception as e:
            print(f"Error changing border color: {e}")

    def change_text_color(self):
        """Change text color of selected text items"""
        try:
            selected_items = [item for item in self.active_text_items if item.isSelected()]
            if not selected_items:
                self.statusBar.showMessage("No text items selected")
                return
                
            color = QColorDialog.getColor(initial=QColor("#000000"))
            if color.isValid():
                for item in selected_items:
                    item.set_text_color(color)
                
                self.statusBar.showMessage(f"Text color changed to {color.name()}")
                self.scene.update()
        except Exception as e:
            print(f"Error changing text color: {e}")

    def change_text_font(self):
        """Change font of selected text items"""
        try:
            selected_items = [item for item in self.active_text_items if item.isSelected()]
            if not selected_items:
                self.statusBar.showMessage("No text items selected")
                return
                
            font, ok = QFontDialog.getFont()
            if ok:
                for item in selected_items:
                    item.set_font_family(font.family())
                    item.set_font_size(font.pointSize())
                
                self.statusBar.showMessage(f"Font changed to {font.family()} {font.pointSize()}pt")
                self.scene.update()
        except Exception as e:
            print(f"Error changing font: {e}")

    # =================================================
    # STEP 6.11: FIXED PDF SAVE FUNCTION
    # =================================================
    def save_pdf(self):
        """Save PDF with shapes and text drawn on it"""
        try:
            if not self.doc:
                self.statusBar.showMessage("No PDF to save")
                return
            
            # Get save file path
            p, _ = QFileDialog.getSaveFileName(self, "Save PDF", "", "*.pdf")
            if not p:
                return
            
            # Ensure the file has .pdf extension
            if not p.lower().endswith('.pdf'):
                p += '.pdf'
            
            # Save the CURRENT document with all modifications
            self.doc.save(p, garbage=4, deflate=True)
            
            # Now open the saved document and add shapes/text
            saved_doc = fitz.open(p)
            
            # Draw shapes on each page
            for page_num, shapes in self.page_shapes.items():
                if page_num < len(saved_doc):
                    page = saved_doc[page_num]
                    
                    # Draw each shape on the page
                    for shape_data in shapes:
                        # Get page dimensions
                        pdf_height = page.rect.height
                        
                        # Convert Qt coordinates (top-left origin) to PDF coordinates (bottom-left origin)
                        # Apply zoom factor to coordinates
                        pdf_x = shape_data.x / self.zoom
                        pdf_y = pdf_height - (shape_data.y / self.zoom) - (shape_data.height / self.zoom)
                        
                        # Create rectangle
                        rect = fitz.Rect(pdf_x, pdf_y, 
                                        pdf_x + (shape_data.width / self.zoom), 
                                        pdf_y + (shape_data.height / self.zoom))
                        
                        # Parse colors
                        try:
                            fill_color = self.parse_color(shape_data.fill_color)
                            border_color = self.parse_color(shape_data.border_color)
                            
                            # Draw filled rectangle with border
                            page.draw_rect(rect, 
                                         color=border_color, 
                                         fill=fill_color, 
                                         width=2,
                                         overlay=True)
                            
                        except Exception as color_error:
                            print(f"Color error: {color_error}")
                            # Fallback to default colors
                            page.draw_rect(rect, 
                                         color=fitz.utils.getColor("red"), 
                                         fill=fitz.utils.getColor("cyan"), 
                                         width=2,
                                         overlay=True)
            
            # Draw text on each page
            for page_num, texts in self.page_texts.items():
                if page_num < len(saved_doc):
                    page = saved_doc[page_num]
                    
                    # Draw each text on the page
                    for text_data in texts:
                        # Get page dimensions
                        pdf_height = page.rect.height
                        
                        # Convert Qt coordinates (top-left origin) to PDF coordinates (bottom-left origin)
                        # Apply zoom factor to coordinates
                        pdf_x = text_data.x / self.zoom
                        pdf_y = pdf_height - (text_data.y / self.zoom)
                        
                        # Parse color
                        text_color = self.parse_color(text_data.text_color)
                        
                        # Draw text with adjusted font size based on zoom
                        adjusted_font_size = text_data.font_size / self.zoom
                        
                        # Draw text
                        try:
                            # Use fitz font handling
                            page.insert_text(
                                (pdf_x, pdf_y),
                                text_data.text,
                                fontsize=adjusted_font_size,
                                color=text_color,
                                overlay=True
                            )
                        except Exception as text_error:
                            print(f"Text error: {text_error}")
                            # Fallback to simple text drawing
                            page.draw_string(
                                (pdf_x, pdf_y),
                                text_data.text,
                                fontsize=adjusted_font_size,
                                color=text_color
                            )
            
            # Save the document with shapes and text
            saved_doc.save(p, garbage=4, deflate=True)
            saved_doc.close()
            
            self.statusBar.showMessage(f"✅ PDF saved with shapes & text: {os.path.basename(p)}")
            print(f"PDF saved with shapes & text: {p}")
            
        except Exception as e:
            print(f"Error saving PDF with shapes and text: {e}")
            import traceback
            traceback.print_exc()
            self.statusBar.showMessage(f"Error saving PDF: {str(e)[:50]}...")
    
    def parse_color(self, color_string):
        """Parse color string to fitz color tuple"""
        if color_string.startswith('#'):
            # Hex color
            hex_color = color_string.lstrip('#')
            if len(hex_color) == 6:
                r = int(hex_color[0:2], 16) / 255.0
                g = int(hex_color[2:4], 16) / 255.0
                b = int(hex_color[4:6], 16) / 255.0
                return (r, g, b)
        
        # Named colors
        color_map = {
            "red": (1, 0, 0),
            "green": (0, 1, 0),
            "blue": (0, 0, 1),
            "cyan": (0, 1, 1),
            "magenta": (1, 0, 1),
            "yellow": (1, 1, 0),
            "black": (0, 0, 0),
            "white": (1, 1, 1)
        }
        
        return color_map.get(color_string.lower(), (0, 0, 0))  # Default to black

    # =================================================
    # STEP 6.12: OTHER CORE PDF FUNCTIONS
    # =================================================
    def page_view_dialog(self):
        try:
            PageViewDialog(self).exec()
        except Exception as e:
            print(f"Error showing page view dialog: {e}")

    def open_pdf(self):
        try:
            p, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "*.pdf")
            if not p:
                return
            
            # Store original path
            self.original_doc_path = p
            
            # Open the PDF
            self.doc = fitz.open(p)
            self.page = 0
            self.page_shapes.clear()
            self.page_texts.clear()
            self.active_shape_items.clear()
            self.active_text_items.clear()
            self.pdf_pixmaps.clear()  # Clear cached pixmaps
            self.render()
            self.statusBar.showMessage(f"Opened: {os.path.basename(p)}")
            print(f"PDF opened: {p}")
            # Update page label
            self.update_page_label()
        except Exception as e:
            print(f"Error opening PDF: {e}")
            self.statusBar.showMessage(f"Error opening PDF: {str(e)[:50]}...")

    # =================================================
    # STEP 6.13: FIXED RENDER FUNCTION
    # =================================================
    def render(self):
        """Render the current page with shapes and text - FIXED VERSION"""
        try:
            # Clear active items lists
            self.active_shape_items.clear()
            self.active_text_items.clear()
            
            # Clear the scene
            self.scene.clear()
            
            # Clear the pixmap cache
            self.pdf_pixmaps.clear()
            
            if self.doc:
                def draw_page(pno, x_offset=0):
                    try:
                        page = self.doc[pno]
                        pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom))
                        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                        item = QGraphicsPixmapItem(QPixmap.fromImage(img))
                        item.setPos(x_offset, 0)
                        item.setZValue(-1000)  # Put PDF behind shapes/text
                        self.scene.addItem(item)
                        
                        # Store for later removal
                        self.pdf_pixmaps[pno] = item

                        return pix.width
                    except Exception as e:
                        print(f"Error drawing page {pno}: {e}")
                        return 0

                # Draw PDF pages
                if self.page_view == "single":
                    draw_page(self.page)
                    
                    # Add shapes for current page only
                    current_page_shapes = self.page_shapes.get(self.page, [])
                    for shape_data in current_page_shapes:
                        # Only show shapes from the current page
                        if shape_data.page_num == self.page:
                            shape_item = ShapeItem(shape_data, self.scene)
                            self.scene.addItem(shape_item)
                            shape_item.setZValue(100)  # Ensure shapes are above PDF
                            if shape_data.selected:
                                shape_item.setSelected(True)
                            self.active_shape_items.append(shape_item)
                    
                    # Add text for current page only
                    current_page_texts = self.page_texts.get(self.page, [])
                    for text_data in current_page_texts:
                        # Only show text from the current page
                        if text_data.page_num == self.page:
                            text_item = EditableTextItem(text_data, self.scene)
                            self.scene.addItem(text_item)
                            text_item.setZValue(200)  # Ensure text is above shapes
                            if text_data.selected:
                                text_item.setSelected(True)
                            self.active_text_items.append(text_item)
                        
                else:
                    w = draw_page(self.page)
                    if self.page + 1 < len(self.doc):
                        draw_page(self.page + 1, w + 20)
                    
                    # Add shapes for current page (first page in view)
                    current_page_shapes = self.page_shapes.get(self.page, [])
                    for shape_data in current_page_shapes:
                        # Only show shapes from the current page
                        if shape_data.page_num == self.page:
                            shape_item = ShapeItem(shape_data, self.scene)
                            self.scene.addItem(shape_item)
                            shape_item.setZValue(100)  # Ensure shapes are above PDF
                            if shape_data.selected:
                                shape_item.setSelected(True)
                            self.active_shape_items.append(shape_item)
                    
                    # Add text for current page (first page in view)
                    current_page_texts = self.page_texts.get(self.page, [])
                    for text_data in current_page_texts:
                        # Only show text from the current page
                        if text_data.page_num == self.page:
                            text_item = EditableTextItem(text_data, self.scene)
                            self.scene.addItem(text_item)
                            text_item.setZValue(200)  # Ensure text is above shapes
                            if text_data.selected:
                                text_item.setSelected(True)
                            self.active_text_items.append(text_item)
                    
                    # Add shapes for next page (second page in view)
                    if self.page + 1 < len(self.doc):
                        next_page_shapes = self.page_shapes.get(self.page + 1, [])
                        for shape_data in next_page_shapes:
                            # Only show shapes from the next page
                            if shape_data.page_num == self.page + 1:
                                # Adjust position for second page
                                page_width = 0
                                if self.page in self.pdf_pixmaps:
                                    page_width = self.pdf_pixmaps[self.page].pixmap().width()
                                
                                # Create a copy of the shape data for display
                                display_shape_data = ShapeData(
                                    shape_data.x + page_width + 20,
                                    shape_data.y,
                                    shape_data.width,
                                    shape_data.height,
                                    shape_data.border_color,
                                    shape_data.fill_color,
                                    shape_data.page_num
                                )
                                display_shape_data.selected = shape_data.selected
                                
                                shape_item = ShapeItem(display_shape_data, self.scene)
                                self.scene.addItem(shape_item)
                                shape_item.setZValue(100)
                                if shape_data.selected:
                                    shape_item.setSelected(True)
                                self.active_shape_items.append(shape_item)
                        
                        # Add text for next page (second page in view)
                        next_page_texts = self.page_texts.get(self.page + 1, [])
                        for text_data in next_page_texts:
                            # Only show text from the next page
                            if text_data.page_num == self.page + 1:
                                # Adjust position for second page
                                page_width = 0
                                if self.page in self.pdf_pixmaps:
                                    page_width = self.pdf_pixmaps[self.page].pixmap().width()
                                
                                # Create a copy of the text data for display
                                display_text_data = TextData(
                                    text_data.x + page_width + 20,
                                    text_data.y,
                                    text_data.width,
                                    text_data.height,
                                    text_data.text,
                                    text_data.font_family,
                                    text_data.font_size,
                                    text_data.text_color,
                                    text_data.page_num
                                )
                                display_text_data.selected = text_data.selected
                                
                                text_item = EditableTextItem(display_text_data, self.scene)
                                self.scene.addItem(text_item)
                                text_item.setZValue(200)
                                if text_data.selected:
                                    text_item.setSelected(True)
                                self.active_text_items.append(text_item)

            # Update page label
            self.update_page_label()
            
        except Exception as e:
            print(f"Error rendering: {e}")
            import traceback
            traceback.print_exc()

    def update_page_label(self):
        """Update the page label text"""
        if self.doc:
            self.page_label.setText(f"📄 Page {self.page + 1} / {len(self.doc)}")
        else:
            self.page_label.setText("📄 Page 0 / 0")

    def prev_page(self):
        try:
            if self.doc and self.page > 0:
                self.page -= 1
                self.render()
                self.statusBar.showMessage(f"Page {self.page + 1}")
        except Exception as e:
            print(f"Error going to previous page: {e}")

    def next_page(self):
        try:
            if self.doc and self.page < len(self.doc) - 1:
                self.page += 1
                self.render()
                self.statusBar.showMessage(f"Page {self.page + 1}")
        except Exception as e:
            print(f"Error going to next page: {e}")

    def zoom_by(self, factor):
        try:
            self.zoom = max(0.4, min(4.0, self.zoom * factor))
            self.render()
            self.statusBar.showMessage(f"Zoom: {int(self.zoom * 100)}%")
        except Exception as e:
            print(f"Error zooming: {e}")

    def rotate_page(self):
        try:
            if self.doc:
                self.doc[self.page].set_rotation((self.doc[self.page].rotation + 90) % 360)
                self.render()
                self.statusBar.showMessage("Page rotated 90°")
        except Exception as e:
            print(f"Error rotating page: {e}")

    def add_blank_page(self):
        try:
            if self.doc:
                ref = self.doc[self.page]
                self.doc.new_page(pno=self.page + 1, width=ref.rect.width, height=ref.rect.height)
                self.render()
                self.statusBar.showMessage("Blank page added")
        except Exception as e:
            print(f"Error adding blank page: {e}")

    def add_replace_page(self):
        try:
            dlg = AddReplaceDialog()
            if dlg.exec():
                for row in dlg.get_data():
                    src = fitz.open(row["pdf"])
                    for _ in range(row["times"]):
                        if row["action"] == "Insert":
                            self.doc.insert_pdf(src, start_at=row["page"] + 1)
                        else:
                            self.doc.delete_page(row["page"])
                            self.doc.insert_pdf(src, start_at=row["page"])
                self.render()
                self.statusBar.showMessage("Pages added/replaced")
        except Exception as e:
            print(f"Error in add/replace pages: {e}")


# =====================================================
# STEP 7: MAIN APPLICATION
# =====================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set a simple style
    app.setStyle("Fusion")
    
    window = PDFEditor()
    window.show()
    
    sys.exit(app.exec())
