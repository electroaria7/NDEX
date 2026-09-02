from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.branding import NDEX_AUTO_SELECTOR_TITLE

from ndex_common.settings import get_section, update_section
from ndex_common.theme import apply_tk_theme, apply_window_icon, build_app_header, style_text_widget

from ..core.models import AnalysisSummary
from ..services.selector import AutoSelectorService

SETTINGS_SECTION = "auto_selector"


class AutoSelectorApp(tk.Tk):
    def __init__(
        self,
        initial_raw_source=None,
        initial_selected_jpg=None,
        initial_work_folder=None,
        retry_manifest: Path | None = None,
    ):
        super().__init__()
        self._initial_raw_source = initial_raw_source
        self._initial_selected_jpg = initial_selected_jpg
        self._initial_work_folder = initial_work_folder
        self.title(NDEX_AUTO_SELECTOR_TITLE)
        self.geometry("1080x720")
        self.minsize(940, 620)
        self.brand_images: list[tk.PhotoImage] = []
        apply_window_icon(self, self.brand_images)

        self.service = AutoSelectorService()
        self.ui_queue: queue.Queue = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.summary: AnalysisSummary | None = None

        self.raw_source_var = tk.StringVar()
        self.selected_jpg_var = tk.StringVar()
        self.work_folder_var = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=True)
        self.duplicate_var = tk.StringVar(value="rename")
        self.write_xmp_var = tk.BooleanVar(value=True)
        self.xmp_rating_var = tk.StringVar(value="5")
        self.rating_from_jpg_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="원본 CR3 폴더와 셀렉 JPG 폴더를 선택하세요.")
        self.summary_var = tk.StringVar(value="분석 전입니다.")
        self.progress_var = tk.DoubleVar(value=0.0)

        apply_tk_theme(self)
        self._build_ui()
        self._bind_events()
        self._apply_initial_paths()
        self._update_buttons()
        self.after(100, self._process_queue)
        if retry_manifest is not None:
            # Launcher에서 넘어온 job. 여기서 열고, 재실행은 설정이 보이는
            # 이 창에서 사용자가 직접 누른다.
            self.after(150, lambda: self.open_job_results(select=Path(retry_manifest)))

    def _apply_initial_paths(self) -> None:
        stored = get_section(SETTINGS_SECTION)
        if stored.get("last_raw_source"):
            self.raw_source_var.set(stored["last_raw_source"])
        if stored.get("last_selected_jpg"):
            self.selected_jpg_var.set(stored["last_selected_jpg"])
        if stored.get("last_work_folder"):
            self.work_folder_var.set(stored["last_work_folder"])
        if "write_xmp" in stored:
            self.write_xmp_var.set(bool(stored["write_xmp"]))
        if "xmp_rating" in stored:
            self.xmp_rating_var.set(str(stored["xmp_rating"]))
        if "rating_from_jpg" in stored:
            self.rating_from_jpg_var.set(bool(stored["rating_from_jpg"]))
        if stored.get("duplicate_policy"):
            self.duplicate_var.set(stored["duplicate_policy"])

        if self._initial_raw_source:
            self.raw_source_var.set(str(self._initial_raw_source))
        if self._initial_selected_jpg:
            self.selected_jpg_var.set(str(self._initial_selected_jpg))
        if self._initial_work_folder:
            self.work_folder_var.set(str(self._initial_work_folder))
        if self._initial_selected_jpg and not self._initial_raw_source:
            self.status_var.set("셀렉 JPG 폴더가 연동되었습니다. 원본 CR3 폴더를 선택하세요.")

    def _build_ui(self) -> None:
        header = build_app_header(
            self,
            title=NDEX_AUTO_SELECTOR_TITLE,
            tagline="Match selected JPGs to original RAW files",
            holder=self.brand_images,
        )
        header.pack(fill=tk.X)

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))
        left = ttk.Frame(body, padding=16, style="Card.TFrame")
        right = ttk.Frame(body, padding=16, style="Card.TFrame")
        body.add(left, weight=2)
        body.add(right, weight=3)

        left.columnconfigure(1, weight=1)
        self._path_row(left, 0, "원본 RAW 폴더 (CR3/CR2/ARW/NEF)", self.raw_source_var, self._browse_raw_source)
        self._path_row(left, 2, "셀렉 JPG 폴더", self.selected_jpg_var, self._browse_selected_jpg)
        self._path_row(left, 4, "작업용 폴더", self.work_folder_var, self._browse_work_folder)

        ttk.Checkbutton(
            left, text="하위 폴더까지 검색", variable=self.recursive_var, style="Card.TCheckbutton"
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 10))

        ttk.Label(left, text="중복 파일 처리", style="CardSection.TLabel").grid(row=7, column=0, sticky="w")
        ttk.Combobox(
            left,
            textvariable=self.duplicate_var,
            values=["rename", "skip", "overwrite"],
            state="readonly",
        ).grid(row=8, column=0, columnspan=3, sticky="ew", pady=(4, 12))

        ttk.Checkbutton(
            left,
            text="Create XMP sidecar for selected CR3",
            variable=self.write_xmp_var,
            style="Card.TCheckbutton",
        ).grid(row=9, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Label(left, text="XMP rating", style="CardSection.TLabel").grid(row=10, column=0, sticky="w")
        ttk.Combobox(
            left,
            textvariable=self.xmp_rating_var,
            values=["0", "1", "2", "3", "4", "5"],
            state="readonly",
        ).grid(row=11, column=0, columnspan=3, sticky="ew", pady=(4, 8))

        ttk.Checkbutton(
            left,
            text="셀렉 JPG의 별점을 읽어 CR3 XMP에 복사 (없으면 위 값 사용)",
            variable=self.rating_from_jpg_var,
            style="Card.TCheckbutton",
        ).grid(row=12, column=0, columnspan=3, sticky="w", pady=(0, 8))

        buttons = ttk.Frame(left, style="CardInner.TFrame")
        buttons.grid(row=13, column=0, columnspan=3, sticky="ew", pady=(8, 8))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        self.analyze_button = ttk.Button(buttons, text="매칭 분석", command=self.start_analysis)
        self.copy_button = ttk.Button(
            buttons, text="CR3 복제 시작", style="Accent.TButton", command=self.start_copy
        )
        self.analyze_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.copy_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Button(buttons, text="작업 결과...", command=self.open_job_results).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )

        ttk.Progressbar(left, variable=self.progress_var, maximum=100).grid(
            row=14, column=0, columnspan=3, sticky="ew", pady=(14, 6)
        )
        ttk.Label(left, textvariable=self.status_var, style="CardMuted.TLabel", wraplength=330).grid(
            row=15, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(left, textvariable=self.summary_var, style="Card.TLabel", justify="left").grid(
            row=16, column=0, columnspan=3, sticky="w", pady=(18, 0)
        )

        right.rowconfigure(1, weight=3)
        right.rowconfigure(3, weight=2)
        right.columnconfigure(0, weight=1)
        ttk.Label(right, text="매칭 결과", style="CardSection.TLabel").grid(row=0, column=0, sticky="w")
        columns = ("jpg", "cr3", "status")
        self.match_tree = ttk.Treeview(right, columns=columns, show="headings", height=14)
        self.match_tree.grid(row=1, column=0, sticky="nsew", pady=(6, 10))
        self.match_tree.heading("jpg", text="Selected JPG")
        self.match_tree.heading("cr3", text="Matched CR3")
        self.match_tree.heading("status", text="Status")
        self.match_tree.column("jpg", width=220, anchor="w")
        self.match_tree.column("cr3", width=260, anchor="w")
        self.match_tree.column("status", width=100, anchor="w")
        match_scroll = ttk.Scrollbar(right, orient="vertical", command=self.match_tree.yview)
        match_scroll.grid(row=1, column=1, sticky="ns", pady=(6, 10))
        self.match_tree.configure(yscrollcommand=match_scroll.set)

        ttk.Label(right, text="로그", style="CardSection.TLabel").grid(row=2, column=0, sticky="w")
        self.log_text = tk.Text(right, height=9, wrap="word")
        style_text_widget(self.log_text)
        self.log_text.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
        log_scroll = ttk.Scrollbar(right, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=3, column=1, sticky="ns", pady=(6, 0))
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def _path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w")
        ttk.Entry(parent, textvariable=variable).grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        ttk.Button(parent, text="찾기", command=command).grid(row=row + 1, column=2, sticky="ew", padx=(8, 0), pady=(4, 8))

    def _bind_events(self) -> None:
        for variable in (self.raw_source_var, self.selected_jpg_var, self.work_folder_var):
            variable.trace_add("write", lambda *_: self._update_buttons())

    def _browse_raw_source(self) -> None:
        selected = filedialog.askdirectory(title="원본 CR3 폴더 선택")
        if selected:
            self.raw_source_var.set(selected)

    def _browse_selected_jpg(self) -> None:
        selected = filedialog.askdirectory(title="셀렉 JPG 폴더 선택")
        if selected:
            self.selected_jpg_var.set(selected)

    def _browse_work_folder(self) -> None:
        selected = filedialog.askdirectory(title="작업용 폴더 선택")
        if selected:
            self.work_folder_var.set(selected)

    def open_job_results(self, select: Path | None = None) -> None:
        """추출 job이 실제로 복제/건너뜀/실패한 내역을 보여준다."""
        from ndex_common.report_dialog import open_job_reports

        open_job_reports(
            self,
            title=NDEX_AUTO_SELECTOR_TITLE,
            apps=("auto_selector",),
            retry=self._retry_extract,
            select=select,
        )

    def _retry_extract(self, plan) -> None:
        """실패/누락/중복이었던 JPG만 다시 추출한다.

        폴더는 그 작업의 manifest에서 가져온다. 지금 창에 떠 있는 폴더가
        그때와 다를 수 있기 때문이다.
        """
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo(NDEX_AUTO_SELECTOR_TITLE, "실행 중인 작업이 끝난 뒤 다시 시도하세요.")
            return

        selected_jpg = plan.report.source
        work_folder = plan.report.destination
        # 원본 폴더는 manifest의 folders에 있다. 그 전 manifest에는 없으니
        # 그때는 창에 있는 값을 쓴다.
        raw_source = str(plan.report.folders.get("raw_source") or "").strip()
        raw_source = raw_source or self.raw_source_var.get().strip()

        for label, folder in (("원본 CR3", raw_source), ("셀렉 JPG", selected_jpg)):
            if not folder or not Path(folder).is_dir():
                messagebox.showerror("폴더 없음", f"그 작업의 {label} 폴더를 찾을 수 없습니다: {folder}")
                return
        if not work_folder:
            messagebox.showerror("폴더 없음", "그 작업의 작업용 폴더가 기록되어 있지 않습니다.")
            return

        options = self._copy_options()
        # The original run decided which folders were searched. Using the
        # checkbox as it stands now could drop JPGs the job found.
        options["recursive"] = bool(plan.report.context.get("recursive", True))
        self._set_busy(True)
        self.progress_var.set(0)
        self.status_var.set(f"실패 {len(plan.paths)}개 다시 복제 중...")
        self._log(f"재실행 시작: {len(plan.paths)}개")
        job = {
            "selected_jpg": selected_jpg,
            "raw_source": raw_source,
            "work_folder": work_folder,
            "options": options,
            "plan": plan,
        }
        self.worker_thread = threading.Thread(target=self._retry_worker, args=(job,), daemon=True)
        self.worker_thread.start()

    def _retry_worker(self, job: dict) -> None:
        plan, options = job["plan"], job["options"]
        selected_jpg, raw_source, work_folder = job["selected_jpg"], job["raw_source"], job["work_folder"]
        try:
            # 다시 분석해야 한다. 사용자가 그 사이 빠진 CR3를 넣었거나
            # 중복을 정리했을 수 있고, 그것이 재실행의 이유다.
            summary = self.service.analyze(
                Path(raw_source), Path(selected_jpg), recursive=options["recursive"]
            )
            matches, dropped = self.service.matches_for(summary.matches, list(plan.paths))
            result = self._copy(matches, Path(work_folder), options)
            # A JPG the analysis no longer lists would otherwise vanish from
            # the record. Count it as missing so the manifest says so.
            self.service.note_missing(result, dropped, "not in the selected JPG folder")
            self.ui_queue.put(("copy_done", result, job))
        except Exception as exc:
            self.ui_queue.put(("error", str(exc)))

    def start_analysis(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return
        raw_source = self.raw_source_var.get().strip()
        selected_jpg = self.selected_jpg_var.get().strip()
        if not raw_source or not selected_jpg:
            messagebox.showwarning("폴더 필요", "원본 CR3 폴더와 셀렉 JPG 폴더를 선택하세요.")
            return
        self._set_busy(True)
        self.progress_var.set(0)
        self.status_var.set("매칭 분석 중...")
        self._clear_matches()
        self._log("분석 시작")
        self.worker_thread = threading.Thread(
            target=self._analysis_worker,
            args=(Path(raw_source), Path(selected_jpg), self.recursive_var.get()),
            daemon=True,
        )
        self.worker_thread.start()

    def _analysis_worker(self, raw_source: Path, selected_jpg: Path, recursive: bool) -> None:
        try:
            summary = self.service.analyze(raw_source, selected_jpg, recursive=recursive)
            self.ui_queue.put(("analysis_done", summary))
        except Exception as exc:
            self.ui_queue.put(("error", str(exc)))

    def _copy_options(self) -> dict:
        """What a copy run needs from the form, read on the UI thread."""
        try:
            rating = int(self.xmp_rating_var.get())
        except (TypeError, ValueError):
            rating = 5
        return {
            "duplicate_policy": self.duplicate_var.get(),
            "recursive": self.recursive_var.get(),
            "write_xmp": self.write_xmp_var.get(),
            "xmp_rating": rating,
            "rating_from_jpg": self.rating_from_jpg_var.get(),
        }

    def _save_settings(self) -> None:
        rating = self._copy_options()["xmp_rating"]
        try:
            update_section(
                SETTINGS_SECTION,
                {
                    "last_raw_source": self.raw_source_var.get().strip(),
                    "last_selected_jpg": self.selected_jpg_var.get().strip(),
                    "last_work_folder": self.work_folder_var.get().strip(),
                    "write_xmp": self.write_xmp_var.get(),
                    "xmp_rating": rating,
                    "rating_from_jpg": self.rating_from_jpg_var.get(),
                    "duplicate_policy": self.duplicate_var.get(),
                },
            )
            from ndex_common.session import remember

            remember(
                "auto_selector",
                folders={
                    "selected_jpg": self.selected_jpg_var.get().strip(),
                    "raw_source": self.raw_source_var.get().strip(),
                    "work": self.work_folder_var.get().strip(),
                },
            )
        except OSError:
            pass

    def start_copy(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return
        if self.summary is None:
            messagebox.showwarning("분석 필요", "먼저 매칭 분석을 실행하세요.")
            return
        work_folder = self.work_folder_var.get().strip()
        if not work_folder:
            messagebox.showwarning("작업 폴더 필요", "CR3 파일을 복제할 작업용 폴더를 선택하세요.")
            return
        self._save_settings()
        # Fixed now, not read when the job ends: the form can change while
        # the copy runs, and the manifest must say what the job used.
        job = {
            "selected_jpg": str(self.summary.selected_jpg_dir),
            "raw_source": str(self.summary.raw_source_dir),
            "work_folder": work_folder,
            "options": self._copy_options(),
            "plan": None,
        }
        self._set_busy(True)
        self.progress_var.set(0)
        self.status_var.set("CR3 복제 중...")
        self._log("복제 시작")
        self.worker_thread = threading.Thread(target=self._copy_worker, args=(job,), daemon=True)
        self.worker_thread.start()

    def _copy_worker(self, job: dict) -> None:
        try:
            assert self.summary is not None
            result = self._copy(self.summary.matches, Path(job["work_folder"]), job["options"])
            self.ui_queue.put(("copy_done", result, job))
        except Exception as exc:
            self.ui_queue.put(("error", str(exc)))

    def _copy(self, matches, work_folder: Path, options: dict):
        return self.service.copy_matches(
            matches,
            work_folder,
            options["duplicate_policy"],
            write_xmp=options["write_xmp"],
            xmp_rating=options["xmp_rating"],
            rating_from_jpg=options["rating_from_jpg"],
            progress_callback=lambda current, total, name: self.ui_queue.put(
                ("progress", current, total, name)
            ),
        )

    def _process_queue(self) -> None:
        try:
            while True:
                event = self.ui_queue.get_nowait()
                kind = event[0]
                if kind == "analysis_done":
                    self._handle_analysis_done(event[1])
                elif kind == "copy_done":
                    _, result, job = event
                    self._handle_copy_done(result, job)
                elif kind == "progress":
                    _, current, total, name = event
                    self.progress_var.set((current / total) * 100 if total else 0)
                    self.status_var.set(f"복제 중: {current}/{total} {name}")
                elif kind == "error":
                    self._handle_error(event[1])
        except queue.Empty:
            pass
        self.after(100, self._process_queue)

    def _handle_analysis_done(self, summary: AnalysisSummary) -> None:
        self.summary = summary
        self._render_summary()
        self._render_matches()
        self.progress_var.set(100)
        self.status_var.set("매칭 분석 완료")
        self._log(f"분석 완료: JPG {summary.selected_count}, 매칭 {summary.matched_count}, 누락 {summary.missing_count}")
        self._set_busy(False)

    def _handle_copy_done(self, result, job: dict) -> None:
        """``job`` is what the run was started with; ``job["plan"]`` marks a retry."""
        self.progress_var.set(100)
        self.status_var.set("CR3 복제 완료")
        self._log(
            f"복제 완료: copied={result.copied}, xmp={result.xmp_written}, skipped={result.skipped}, "
            f"overwritten={result.overwritten}, ambiguous={result.ambiguous}, "
            f"missing={result.missing}, errors={result.errors}"
        )
        for message in result.messages[:80]:
            self._log(message)
        if len(result.messages) > 80:
            self._log(f"... 추가 메시지 {len(result.messages) - 80}개 생략")
        from ndex_common.workflow import record_extract

        plan = job["plan"]
        record_extract(
            job["selected_jpg"],
            job["raw_source"],
            job["work_folder"],
            result,
            recursive=job["options"]["recursive"],
            context=plan.context() if plan is not None else None,
        )
        self._set_busy(False)

    def _handle_error(self, message: str) -> None:
        self.status_var.set("작업 실패")
        self._log(f"오류: {message}")
        self._set_busy(False)
        messagebox.showerror("오류", message)

    def _render_summary(self) -> None:
        if self.summary is None:
            self.summary_var.set("분석 전입니다.")
            return
        self.summary_var.set(
            "요약\n"
            f"Selected JPG: {self.summary.selected_count}\n"
            f"Matched CR3: {self.summary.matched_count}\n"
            f"Ambiguous: {self.summary.ambiguous_count}\n"
            f"Missing CR3: {self.summary.missing_count}"
        )

    def _render_matches(self) -> None:
        self._clear_matches()
        if self.summary is None:
            return
        for match in self.summary.matches:
            self.match_tree.insert(
                "",
                tk.END,
                values=(
                    match.jpg_path.name,
                    match.raw_path.name if match.raw_path else "",
                    match.status,
                ),
            )

    def _clear_matches(self) -> None:
        for item_id in self.match_tree.get_children():
            self.match_tree.delete(item_id)

    def _log(self, message: str) -> None:
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def _set_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        self.analyze_button.configure(state=state)
        self.copy_button.configure(state=state if busy else (tk.NORMAL if self._can_copy() else tk.DISABLED))

    def _update_buttons(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return
        self.analyze_button.configure(state=tk.NORMAL if self._can_analyze() else tk.DISABLED)
        self.copy_button.configure(state=tk.NORMAL if self._can_copy() else tk.DISABLED)

    def _can_analyze(self) -> bool:
        return bool(self.raw_source_var.get().strip() and self.selected_jpg_var.get().strip())

    def _can_copy(self) -> bool:
        return self.summary is not None and bool(self.work_folder_var.get().strip())


def run_app(
    initial_raw_source=None,
    initial_selected_jpg=None,
    initial_work_folder=None,
    retry_manifest: Path | None = None,
) -> None:
    app = AutoSelectorApp(
        initial_raw_source=initial_raw_source,
        initial_selected_jpg=initial_selected_jpg,
        initial_work_folder=initial_work_folder,
        retry_manifest=retry_manifest,
    )
    app.mainloop()
