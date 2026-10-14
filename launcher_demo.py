# -*- coding: utf-8 -*-
"""
launcher_demo.py —— 最小启动器示例
===================================
演示如何将两个插件的界面通过 Notebook Tab 融合到一起。
你同事的插件只需要同样实现 get_plugin_tab() 接口即可。

使用方法：
  1. 确保 run_pipeline_plugin.py 在同一目录（或 Python path 中）
  2. python launcher_demo.py
"""

import json
import importlib
import tkinter as tk
from tkinter import ttk
from pathlib import Path


class Launcher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("工具箱")
        self.root.geometry("820x720")
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=4, pady=4)
        self.load_plugins()

    def load_plugins(self):
        """自动发现并加载当前目录下所有带 manifest.json 的插件"""
        plugin_dir = Path(__file__).parent

        manifest_paths = set()
        # 子目录插件
        manifest_paths.update(plugin_dir.glob("*/manifest.json"))
        # 根目录插件
        root_manifest = plugin_dir / "manifest.json"
        if root_manifest.exists():
            manifest_paths.add(root_manifest)

        import sys

        for manifest_path in sorted(manifest_paths):
            # manifest 所在目录就是插件目录
            plugin_path = str(manifest_path.parent)
            cfg = json.loads(manifest_path.read_text(encoding="utf-8"))
            print(f"发现插件：{cfg['name']}  @ {plugin_path}")

            # 动态导入
            mod_name, func_name = cfg["entry"].split(":")
            # 把插件目录加入 sys.path（如果还不在的话）
            if plugin_path not in sys.path:
                sys.path.insert(0, plugin_path)

            mod = importlib.import_module(mod_name)
            widget = getattr(mod, func_name)(master=self.root)
            self.notebook.add(widget, text=cfg["name"])
            print(f"✅ 已加载：{cfg['name']}")


if __name__ == "__main__":
    app = Launcher()
    app.root.mainloop()
