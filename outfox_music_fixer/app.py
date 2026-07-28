from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .cache import (
    CachedLibrary,
    cache_exists,
    default_cache_path,
    load_library_cache,
    save_library_cache,
)
from .genres import build_genre_index, genre_label, sorted_genre_counts
from .models import Song
from .scanner import GroupFolder, discover_groups, scan_group, scan_groups
from .writer import save_song_metadata


class GroupDiscoveryLoader(QObject):
    progress = pyqtSignal(str)
    loaded = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    def run(self) -> None:
        try:
            self.loaded.emit(discover_groups(self.root, progress=self.progress.emit))
        except Exception as exc:  # noqa: BLE001 - GUI boundary should show scanner failures.
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class GroupScanLoader(QObject):
    progress = pyqtSignal(str)
    loaded = pyqtSignal(str, object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, root: Path, group: GroupFolder) -> None:
        super().__init__()
        self.root = root
        self.group = group

    def run(self) -> None:
        try:
            songs = scan_group(self.root, self.group, progress=self.progress.emit)
            self.loaded.emit(self.group.name, songs)
        except Exception as exc:  # noqa: BLE001 - GUI boundary should show scanner failures.
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class AllGroupsScanLoader(QObject):
    progress = pyqtSignal(str)
    loaded = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, root: Path, groups: tuple[GroupFolder, ...]) -> None:
        super().__init__()
        self.root = root
        self.groups = groups

    def run(self) -> None:
        try:
            songs_by_group: dict[str, list[Song]] = {group.name: [] for group in self.groups}
            for song in scan_groups(self.root, self.groups, progress=self.progress.emit):
                songs_by_group.setdefault(song.group, []).append(song)
            self.loaded.emit(songs_by_group)
        except Exception as exc:  # noqa: BLE001 - GUI boundary should show scanner failures.
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OutFox Music Fixer")
        self.resize(1180, 780)

        self.root_path: Path | None = None
        self.group_folders: dict[str, GroupFolder] = {}
        self.group_order: list[str] = []
        self.songs_by_group: dict[str, tuple[Song, ...]] = {}
        self.current_group: str | None = None
        self.current_genre: str | None = None
        self.current_song: Song | None = None
        self.loader_thread: QThread | None = None
        self.loader_worker: QObject | None = None

        self.open_action = QAction("Open Folder", self)
        self.open_action.triggered.connect(self.choose_folder)

        self.rescan_action = QAction("Rescan Group", self)
        self.rescan_action.setEnabled(False)
        self.rescan_action.triggered.connect(self.rescan_current_group)

        self.scan_all_action = QAction("Scan All Groups", self)
        self.scan_all_action.setEnabled(False)
        self.scan_all_action.triggered.connect(self.scan_all_groups)

        self.read_only_toggle = QCheckBox("Read-only")
        self.read_only_toggle.setChecked(True)
        self.read_only_toggle.setToolTip(
            "Turn off to edit title, artist, and genre for the selected song."
        )
        self.read_only_toggle.stateChanged.connect(self.update_edit_state)

        toolbar = QToolBar("Library")
        toolbar.setMovable(False)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.rescan_action)
        toolbar.addAction(self.scan_all_action)
        toolbar.addSeparator()
        toolbar.addWidget(self.read_only_toggle)
        self.addToolBar(toolbar)

        self.groups_list = QListWidget()
        self.groups_list.currentItemChanged.connect(self.group_selected)

        self.songs_list = QListWidget()
        self.songs_list.currentItemChanged.connect(self.song_selected)

        self.genres_list = QListWidget()
        self.genres_list.currentItemChanged.connect(self.genre_selected)

        self.genre_songs_list = QListWidget()
        self.genre_songs_list.currentItemChanged.connect(self.song_selected)

        self.genre_status_label = QLabel("Run Scan All Groups to build a full genre list.")
        self.genre_status_label.setWordWrap(True)

        self.missing_genre_filter = QCheckBox("Missing genre")
        self.missing_genre_filter.stateChanged.connect(self.populate_songs)

        self.title_field = QLineEdit()
        self.artist_field = QLineEdit()
        self.genre_field = QLineEdit()
        self.bpm_field = QLineEdit()
        self.file_field = QLineEdit()
        self.folder_field = QLineEdit()

        for field in (
            self.title_field,
            self.artist_field,
            self.genre_field,
            self.bpm_field,
            self.file_field,
            self.folder_field,
        ):
            field.setReadOnly(True)

        self.save_button = QPushButton("Save Metadata")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_current_song)

        self.difficulty_table = QTableWidget(0, 5)
        self.difficulty_table.setHorizontalHeaderLabels(
            ["Type", "Difficulty", "Meter", "Name", "Credit"]
        )
        self.difficulty_table.verticalHeader().setVisible(False)
        self.difficulty_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.difficulty_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        fixed_font = QFont("Menlo")
        fixed_font.setStyleHint(QFont.StyleHint.Monospace)

        self.tags_text = QTextEdit()
        self.tags_text.setReadOnly(True)
        self.tags_text.setFont(fixed_font)

        self.warning_text = QTextEdit()
        self.warning_text.setReadOnly(True)
        self.warning_text.setMaximumHeight(86)

        self.activity_log = QPlainTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setMaximumBlockCount(1000)
        self.activity_log.setMaximumHeight(120)
        self.activity_log.setFont(fixed_font)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)

        self.summary_label = QLabel("Open a StepMania/OutFox Songs folder.")
        self.summary_label.setWordWrap(True)

        self.open_button = QPushButton("Open Folder")
        self.open_button.clicked.connect(self.choose_folder)

        central = QWidget()
        central.setLayout(self.build_layout())
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())
        self.update_edit_state()
        QTimer.singleShot(0, self.prompt_load_last_cache)

    def build_layout(self) -> QHBoxLayout:
        browser_tabs = QTabWidget()
        browser_tabs.addTab(self.build_groups_tab(), "Groups")
        browser_tabs.addTab(self.build_genres_tab(), "Genres")

        details_box = self.build_details_box()

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(browser_tabs)
        main_splitter.addWidget(details_box)
        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 3)

        root_layout = QHBoxLayout()
        side = QVBoxLayout()
        side.addWidget(self.summary_label)
        side.addWidget(self.open_button)
        side.addWidget(self.progress_bar)
        side.addWidget(main_splitter)
        side.addWidget(QLabel("Activity"))
        side.addWidget(self.activity_log)

        root_layout.addLayout(side)
        return root_layout

    def build_groups_tab(self) -> QWidget:
        groups_box = QGroupBox("Groups")
        groups_layout = QVBoxLayout()
        groups_layout.addWidget(self.groups_list)
        groups_box.setLayout(groups_layout)

        songs_box = QGroupBox("Songs")
        songs_layout = QVBoxLayout()
        songs_layout.addWidget(self.missing_genre_filter)
        songs_layout.addWidget(self.songs_list)
        songs_box.setLayout(songs_layout)

        lists_splitter = QSplitter(Qt.Orientation.Horizontal)
        lists_splitter.addWidget(groups_box)
        lists_splitter.addWidget(songs_box)
        lists_splitter.setStretchFactor(0, 1)
        lists_splitter.setStretchFactor(1, 2)

        tab = QWidget()
        layout = QHBoxLayout()
        layout.addWidget(lists_splitter)
        tab.setLayout(layout)
        return tab

    def build_genres_tab(self) -> QWidget:
        genres_box = QGroupBox("Genres")
        genres_layout = QVBoxLayout()
        genres_layout.addWidget(self.genre_status_label)
        genres_layout.addWidget(self.genres_list)
        genres_box.setLayout(genres_layout)

        genre_songs_box = QGroupBox("Songs in Genre")
        genre_songs_layout = QVBoxLayout()
        genre_songs_layout.addWidget(self.genre_songs_list)
        genre_songs_box.setLayout(genre_songs_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(genres_box)
        splitter.addWidget(genre_songs_box)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        tab = QWidget()
        layout = QHBoxLayout()
        layout.addWidget(splitter)
        tab.setLayout(layout)
        return tab

    def build_details_box(self) -> QGroupBox:
        details_box = QGroupBox("Selected Song")
        details_layout = QVBoxLayout()

        form = QFormLayout()
        form.addRow("Title", self.title_field)
        form.addRow("Artist", self.artist_field)
        form.addRow("Genre", self.genre_field)
        form.addRow("BPM(s)", self.bpm_field)
        form.addRow("Folder", self.folder_field)
        form.addRow("Stepfile", self.file_field)
        details_layout.addLayout(form)
        details_layout.addWidget(self.save_button)

        details_layout.addWidget(QLabel("Difficulties"))
        details_layout.addWidget(self.difficulty_table)

        metadata_layout = QGridLayout()
        metadata_layout.addWidget(QLabel("Other tags"), 0, 0)
        metadata_layout.addWidget(QLabel("Warnings"), 0, 1)
        metadata_layout.addWidget(self.tags_text, 1, 0)
        metadata_layout.addWidget(self.warning_text, 1, 1)
        metadata_layout.setColumnStretch(0, 2)
        metadata_layout.setColumnStretch(1, 1)
        details_layout.addLayout(metadata_layout)

        details_box.setLayout(details_layout)
        return details_box

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Open StepMania/OutFox Songs Folder",
            str(Path.home()),
        )
        if folder:
            self.discover_library(Path(folder))

    def prompt_load_last_cache(self) -> None:
        if not cache_exists():
            return

        try:
            cached = load_library_cache()
        except Exception as exc:  # noqa: BLE001 - GUI boundary should show cache failures.
            self.append_activity(f"Could not load cache: {exc}")
            return

        result = QMessageBox.question(
            self,
            "Load Cached Library?",
            (
                "Load the last cached library?\n\n"
                f"Folder: {cached.root_path}\n"
                f"Saved: {cached.saved_at or 'unknown'}\n"
                f"Parsed groups: {cached.parsed_group_count}\n"
                f"Songs: {cached.song_count}\n\n"
                "You can still rescan groups after loading the cache."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.apply_cached_library(cached)

    def apply_cached_library(self, cached: CachedLibrary) -> None:
        if self.is_busy():
            return

        self.root_path = cached.root_path
        self.group_folders = dict(cached.group_folders)
        self.group_order = list(cached.group_order)
        self.songs_by_group = dict(cached.songs_by_group)
        self.current_group = None
        self.current_genre = None
        self.groups_list.clear()
        self.songs_list.clear()
        self.genres_list.clear()
        self.genre_songs_list.clear()
        self.clear_song_details()
        self.populate_groups()
        self.populate_genres()
        self.update_summary()
        self.set_busy(False)
        self.append_activity(
            f"Loaded cached library from {default_cache_path()} "
            f"({cached.parsed_group_count} parsed group(s), {cached.song_count} song(s))."
        )
        self.statusBar().showMessage("Loaded cached library", 7000)

    def discover_library(self, root: Path) -> None:
        if self.is_busy():
            QMessageBox.information(self, "Scan running", "A library scan is already running.")
            return

        self.root_path = root
        self.group_folders.clear()
        self.group_order.clear()
        self.songs_by_group.clear()
        self.current_group = None
        self.current_genre = None
        self.activity_log.clear()
        self.groups_list.clear()
        self.songs_list.clear()
        self.genres_list.clear()
        self.genre_songs_list.clear()
        self.clear_song_details()
        self.append_activity(f"Loading groups: {root}")
        self.summary_label.setText("Loading group folders...")
        self.genre_status_label.setText("Run Scan All Groups to build a full genre list.")
        self.statusBar().showMessage(f"Loading groups from {root} ...")

        worker = GroupDiscoveryLoader(root)
        worker.progress.connect(self.append_activity)
        worker.loaded.connect(self.groups_discovered)
        worker.failed.connect(self.operation_failed)
        self.start_worker(worker)

    def groups_discovered(self, groups: tuple[GroupFolder, ...]) -> None:
        self.group_folders = {group.name: group for group in groups}
        self.group_order = [group.name for group in groups]
        self.populate_groups()
        self.update_summary()
        self.append_activity(
            "Select a group to parse it, or use Scan All Groups if you want the full library."
        )
        self.populate_genres()
        self.save_current_cache()
        self.statusBar().showMessage(f"Loaded {len(groups)} group folder(s)", 7000)

    def rescan_current_group(self) -> None:
        if self.current_group is not None:
            self.load_group(self.current_group, force=True)

    def scan_all_groups(self) -> None:
        if self.root_path is None or not self.group_order or self.is_busy():
            return

        self.songs_list.clear()
        self.clear_song_details()
        self.append_activity("Scanning all groups")
        groups = tuple(self.group_folders[name] for name in self.group_order)
        worker = AllGroupsScanLoader(self.root_path, groups)
        worker.progress.connect(self.append_activity)
        worker.loaded.connect(self.all_groups_loaded)
        worker.failed.connect(self.operation_failed)
        self.start_worker(worker)

    def all_groups_loaded(self, songs_by_group: dict[str, list[Song]]) -> None:
        self.songs_by_group = {
            group: tuple(sorted(songs, key=lambda song: song.display_title.casefold()))
            for group, songs in songs_by_group.items()
        }
        self.populate_groups()
        if self.current_group is not None:
            self.populate_songs()
        self.populate_genres()
        self.update_summary()
        index = build_genre_index(self.all_songs())
        genre_count = sum(1 for genre in index if genre)
        missing_count = len(index.get("", ()))
        self.append_activity(
            f"Genre inventory: {genre_count} exact genre value(s), "
            f"{missing_count} missing genre."
        )
        self.append_activity("Finished scanning all groups")
        self.save_current_cache()

    def load_group(self, group_name: str, *, force: bool = False) -> None:
        if self.root_path is None:
            return
        if self.is_busy():
            self.statusBar().showMessage("A scan is already running.", 5000)
            return
        if not force and group_name in self.songs_by_group:
            self.populate_songs()
            return

        group = self.group_folders[group_name]
        self.songs_list.clear()
        self.clear_song_details()
        self.append_activity(f"Parsing group: {group.name}")
        self.summary_label.setText(f"Parsing group: {group.name}")
        worker = GroupScanLoader(self.root_path, group)
        worker.progress.connect(self.append_activity)
        worker.loaded.connect(self.group_loaded)
        worker.failed.connect(self.operation_failed)
        self.start_worker(worker)

    def group_loaded(self, group_name: str, songs: tuple[Song, ...]) -> None:
        self.songs_by_group[group_name] = tuple(
            sorted(songs, key=lambda song: song.display_title.casefold())
        )
        self.populate_groups()
        if self.current_group == group_name:
            self.populate_songs()
        self.populate_genres()
        self.update_summary()
        self.append_activity(f"Loaded {len(songs)} song(s) from {group_name}")
        self.save_current_cache()
        self.statusBar().showMessage(f"Loaded {len(songs)} song(s) from {group_name}", 7000)

    def start_worker(self, worker: QObject) -> None:
        self.set_busy(True)
        self.loader_thread = QThread()
        self.loader_worker = worker
        worker.moveToThread(self.loader_thread)
        self.loader_thread.started.connect(worker.run)  # type: ignore[attr-defined]
        worker.finished.connect(self.loader_thread.quit)  # type: ignore[attr-defined]
        worker.finished.connect(worker.deleteLater)  # type: ignore[attr-defined]
        self.loader_thread.finished.connect(self.loader_thread.deleteLater)
        self.loader_thread.finished.connect(self.loader_finished)
        self.loader_thread.start()

    def operation_failed(self, message: str) -> None:
        self.summary_label.setText("Operation failed.")
        self.append_activity(f"Operation failed: {message}")
        QMessageBox.critical(self, "Operation failed", message)
        self.statusBar().showMessage("Operation failed", 7000)

    def loader_finished(self) -> None:
        self.loader_thread = None
        self.loader_worker = None
        self.set_busy(False)
        self.update_summary()

    def is_busy(self) -> bool:
        return self.loader_thread is not None

    def set_busy(self, busy: bool) -> None:
        self.progress_bar.setVisible(busy)
        self.open_action.setEnabled(not busy)
        self.open_button.setEnabled(not busy)
        self.scan_all_action.setEnabled(not busy and bool(self.group_order))
        self.rescan_action.setEnabled(not busy and self.current_group is not None)
        self.update_edit_state()

    def append_activity(self, message: str) -> None:
        self.activity_log.appendPlainText(message)
        scrollbar = self.activity_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def update_summary(self) -> None:
        if self.root_path is None:
            self.summary_label.setText("Open a StepMania/OutFox Songs folder.")
            return

        parsed_groups = len(self.songs_by_group)
        song_count = sum(len(songs) for songs in self.songs_by_group.values())
        missing_genre = sum(
            1 for songs in self.songs_by_group.values() for song in songs if not song.has_genre
        )
        parse_warnings = sum(
            1 for songs in self.songs_by_group.values() for song in songs if song.parse_errors
        )
        self.summary_label.setText(
            f"{len(self.group_order)} groups loaded, {parsed_groups} parsed, "
            f"{song_count} songs, {missing_genre} missing genre, "
            f"{parse_warnings} parse warnings."
        )

    def save_current_cache(self) -> None:
        if self.root_path is None:
            return
        try:
            path = save_library_cache(
                self.root_path,
                self.group_folders,
                self.group_order,
                self.songs_by_group,
            )
        except Exception as exc:  # noqa: BLE001 - cache failures should not break scanning.
            self.append_activity(f"Could not save cache: {exc}")
            return

        self.append_activity(f"Saved local cache: {path}")

    def populate_groups(self) -> None:
        current_group = self.current_group
        self.groups_list.blockSignals(True)
        self.groups_list.clear()

        selected_row = -1
        for row, group_name in enumerate(self.group_order):
            songs = self.songs_by_group.get(group_name)
            if songs is None:
                label = f"{group_name} (not parsed)"
            else:
                missing = sum(1 for song in songs if not song.has_genre)
                label = f"{group_name} ({missing}/{len(songs)} missing genre)"

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, group_name)
            self.groups_list.addItem(item)
            if group_name == current_group:
                selected_row = row

        if selected_row >= 0:
            self.groups_list.setCurrentRow(selected_row)
        self.groups_list.blockSignals(False)

    def all_songs(self) -> tuple[Song, ...]:
        return tuple(song for songs in self.songs_by_group.values() for song in songs)

    def full_scan_complete(self) -> bool:
        return bool(self.group_order) and all(group in self.songs_by_group for group in self.group_order)

    def populate_genres(
        self,
        select_genre: str | None = None,
        select_song_path: Path | None = None,
    ) -> None:
        if select_genre is None:
            select_genre = self.current_genre

        index = build_genre_index(self.all_songs())
        self.genres_list.blockSignals(True)
        self.genres_list.clear()

        selected_row = -1
        for row, (genre, count) in enumerate(sorted_genre_counts(index)):
            item = QListWidgetItem(f"{genre_label(genre)} ({count})")
            item.setData(Qt.ItemDataRole.UserRole, genre)
            self.genres_list.addItem(item)
            if select_genre is not None and genre == select_genre:
                selected_row = row

        self.genres_list.blockSignals(False)
        self.update_genre_status(index)

        if selected_row >= 0:
            self.genres_list.setCurrentRow(selected_row)
            self.populate_genre_songs(select_song_path=select_song_path)
        else:
            self.current_genre = None
            self.genre_songs_list.blockSignals(True)
            self.genre_songs_list.clear()
            self.genre_songs_list.blockSignals(False)

    def update_genre_status(self, index: dict[str, tuple[Song, ...]]) -> None:
        song_count = sum(len(songs) for songs in index.values())
        genre_count = sum(1 for genre in index if genre)
        missing_count = len(index.get("", ()))

        if not self.group_order:
            self.genre_status_label.setText("Open a Songs folder, then run Scan All Groups.")
        elif self.full_scan_complete():
            self.genre_status_label.setText(
                f"{genre_count} exact genre value(s) from {song_count} song(s); "
                f"{missing_count} missing genre."
            )
        else:
            self.genre_status_label.setText(
                f"Partial genre list from {len(self.songs_by_group)}/{len(self.group_order)} "
                "parsed group(s). Run Scan All Groups for the full library."
            )

    def genre_selected(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None = None,
    ) -> None:
        self.current_genre = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.populate_genre_songs()

    def populate_genre_songs(
        self,
        select_song_path: Path | None = None,
        *_: object,
    ) -> None:
        if select_song_path is None and self.current_song is not None:
            select_song_path = self.current_song.file_path

        self.genre_songs_list.blockSignals(True)
        self.genre_songs_list.clear()
        self.clear_song_details()

        if self.current_genre is None:
            self.genre_songs_list.blockSignals(False)
            return

        index = build_genre_index(self.all_songs())
        songs = index.get(self.current_genre, ())
        selected_row = -1
        for row, song in enumerate(songs):
            item = self.make_song_item(song, include_group=True)
            self.genre_songs_list.addItem(item)
            if select_song_path is not None and song.file_path == select_song_path:
                selected_row = row

        self.genre_songs_list.blockSignals(False)
        if selected_row >= 0:
            self.genre_songs_list.setCurrentRow(selected_row)
        elif self.genre_songs_list.count():
            self.genre_songs_list.setCurrentRow(0)

    def group_selected(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None = None,
    ) -> None:
        self.current_group = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.rescan_action.setEnabled(not self.is_busy() and self.current_group is not None)

        if self.current_group is None:
            self.songs_list.clear()
            self.clear_song_details()
            return

        if self.current_group in self.songs_by_group:
            self.populate_songs()
        else:
            self.load_group(self.current_group)

    def populate_songs(self, select_song_path: Path | None = None, *_: object) -> None:
        if select_song_path is not None and not isinstance(select_song_path, Path):
            select_song_path = None
        if select_song_path is None and self.current_song is not None:
            select_song_path = self.current_song.file_path

        self.songs_list.blockSignals(True)
        self.songs_list.clear()
        self.clear_song_details()
        if self.current_group is None:
            self.songs_list.blockSignals(False)
            return

        songs = self.songs_by_group.get(self.current_group, ())
        if self.missing_genre_filter.isChecked():
            songs = tuple(song for song in songs if not song.has_genre)

        selected_row = -1
        for row, song in enumerate(songs):
            item = self.make_song_item(song)
            self.songs_list.addItem(item)
            if select_song_path is not None and song.file_path == select_song_path:
                selected_row = row

        self.songs_list.blockSignals(False)
        if selected_row >= 0:
            self.songs_list.setCurrentRow(selected_row)
        elif self.songs_list.count():
            self.songs_list.setCurrentRow(0)

    def song_selected(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None = None,
    ) -> None:
        song = current.data(Qt.ItemDataRole.UserRole) if current else None
        if isinstance(song, Song):
            self.show_song(song)
        else:
            self.clear_song_details()

    def make_song_item(self, song: Song, *, include_group: bool = False) -> QListWidgetItem:
        prefix = "!" if song.issue_labels else " "
        artist = f" - {song.artist}" if song.artist else ""
        group = f"{song.group} / " if include_group else ""
        item = QListWidgetItem(f"{prefix} {group}{song.display_title}{artist}")
        item.setData(Qt.ItemDataRole.UserRole, song)
        tooltip_lines = [str(song.file_path)]
        if song.issue_labels:
            tooltip_lines.append(", ".join(song.issue_labels))
        item.setToolTip("\n".join(tooltip_lines))
        return item

    def show_song(self, song: Song) -> None:
        self.current_song = song
        self.title_field.setText(song.title)
        self.artist_field.setText(song.artist)
        self.genre_field.setText(song.genre)
        self.bpm_field.setText(song.bpm_display)
        self.folder_field.setText(str(song.directory))
        self.file_field.setText(f"{song.file_path.name} ({song.file_format})")

        self.difficulty_table.setRowCount(len(song.charts))
        for row, chart in enumerate(song.charts):
            values = [
                chart.stepstype,
                chart.normalized_difficulty,
                chart.meter,
                chart.chart_name or chart.description,
                chart.credit,
            ]
            for column, value in enumerate(values):
                self.difficulty_table.setItem(row, column, QTableWidgetItem(value))
        self.difficulty_table.resizeColumnsToContents()

        tag_lines = []
        for key in sorted(song.tags):
            value = song.tags[key].replace("\n", "\\n")
            if len(value) > 180:
                value = value[:177] + "..."
            tag_lines.append(f"#{key}: {value}")
        self.tags_text.setPlainText("\n".join(tag_lines))

        warnings = list(song.issue_labels)
        warnings.extend(song.parse_errors)
        self.warning_text.setPlainText("\n".join(warnings))
        self.update_edit_state()

    def clear_song_details(self) -> None:
        self.current_song = None
        for field in (
            self.title_field,
            self.artist_field,
            self.genre_field,
            self.bpm_field,
            self.file_field,
            self.folder_field,
        ):
            field.clear()
        self.difficulty_table.setRowCount(0)
        self.tags_text.clear()
        self.warning_text.clear()
        self.update_edit_state()

    def update_edit_state(self, *_: object) -> None:
        editable = (
            not self.read_only_toggle.isChecked()
            and self.current_song is not None
            and not self.is_busy()
        )
        self.title_field.setReadOnly(not editable)
        self.artist_field.setReadOnly(not editable)
        self.genre_field.setReadOnly(not editable)
        self.save_button.setEnabled(editable)

        self.bpm_field.setReadOnly(True)
        self.file_field.setReadOnly(True)
        self.folder_field.setReadOnly(True)

        if editable:
            self.statusBar().showMessage(
                "Read-write mode enabled. Save Metadata writes only the selected simfile.",
                7000,
            )

    def save_current_song(self) -> None:
        if self.current_song is None:
            return
        if self.read_only_toggle.isChecked():
            self.statusBar().showMessage("Read-only mode is enabled.", 5000)
            return

        updates = {
            "TITLE": self.title_field.text(),
            "ARTIST": self.artist_field.text(),
            "GENRE": self.genre_field.text(),
        }
        try:
            updated_song, backup_path = save_song_metadata(self.current_song, updates)
        except Exception as exc:  # noqa: BLE001 - GUI boundary should show write failures.
            self.append_activity(f"Save failed: {exc}")
            QMessageBox.critical(self, "Save failed", str(exc))
            self.statusBar().showMessage("Save failed", 7000)
            return

        if backup_path is None:
            self.statusBar().showMessage("No metadata changes to save.", 5000)
            return

        self.replace_song_in_cache(updated_song)
        self.current_song = updated_song
        self.current_genre = updated_song.genre.strip()
        self.populate_groups()
        self.populate_songs(select_song_path=updated_song.file_path)
        self.populate_genres(
            select_genre=updated_song.genre.strip(),
            select_song_path=updated_song.file_path,
        )
        self.append_activity(f"Saved {updated_song.file_path.name}; backup: {backup_path.name}")
        self.save_current_cache()
        self.statusBar().showMessage(f"Saved metadata for {updated_song.display_title}", 7000)

    def replace_song_in_cache(self, updated_song: Song) -> None:
        songs = list(self.songs_by_group.get(updated_song.group, ()))
        for index, song in enumerate(songs):
            if song.file_path == updated_song.file_path:
                songs[index] = updated_song
                break
        else:
            songs.append(updated_song)
        self.songs_by_group[updated_song.group] = tuple(
            sorted(songs, key=lambda song: song.display_title.casefold())
        )


def run(argv: list[str] | None = None) -> int:
    app = QApplication(argv or [])
    window = MainWindow()
    window.show()
    return app.exec()
