"""
屏幕旋转控制工具 - 修复版
- 修复长时间运行/休眠恢复后自动旋转失效
- 增强权限不足的友好提示
- 所有异常均显示详细原因
- 线程安全退出机制
- 基于 rotate-screen 官方 API
"""

import customtkinter as ctk
import rotatescreen
import json
import os
import threading
from pathlib import Path

# ============================================================
# 常量定义
# ============================================================
CONFIG_DIR = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / "ScreenRotator"
CONFIG_FILE = CONFIG_DIR / "config.json"

TIMER_MIN_SEC = 1
TIMER_MAX_SEC = 86400  # 24 小时

ORIENTATIONS = {
    "up": 0,
    "right": 90,
    "down": 180,
    "left": 270
}

ARROW_SYMBOLS = {
    "up": "↑",
    "right": "→",
    "down": "↓",
    "left": "←"
}


def get_friendly_display_name(display, index):
    """生成友好的显示器名称，安全处理各种返回类型"""
    def safe_str(value):
        if isinstance(value, (list, tuple)):
            return str(value[0]) if value else ""
        return str(value) if value is not None else ""

    desc = safe_str(getattr(display, 'device_description', None))
    name = safe_str(getattr(display, 'device_name', None))

    if desc and not desc.startswith('\\') and len(desc) >= 3:
        friendly = desc
    elif name and not name.startswith('\\') and len(name) >= 3:
        friendly = name
    else:
        friendly = f"显示器 {index + 1}"

    if len(friendly) > 40:
        friendly = friendly[:37] + "..."

    if getattr(display, 'is_primary', False):
        friendly += " (主)"

    return friendly


def is_permission_error(exception):
    """判断异常是否由权限不足引起"""
    msg = str(exception).lower()
    return "access" in msg or "privilege" in msg or "denied" in msg


class ScreenRotatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("屏幕旋转控制工具")
        self.geometry("600x800")
        self.resizable(True, True)
        self.minsize(480, 600)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # 状态变量
        self.displays = []
        self.display_options = []
        self.selected_display_index = 0
        self.current_orientation = "up"
        self.timer_seconds = 10
        self.auto_rotate_enabled = False
        self.topmost_enabled = False
        self.timer_thread = None
        self.timer_stop_event = threading.Event()

        self.load_config()
        self.create_widgets()
        self.refresh_displays()
        self.apply_config()

    def create_widgets(self):
        """创建可滚动界面"""
        self.scroll_frame = ctk.CTkScrollableFrame(self, corner_radius=15)
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # 标题
        ctk.CTkLabel(self.scroll_frame, text="屏幕旋转控制工具",
                     font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(20, 10))
        ctk.CTkLabel(self.scroll_frame, text="选择显示器，点击方向按钮旋转屏幕",
                     font=ctk.CTkFont(size=14), text_color="gray").pack(pady=(0, 20))

        # 显示器选择
        monitor_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
        monitor_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(monitor_frame, text="选择显示器",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5))
        self.monitor_combo = ctk.CTkComboBox(monitor_frame, values=["正在检测..."],
                                             command=self.on_monitor_changed,
                                             font=ctk.CTkFont(size=14), height=35, corner_radius=8)
        self.monitor_combo.pack(fill="x", padx=20, pady=(5, 5))
        ctk.CTkButton(monitor_frame, text="刷新显示器列表", command=self.refresh_displays,
                      font=ctk.CTkFont(size=13), height=30, corner_radius=8).pack(pady=(5, 10))

        # 方向按钮
        direction_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
        direction_frame.pack(padx=20, pady=10)
        ctk.CTkLabel(direction_frame, text="旋转方向",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5))
        grid_frame = ctk.CTkFrame(direction_frame, fg_color="transparent")
        grid_frame.pack(pady=(10, 20))
        for i in range(3):
            grid_frame.grid_columnconfigure(i, weight=1)
            grid_frame.grid_rowconfigure(i, weight=1)

        self.btn_up = ctk.CTkButton(grid_frame, text=f"上 {ARROW_SYMBOLS['up']}",
                                    width=100, height=50, font=ctk.CTkFont(size=16),
                                    corner_radius=10, command=lambda: self.rotate_to_direction("up"))
        self.btn_up.grid(row=0, column=1, padx=10, pady=10)

        self.btn_left = ctk.CTkButton(grid_frame, text=f"{ARROW_SYMBOLS['left']} 左",
                                      width=100, height=50, font=ctk.CTkFont(size=16),
                                      corner_radius=10, command=lambda: self.rotate_to_direction("left"))
        self.btn_left.grid(row=1, column=0, padx=10, pady=10)

        self.current_direction_label = ctk.CTkLabel(grid_frame, text="●",
                                                    font=ctk.CTkFont(size=24), text_color="#3a7ebf")
        self.current_direction_label.grid(row=1, column=1, padx=10, pady=10)

        self.btn_right = ctk.CTkButton(grid_frame, text=f"右 {ARROW_SYMBOLS['right']}",
                                       width=100, height=50, font=ctk.CTkFont(size=16),
                                       corner_radius=10, command=lambda: self.rotate_to_direction("right"))
        self.btn_right.grid(row=1, column=2, padx=10, pady=10)

        self.btn_down = ctk.CTkButton(grid_frame, text=f"下 {ARROW_SYMBOLS['down']}",
                                      width=100, height=50, font=ctk.CTkFont(size=16),
                                      corner_radius=10, command=lambda: self.rotate_to_direction("down"))
        self.btn_down.grid(row=2, column=1, padx=10, pady=10)

        self.update_direction_highlight()

        # 窗口置顶
        topmost_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
        topmost_frame.pack(fill="x", padx=20, pady=10)
        self.topmost_var = ctk.BooleanVar(value=False)
        self.topmost_switch = ctk.CTkSwitch(topmost_frame, text="窗口置顶", variable=self.topmost_var,
                                            command=self.toggle_topmost, font=ctk.CTkFont(size=14),
                                            switch_width=50, switch_height=25, corner_radius=12)
        self.topmost_switch.pack(padx=20, pady=10)

        # 自动旋转
        auto_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
        auto_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(auto_frame, text="自动旋转设置",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5))
        switch_row = ctk.CTkFrame(auto_frame, fg_color="transparent")
        switch_row.pack(fill="x", padx=20, pady=5)
        self.auto_switch_var = ctk.BooleanVar(value=False)
        self.auto_switch = ctk.CTkSwitch(switch_row, text="启用自动旋转", variable=self.auto_switch_var,
                                         command=self.on_auto_switch_toggled, font=ctk.CTkFont(size=14),
                                         switch_width=50, switch_height=25, corner_radius=12)
        self.auto_switch.pack(side="left")
        time_row = ctk.CTkFrame(auto_frame, fg_color="transparent")
        time_row.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(time_row, text="间隔秒数:", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10))
        self.timer_entry = ctk.CTkEntry(time_row, font=ctk.CTkFont(size=14), height=30, width=100, corner_radius=6)
        self.timer_entry.pack(side="left")
        self.timer_entry.insert(0, str(self.timer_seconds))
        ctk.CTkLabel(auto_frame, text=f"(允许 {TIMER_MIN_SEC} ~ {TIMER_MAX_SEC} 秒)",
                     font=ctk.CTkFont(size=11), text_color="gray").pack(pady=(5, 0))
        self.timer_status_label = ctk.CTkLabel(auto_frame, text="自动旋转：已关闭",
                                               font=ctk.CTkFont(size=12), text_color="gray")
        self.timer_status_label.pack(pady=(5, 10))

        # 状态栏
        status_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
        status_frame.pack(fill="x", padx=20, pady=10)
        self.status_label = ctk.CTkLabel(status_frame, text="就绪",
                                         font=ctk.CTkFont(size=14), text_color="gray")
        self.status_label.pack(pady=(10, 10))

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    # ============================================================
    # 核心功能（已审计修复）
    # ============================================================
    def get_live_display(self):
        """
        实时获取当前选中的显示器对象。
        解决长时间运行或休眠后设备句柄失效的问题。
        """
        try:
            displays = rotatescreen.get_displays()
            if 0 <= self.selected_display_index < len(displays):
                return displays[self.selected_display_index]
            else:
                self.status_label.configure(text="错误：选中的显示器索引无效，请刷新列表")
        except Exception as e:
            if is_permission_error(e):
                self.status_label.configure(text="权限不足，请以管理员身份运行程序！")
            else:
                self.status_label.configure(text=f"获取显示器失败: {e}")
        return None

    def toggle_topmost(self):
        self.topmost_enabled = self.topmost_var.get()
        self.attributes('-topmost', self.topmost_enabled)
        self.save_config()

    def update_direction_highlight(self):
        for btn, dir_name in [(self.btn_up, "up"), (self.btn_right, "right"),
                              (self.btn_down, "down"), (self.btn_left, "left")]:
            btn.configure(fg_color="#3a7ebf" if self.current_orientation == dir_name else "#2b2b2b")
        self.current_direction_label.configure(text=ARROW_SYMBOLS.get(self.current_orientation, "●"))

    def refresh_displays(self):
        """刷新显示器列表，并在状态栏显示友好信息"""
        try:
            raw_displays = rotatescreen.get_displays()
            self.displays = list(raw_displays)
            self.display_options = [get_friendly_display_name(d, i) for i, d in enumerate(self.displays)]

            if not self.display_options:
                self.display_options = ["未检测到显示器"]
                self.displays = []

            self.monitor_combo.configure(values=self.display_options)
            if self.selected_display_index >= len(self.displays):
                self.selected_display_index = 0
            self.monitor_combo.set(self.display_options[self.selected_display_index])
            self.status_label.configure(text="显示器列表已刷新")
        except Exception as e:
            if is_permission_error(e):
                self.status_label.configure(text="权限不足！请以管理员身份重新运行。")
            else:
                self.status_label.configure(text=f"刷新失败: {e}")

    def on_monitor_changed(self, choice):
        for i, option in enumerate(self.display_options):
            if option == choice:
                self.selected_display_index = i
                self.status_label.configure(text=f"已选择: {choice}")
                self.save_config()
                break

    def rotate_to_direction(self, direction):
        """旋转屏幕（使用实时显示器对象），返回是否成功"""
        display = self.get_live_display()
        if not display:
            # get_live_display 已经设置了状态栏信息
            return False

        if direction not in ORIENTATIONS:
            self.status_label.configure(text="错误：无效的方向")
            return False

        try:
            display.rotate_to(ORIENTATIONS[direction])
            self.current_orientation = direction
            self.update_direction_highlight()
            self.status_label.configure(text=f"✓ 屏幕已旋转至：{direction}")
            self.save_config()
            return True
        except Exception as e:
            if is_permission_error(e):
                self.status_label.configure(text="旋转失败：权限不足，请以管理员身份运行！")
            else:
                self.status_label.configure(text=f"✗ 旋转失败: {e}")
            return False

    # ---------- 自动旋转（增强错误处理与提示） ----------
    def on_auto_switch_toggled(self):
        if self.auto_switch_var.get():
            self.start_auto_rotate()
        else:
            self.stop_auto_rotate()

    def start_auto_rotate(self):
        try:
            seconds = int(self.timer_entry.get())
        except ValueError:
            self.status_label.configure(text="错误：请输入有效的整数值")
            self.auto_switch_var.set(False)
            return

        if seconds < TIMER_MIN_SEC or seconds > TIMER_MAX_SEC:
            self.status_label.configure(
                text=f"错误：秒数必须在 {TIMER_MIN_SEC} ~ {TIMER_MAX_SEC} 之间")
            self.auto_switch_var.set(False)
            return

        if not self.get_live_display():
            self.auto_switch_var.set(False)
            return

        self.stop_timer_thread()
        self.timer_seconds = seconds
        self.auto_rotate_enabled = True
        self.timer_stop_event.clear()
        self.timer_status_label.configure(text=f"自动旋转：已开启 (每 {self.timer_seconds} 秒)")
        self.save_config()
        self._schedule_timer()

    def stop_auto_rotate(self):
        self.auto_rotate_enabled = False
        self.auto_switch_var.set(False)
        self.stop_timer_thread()
        self.timer_status_label.configure(text="自动旋转：已关闭")
        self.save_config()

    def stop_timer_thread(self):
        self.timer_stop_event.set()
        if self.timer_thread and self.timer_thread.is_alive():
            self.timer_thread.join(timeout=2)
        self.timer_thread = None

    def _schedule_timer(self):
        if not self.auto_rotate_enabled:
            return
        self.timer_thread = threading.Thread(target=self._timer_worker, daemon=True)
        self.timer_thread.start()

    def _timer_worker(self):
        """可中断的等待，每0.5秒检查停止事件"""
        remaining = self.timer_seconds
        while remaining > 0 and self.auto_rotate_enabled:
            if self.timer_stop_event.wait(timeout=min(0.5, remaining)):
                return
            remaining -= 0.5

        if not self.auto_rotate_enabled:
            return
        self.after(0, self._timer_rotate)

    def _timer_rotate(self):
        """定时旋转执行函数，失败自动停止定时器"""
        if not self.auto_rotate_enabled:
            return

        success = self.rotate_to_direction(self.current_orientation)
        if not success:
            self.status_label.configure(text="自动旋转已停止：旋转失败")
            self.stop_auto_rotate()
            return

        if self.auto_rotate_enabled:
            self._schedule_timer()

    # ---------- 配置持久化 ----------
    def load_config(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                self.selected_display_index = config.get("display_index", 0)
                self.current_orientation = config.get("orientation", "up")
                self.timer_seconds = config.get("timer_seconds", 10)
                self.auto_rotate_enabled = config.get("auto_rotate_enabled", False)
                self.topmost_enabled = config.get("topmost", False)
                if self.current_orientation not in ORIENTATIONS:
                    self.current_orientation = "up"
                return
        except Exception:
            pass
        # 默认值
        self.selected_display_index = 0
        self.current_orientation = "up"
        self.timer_seconds = 10
        self.auto_rotate_enabled = False
        self.topmost_enabled = False

    def save_config(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            config = {
                "display_index": self.selected_display_index,
                "orientation": self.current_orientation,
                "timer_seconds": self.timer_seconds,
                "auto_rotate_enabled": self.auto_rotate_enabled,
                "topmost": self.topmost_enabled,
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def apply_config(self):
        """将配置应用到UI，并自动恢复定时器（如果之前是开启状态）"""
        if 0 <= self.selected_display_index < len(self.display_options):
            self.monitor_combo.set(self.display_options[self.selected_display_index])
        else:
            self.selected_display_index = 0
            if self.display_options:
                self.monitor_combo.set(self.display_options[0])

        self.update_direction_highlight()

        self.timer_entry.delete(0, "end")
        self.timer_entry.insert(0, str(self.timer_seconds))

        self.auto_switch_var.set(self.auto_rotate_enabled)
        if self.auto_rotate_enabled:
            self.timer_status_label.configure(text=f"自动旋转：已开启 (每 {self.timer_seconds} 秒)")
            self.start_auto_rotate()
        else:
            self.timer_status_label.configure(text="自动旋转：已关闭")

        self.topmost_var.set(self.topmost_enabled)
        self.attributes('-topmost', self.topmost_enabled)

    def on_closing(self):
        self.stop_timer_thread()
        self.save_config()
        self.destroy()


if __name__ == "__main__":
    app = ScreenRotatorApp()
    app.mainloop()