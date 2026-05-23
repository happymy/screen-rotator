"""
屏幕旋转控制工具 - 最终增强版
- 保存/恢复全部设置（显示器、方向、定时器、自动旋转、置顶状态）
- 使用可滚动框架，窗口缩小时自动出现垂直滚动条
- 增大默认窗口高度，避免界面截断
- 修复显示器名称读取错误
- 十字方向按钮、自动旋转复选框、窗口置顶
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
    """生成友好的显示器名称，安全处理属性类型"""
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


class ScreenRotatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # 窗口设置（适当增高，保证默认显示完整）
        self.title("屏幕旋转控制工具")
        self.geometry("600x800")
        self.resizable(True, True)
        self.minsize(480, 600)  # 允许缩小，但会触发滚动条

        # 主题
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # 状态变量
        self.displays = []
        self.display_options = []
        self.selected_display_index = 0
        self.current_orientation = "up"
        self.timer_seconds = 10
        self.auto_rotate_enabled = False
        self.topmost_enabled = False  # 新增：置顶状态
        self.timer_thread = None
        self.timer_stop_event = threading.Event()

        # 加载配置
        self.load_config()

        # 构建 UI
        self.create_widgets()

        # 刷新显示器并应用配置
        self.refresh_displays()
        self.apply_config()

    def create_widgets(self):
        """使用可滚动框架承载所有控件"""
        # 可滚动主框架（自动添加垂直滚动条）
        self.scroll_frame = ctk.CTkScrollableFrame(self, corner_radius=15)
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # ---------- 标题 ----------
        title_label = ctk.CTkLabel(
            self.scroll_frame,
            text="屏幕旋转控制工具",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title_label.pack(pady=(20, 10))

        subtitle_label = ctk.CTkLabel(
            self.scroll_frame,
            text="选择显示器，点击方向按钮旋转屏幕",
            font=ctk.CTkFont(size=14),
            text_color="gray",
        )
        subtitle_label.pack(pady=(0, 20))

        # ---------- 显示器选择 ----------
        monitor_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
        monitor_frame.pack(fill="x", padx=20, pady=10)

        monitor_label = ctk.CTkLabel(
            monitor_frame,
            text="选择显示器",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        monitor_label.pack(pady=(10, 5))

        self.monitor_combo = ctk.CTkComboBox(
            monitor_frame,
            values=["正在检测..."],
            command=self.on_monitor_changed,
            font=ctk.CTkFont(size=14),
            height=35,
            corner_radius=8,
        )
        self.monitor_combo.pack(fill="x", padx=20, pady=(5, 5))

        refresh_btn = ctk.CTkButton(
            monitor_frame,
            text="刷新显示器列表",
            command=self.refresh_displays,
            font=ctk.CTkFont(size=13),
            height=30,
            corner_radius=8,
        )
        refresh_btn.pack(pady=(5, 10))

        # ---------- 十字方向按钮 ----------
        direction_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
        direction_frame.pack(padx=20, pady=10)

        direction_label = ctk.CTkLabel(
            direction_frame,
            text="旋转方向",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        direction_label.pack(pady=(10, 5))

        grid_frame = ctk.CTkFrame(direction_frame, fg_color="transparent")
        grid_frame.pack(pady=(10, 20))

        grid_frame.grid_columnconfigure(0, weight=1)
        grid_frame.grid_columnconfigure(1, weight=1)
        grid_frame.grid_columnconfigure(2, weight=1)
        grid_frame.grid_rowconfigure(0, weight=1)
        grid_frame.grid_rowconfigure(1, weight=1)
        grid_frame.grid_rowconfigure(2, weight=1)

        self.btn_up = ctk.CTkButton(
            grid_frame,
            text=f"上 {ARROW_SYMBOLS['up']}",
            width=100,
            height=50,
            font=ctk.CTkFont(size=16),
            corner_radius=10,
            command=lambda: self.rotate_to_direction("up")
        )
        self.btn_up.grid(row=0, column=1, padx=10, pady=10)

        self.btn_left = ctk.CTkButton(
            grid_frame,
            text=f"{ARROW_SYMBOLS['left']} 左",
            width=100,
            height=50,
            font=ctk.CTkFont(size=16),
            corner_radius=10,
            command=lambda: self.rotate_to_direction("left")
        )
        self.btn_left.grid(row=1, column=0, padx=10, pady=10)

        self.current_direction_label = ctk.CTkLabel(
            grid_frame,
            text="●",
            font=ctk.CTkFont(size=24),
            text_color="#3a7ebf",
        )
        self.current_direction_label.grid(row=1, column=1, padx=10, pady=10)

        self.btn_right = ctk.CTkButton(
            grid_frame,
            text=f"右 {ARROW_SYMBOLS['right']}",
            width=100,
            height=50,
            font=ctk.CTkFont(size=16),
            corner_radius=10,
            command=lambda: self.rotate_to_direction("right")
        )
        self.btn_right.grid(row=1, column=2, padx=10, pady=10)

        self.btn_down = ctk.CTkButton(
            grid_frame,
            text=f"下 {ARROW_SYMBOLS['down']}",
            width=100,
            height=50,
            font=ctk.CTkFont(size=16),
            corner_radius=10,
            command=lambda: self.rotate_to_direction("down")
        )
        self.btn_down.grid(row=2, column=1, padx=10, pady=10)

        self.update_direction_highlight()

        # ---------- 窗口置顶开关 ----------
        topmost_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
        topmost_frame.pack(fill="x", padx=20, pady=10)

        self.topmost_var = ctk.BooleanVar(value=False)
        self.topmost_switch = ctk.CTkSwitch(
            topmost_frame,
            text="窗口置顶",
            variable=self.topmost_var,
            command=self.toggle_topmost,
            font=ctk.CTkFont(size=14),
            switch_width=50,
            switch_height=25,
            corner_radius=12,
        )
        self.topmost_switch.pack(padx=20, pady=10)

        # ---------- 自动旋转设置 ----------
        auto_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
        auto_frame.pack(fill="x", padx=20, pady=10)

        auto_label = ctk.CTkLabel(
            auto_frame,
            text="自动旋转设置",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        auto_label.pack(pady=(10, 5))

        switch_row = ctk.CTkFrame(auto_frame, fg_color="transparent")
        switch_row.pack(fill="x", padx=20, pady=5)

        self.auto_switch_var = ctk.BooleanVar(value=False)
        self.auto_switch = ctk.CTkSwitch(
            switch_row,
            text="启用自动旋转",
            variable=self.auto_switch_var,
            command=self.on_auto_switch_toggled,
            font=ctk.CTkFont(size=14),
            switch_width=50,
            switch_height=25,
            corner_radius=12,
        )
        self.auto_switch.pack(side="left")

        time_row = ctk.CTkFrame(auto_frame, fg_color="transparent")
        time_row.pack(fill="x", padx=20, pady=5)

        time_input_label = ctk.CTkLabel(
            time_row,
            text="间隔秒数:",
            font=ctk.CTkFont(size=14),
        )
        time_input_label.pack(side="left", padx=(0, 10))

        self.timer_entry = ctk.CTkEntry(
            time_row,
            font=ctk.CTkFont(size=14),
            height=30,
            width=100,
            corner_radius=6,
        )
        self.timer_entry.pack(side="left")
        self.timer_entry.insert(0, str(self.timer_seconds))

        limit_label = ctk.CTkLabel(
            auto_frame,
            text=f"(允许 {TIMER_MIN_SEC} ~ {TIMER_MAX_SEC} 秒)",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        limit_label.pack(pady=(5, 0))

        self.timer_status_label = ctk.CTkLabel(
            auto_frame,
            text="自动旋转：已关闭",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.timer_status_label.pack(pady=(5, 10))

        # ---------- 状态栏 ----------
        status_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
        status_frame.pack(fill="x", padx=20, pady=10)

        self.status_label = ctk.CTkLabel(
            status_frame,
            text="就绪",
            font=ctk.CTkFont(size=14),
            text_color="gray",
        )
        self.status_label.pack(pady=(10, 10))

        # 窗口关闭协议
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def toggle_topmost(self):
        """切换窗口置顶状态并保存"""
        self.topmost_enabled = self.topmost_var.get()
        self.attributes('-topmost', self.topmost_enabled)
        self.save_config()

    def update_direction_highlight(self):
        self.btn_up.configure(fg_color="#3a7ebf" if self.current_orientation == "up" else "#2b2b2b")
        self.btn_right.configure(fg_color="#3a7ebf" if self.current_orientation == "right" else "#2b2b2b")
        self.btn_down.configure(fg_color="#3a7ebf" if self.current_orientation == "down" else "#2b2b2b")
        self.btn_left.configure(fg_color="#3a7ebf" if self.current_orientation == "left" else "#2b2b2b")
        arrow = ARROW_SYMBOLS.get(self.current_orientation, "●")
        self.current_direction_label.configure(text=arrow)

    def refresh_displays(self):
        try:
            raw_displays = rotatescreen.get_displays()
            self.displays = []
            self.display_options = []

            for i, display in enumerate(raw_displays):
                self.displays.append(display)
                friendly_name = get_friendly_display_name(display, i)
                self.display_options.append(friendly_name)

            if not self.display_options:
                self.display_options = ["未检测到显示器"]
                self.displays = []

            self.monitor_combo.configure(values=self.display_options)

            if self.selected_display_index >= len(self.displays):
                self.selected_display_index = 0

            self.monitor_combo.set(self.display_options[self.selected_display_index])
            self.status_label.configure(text="显示器列表已刷新")

        except Exception as e:
            self.status_label.configure(text=f"刷新失败: {e}")

    def on_monitor_changed(self, choice):
        for i, option in enumerate(self.display_options):
            if option == choice:
                self.selected_display_index = i
                self.status_label.configure(text=f"已选择: {choice}")
                self.save_config()  # 立即保存显示器选择
                break

    def get_selected_display(self):
        if self.displays and 0 <= self.selected_display_index < len(self.displays):
            return self.displays[self.selected_display_index]
        return None

    def rotate_to_direction(self, direction):
        display = self.get_selected_display()
        if not display:
            self.status_label.configure(text="错误：未检测到显示器或未选择")
            return False

        if direction not in ORIENTATIONS:
            self.status_label.configure(text="错误：无效的方向")
            return False

        try:
            target_degrees = ORIENTATIONS[direction]
            display.rotate_to(target_degrees)

            self.current_orientation = direction
            self.update_direction_highlight()

            self.status_label.configure(text=f"✓ 屏幕已旋转至：{direction}")
            self.save_config()
            return True

        except Exception as e:
            self.status_label.configure(text=f"✗ 旋转失败: {e}")
            return False

    # ---------- 自动旋转 ----------
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
                text=f"错误：秒数必须在 {TIMER_MIN_SEC} ~ {TIMER_MAX_SEC} 之间"
            )
            self.auto_switch_var.set(False)
            return

        if not self.get_selected_display():
            self.status_label.configure(text="错误：未选择显示器")
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

    def _schedule_timer(self):
        if not self.auto_rotate_enabled:
            return
        self.timer_thread = threading.Thread(target=self._timer_worker, daemon=True)
        self.timer_thread.start()

    def _timer_worker(self):
        remaining = self.timer_seconds
        while remaining > 0 and self.auto_rotate_enabled:
            if self.timer_stop_event.wait(timeout=min(0.5, remaining)):
                return
            remaining -= 0.5

        if not self.auto_rotate_enabled:
            return
        self.after(0, self._timer_rotate)

    def _timer_rotate(self):
        if not self.auto_rotate_enabled:
            return
        if not self.get_selected_display():
            self.status_label.configure(text="自动旋转已停止：未选择显示器")
            self.stop_auto_rotate()
            return
        self.rotate_to_direction(self.current_orientation)
        if self.auto_rotate_enabled:
            self._schedule_timer()

    # ---------- 配置管理（包含置顶状态） ----------
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
        # 显示器选择
        if 0 <= self.selected_display_index < len(self.display_options):
            self.monitor_combo.set(self.display_options[self.selected_display_index])

        # 方向高亮
        self.update_direction_highlight()

        # 定时器输入
        self.timer_entry.delete(0, "end")
        self.timer_entry.insert(0, str(self.timer_seconds))

        # 自动旋转开关状态（不自动启动）
        self.auto_switch_var.set(self.auto_rotate_enabled)
        if self.auto_rotate_enabled:
            self.timer_status_label.configure(text=f"自动旋转：已开启 (每 {self.timer_seconds} 秒)")
        else:
            self.timer_status_label.configure(text="自动旋转：已关闭")

        # 窗口置顶状态
        self.topmost_var.set(self.topmost_enabled)
        self.attributes('-topmost', self.topmost_enabled)

    def on_closing(self):
        self.stop_timer_thread()
        self.save_config()
        self.destroy()


if __name__ == "__main__":
    app = ScreenRotatorApp()
    app.mainloop()