import datetime
import os
import queue
import shutil
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, scrolledtext


def resource_path(relative_path: str) -> str:
    """Return bundled resource path when running from PyInstaller."""
    base_path = getattr(sys, "_MEIPASS", None)
    if base_path is None:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


from md_to_word import convert_md_directory
from run_pipeline import (
    BATCH_COUNT_DEFAULT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_POLL_TIMEOUT,
    MAX_PAGE_DEFAULT,
    MAX_SIZE_MB_DEFAULT,
    PipelineAborted,
    cleanup_on_abort,
    cleanup_temp_dirs,
    cleanup_temp_files,
    merge_full_md,
    organize_pdf_files,
    process_batch_files,
    resolve_token,
)

APP_VERSION = "v1.5.0"


class GuiLogger:
    def __init__(self, queue):
        self.queue = queue
        self._buffer = ""

    def _format_line(self, line: str) -> str:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{ts}] {line}"

    def write(self, text):
        if text is None:
            return

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if not text:
            return

        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self.queue.put(self._format_line(line) + "\n")

    def flush(self):
        if self._buffer:
            self.queue.put(self._format_line(self._buffer))
            self._buffer = ""


class App:

    def __init__(self, root):
        self.root = root
        self.root.title("PDF批量OCR工具（外网版）")
        self.root.geometry("760x560")
        self.root.resizable(False, False)

        try:
            icon_path = resource_path("mineru_icon.png")
            if os.path.exists(icon_path):
                icon_image = tk.PhotoImage(file=icon_path)
                self.root.iconphoto(False, icon_image)
        except Exception:
            pass

        self.token_var = tk.StringVar()
        self.folder_var = tk.StringVar()
        self.batch_size_var = tk.IntVar(value=BATCH_COUNT_DEFAULT)
        self.max_page_var = tk.IntVar(value=MAX_PAGE_DEFAULT)
        self.max_size_mb_var = tk.IntVar(value=MAX_SIZE_MB_DEFAULT)
        self.poll_interval_var = tk.IntVar(value=DEFAULT_POLL_INTERVAL)
        self.poll_timeout_var = tk.IntVar(value=DEFAULT_POLL_TIMEOUT)
        self.extract_images_var = tk.BooleanVar(value=False)
        self.recognize_images_var = tk.BooleanVar(value=False)
        self.export_word_var = tk.BooleanVar(value=False)
        self.recursive_var = tk.BooleanVar(value=False)

        self.log_queue = queue.Queue()
        self.worker_thread = None
        self.stop_event = threading.Event()

        self.create_menu()
        self.create_widgets()
        self.root.after(100, self.flush_log_queue)

    def create_widgets(self):
        main_frame = tk.Frame(self.root, padx=14, pady=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        control_frame = tk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(4, 10))

        input_frame = tk.LabelFrame(control_frame, text="输入信息", padx=12, pady=12, font=("微软雅黑", 10, "bold"))
        input_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(input_frame, text="Token:", width=12, anchor=tk.W).grid(row=0, column=0, sticky=tk.W)
        tk.Entry(input_frame, textvariable=self.token_var, width=48).grid(row=0, column=1, columnspan=2, sticky=tk.W, padx=(0, 8))
        token_link = tk.Label(input_frame, text="获取 Token", fg="blue", cursor="hand2")
        token_link.grid(row=0, column=3, sticky=tk.W)
        token_link.bind("<Button-1>", lambda e: webbrowser.open_new("https://mineru.net/apiManage/token"))

        tk.Label(input_frame, text="PDF 源目录:", width=12, anchor=tk.W).grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        tk.Entry(input_frame, textvariable=self.folder_var, width=48).grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=(0, 8), pady=(6, 0))
        tk.Button(input_frame, text="浏览", width=10, command=self.choose_folder).grid(row=1, column=3, sticky=tk.W, pady=(6, 0))

        button_frame = tk.Frame(control_frame, padx=12, pady=16)
        button_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.start_button = tk.Button(button_frame, text="开始处理", width=8, height=2, command=self.on_start, bg="#2E8B57", fg="white", font=("微软雅黑", 11, "bold"))
        self.start_button.pack()
        self.stop_button = tk.Button(button_frame, text="中止", width=8, height=2, command=self.on_stop, bg="#B22222", fg="white", font=("微软雅黑", 11, "bold"), state=tk.DISABLED)
        self.stop_button.pack(pady=(8, 0))

        log_frame = tk.LabelFrame(main_frame, text="处理日志", padx=12, pady=12, font=("微软雅黑", 10, "bold"))
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 10), undo=True)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def create_menu(self):
        menu_bar = tk.Menu(self.root)
        settings_menu = tk.Menu(menu_bar, tearoff=0)
        settings_menu.add_command(label="设置", command=self.open_settings)
        menu_bar.add_cascade(label="设置", menu=settings_menu)

        about_menu = tk.Menu(menu_bar, tearoff=0)
        about_menu.add_command(label="关于", command=self.show_about)
        menu_bar.add_cascade(label="关于", menu=about_menu)

        self.root.config(menu=menu_bar)

    def choose_folder(self):
        folder = filedialog.askdirectory(title="选择PDF根目录")
        if folder:
            self.folder_var.set(folder)

    def open_settings(self):
        settings_window = tk.Toplevel(self.root)
        settings_window.title("设置")
        settings_window.geometry("420x450")
        settings_window.resizable(False, False)

        frame = tk.Frame(settings_window, padx=12, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="文件数量:").grid(row=0, column=0, sticky=tk.W, pady=(4, 0))
        tk.Entry(frame, textvariable=self.batch_size_var, width=12).grid(row=0, column=1, sticky=tk.W, pady=(4, 0))

        tk.Label(frame, text="最大页数:").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        tk.Entry(frame, textvariable=self.max_page_var, width=12).grid(row=1, column=1, sticky=tk.W, pady=(8, 0))

        tk.Label(frame, text="最大大小(MB):").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        tk.Entry(frame, textvariable=self.max_size_mb_var, width=12).grid(row=2, column=1, sticky=tk.W, pady=(8, 0))

        tk.Label(frame, text="轮询间隔(秒):").grid(row=3, column=0, sticky=tk.W, pady=(8, 0))
        tk.Entry(frame, textvariable=self.poll_interval_var, width=12).grid(row=3, column=1, sticky=tk.W, pady=(8, 0))

        tk.Label(frame, text="轮询超时(秒):").grid(row=4, column=0, sticky=tk.W, pady=(8, 0))
        tk.Entry(frame, textvariable=self.poll_timeout_var, width=12).grid(row=4, column=1, sticky=tk.W, pady=(8, 0))

        tk.Checkbutton(frame, text="提取图片（存放到 assets 目录）", variable=self.extract_images_var).grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(14, 0))

        tk.Checkbutton(frame, text="识别目录下的图片文件", variable=self.recognize_images_var).grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))

        tk.Checkbutton(frame, text="将 MD 转换为 Word 文档（.docx）", variable=self.export_word_var).grid(row=7, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))

        tk.Checkbutton(frame, text="递归处理子文件夹（默认仅扫描当前目录）", variable=self.recursive_var).grid(row=8, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))

        tk.Button(frame, text="保存", width=12, command=settings_window.destroy).grid(row=9, column=0, columnspan=2, pady=(16, 0))

    def show_about(self):
        messagebox.showinfo(
            "关于",
            f"版本信息: {APP_VERSION}\nCopyright @ 2026 广东电网审计中心 All Rights Reserved.\n技术支持：数智审计部 455509712@qq.com",
        )

    def on_start(self):
        token = resolve_token(self.token_var.get().strip())
        folder = self.folder_var.get().strip()
        batch_size = self.batch_size_var.get()
        max_page = self.max_page_var.get()
        max_size_mb = self.max_size_mb_var.get()
        poll_interval = self.poll_interval_var.get()
        poll_timeout = self.poll_timeout_var.get()
        extract_images = self.extract_images_var.get()
        recognize_images = self.recognize_images_var.get()
        export_word = self.export_word_var.get()
        recursive = self.recursive_var.get()

        if not token:
            messagebox.showwarning("缺少Token", "请先输入 Mineru Token。")
            return
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("目录错误", "请选择有效的PDF源目录。")
            return
        if batch_size <= 0:
            messagebox.showwarning("批次大小错误", "批次大小必须大于0。")
            return
        if max_page <= 0 or max_size_mb <= 0:
            messagebox.showwarning("拆分参数错误", "最大页数和最大大小必须大于0。")
            return
        if poll_interval <= 0 or poll_timeout <= 0:
            messagebox.showwarning("轮询参数错误", "轮询间隔和超时必须大于0。")
            return

        if self.worker_thread is not None and self.worker_thread.is_alive():
            messagebox.showinfo("请稍候", "上一次任务仍在停止中，请稍候再开始。")
            return

        self.stop_event.clear()
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL, text="中止")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

        self.worker_thread = threading.Thread(
            target=self.run_pipeline,
            args=(token, folder, batch_size, max_page, max_size_mb, poll_interval, poll_timeout, extract_images, recognize_images, export_word, recursive),
            daemon=True,
        )
        self.worker_thread.start()

    def on_stop(self):
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.stop_button.config(state=tk.DISABLED, text="中止")
            return
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        self.stop_button.config(state=tk.DISABLED, text="正在中止…")
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_queue.put(f"[{ts}] [用户操作] 已请求中止，正在停止任务并清理临时文件…\n")

    def reset_buttons(self):
        self.stop_event.clear()
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED, text="中止")

    def flush_log_queue(self):
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, message)
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.root.after(100, self.flush_log_queue)

    def run_pipeline(self, token, folder, batch_size, max_page, max_size_mb, poll_interval, poll_timeout, extract_images, recognize_images, export_word=False, recursive=False):
        stdout_orig = sys.stdout
        stderr_orig = sys.stderr
        sys.stdout = sys.stderr = GuiLogger(self.log_queue)

        valid_pdf_dir = None
        aborted = False

        try:
            valid_pdf_dir, valid_pdf_list = organize_pdf_files(
                folder,
                max_page,
                max_size_mb,
                include_images=recognize_images,
                recursive=recursive,
                stop_event=self.stop_event,
            )
            if not valid_pdf_list:
                print("⚠️ 未找到合规文件，流程结束。")
                return

            batches = [valid_pdf_list[i : i + batch_size] for i in range(0, len(valid_pdf_list), batch_size)]
            print(f"\n共计 {len(valid_pdf_list)} 个合规文件，分为 {len(batches)} 个批次处理。")

            for idx, batch_files in enumerate(batches, start=1):
                if self.stop_event.is_set():
                    raise PipelineAborted("用户请求中止")
                print(f"\n--- 正在处理第 {idx} / {len(batches)} 批次 ---")
                success = process_batch_files(
                    batch_files,
                    valid_pdf_dir,
                    token,
                    poll_interval,
                    poll_timeout,
                    stop_event=self.stop_event,
                )
                if not success:
                    print(f"⚠️ 第 {idx} 批次处理失败，继续处理下一批次")

            output_md_dir = os.path.join(folder, "汇总MD")
            merged_ok = merge_full_md(valid_pdf_dir, output_md_dir, extract_images=extract_images)
            if merged_ok:
                cleanup_temp_files(valid_pdf_dir)
                cleanup_temp_dirs(folder)
                print(f"\n🎯 整体流程执行完毕，最终MD文件保存在：{output_md_dir}")
                if export_word:
                    print("\n--- 开始将 MD 转换为 Word 文档 ---")
                    try:
                        created = convert_md_directory(output_md_dir)
                        if created:
                            print(f"📄 Word 文档已保存在：{output_md_dir}")
                    except Exception as exc:
                        print(f"⚠️ Word 转换失败（不影响已生成的 MD）：{exc}")
            else:
                print("\n⚠️ 未生成合并MD，保留临时文件供排查")
                print(f"请检查临时目录：{valid_pdf_dir}")
        except PipelineAborted:
            aborted = True
            print("\n⛔ 已中止本次处理")
        except Exception as exc:
            print(f"❌ 处理过程出现异常：{exc}")
        finally:
            if aborted:
                try:
                    cleanup_on_abort(folder, valid_pdf_dir)
                except Exception as exc:
                    print(f"⚠️ 清理临时文件失败：{exc}")
            sys.stdout = stdout_orig
            sys.stderr = stderr_orig
            self.reset_buttons()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
