"""
Мышиный бот с окошком (аналог TinyTask).
Запись и воспроизведение движений, зажатий кнопок и прокрутки мыши.

Установка:  pip install pynput
Запуск:     python mouse_bot_gui.py
Сборка exe: pip install pyinstaller
            pyinstaller --onefile --noconsole mouse_bot_gui.py
            (готовый exe появится в папке dist)

Горячие клавиши (работают, даже если окно свёрнуто):
    F8 - запись старт/стоп
    F9 - воспроизведение старт/стоп
"""

import json
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from pynput import keyboard, mouse


class App:
    def __init__(self, root):
        self.root = root
        root.title("Mouse Bot")
        root.attributes("-topmost", True)   # окно всегда поверх остальных
        root.resizable(False, False)

        self.events = []
        self.recording = False
        self.playing = False
        self.t0 = 0.0
        self.bounds = (0, 0, 0, 0)          # положение окна, чтобы не записывать клики по нему
        self.controller = mouse.Controller()

        # --- интерфейс ---
        top = tk.Frame(root)
        top.pack(padx=8, pady=8)
        self.btn_rec = tk.Button(top, text="● Запись (F8)", width=14, command=self.toggle_record)
        self.btn_play = tk.Button(top, text="▶ Играть (F9)", width=14, command=self.toggle_play)
        self.btn_rec.grid(row=0, column=0, padx=3, pady=3)
        self.btn_play.grid(row=0, column=1, padx=3, pady=3)
        tk.Button(top, text="Сохранить", width=14, command=self.save).grid(row=1, column=0, padx=3, pady=3)
        tk.Button(top, text="Загрузить", width=14, command=self.load).grid(row=1, column=1, padx=3, pady=3)

        opts = tk.Frame(root)
        opts.pack(padx=8)
        tk.Label(opts, text="Повторов (0 = бесконечно):").grid(row=0, column=0, sticky="w")
        self.loops = tk.Spinbox(opts, from_=0, to=99999, width=6)
        self.loops.delete(0, "end")
        self.loops.insert(0, "1")
        self.loops.grid(row=0, column=1, padx=4)
        tk.Label(opts, text="Скорость:").grid(row=1, column=0, sticky="w")
        self.speed = tk.Scale(opts, from_=0.25, to=4.0, resolution=0.25,
                              orient="horizontal", length=140)
        self.speed.set(1.0)
        self.speed.grid(row=1, column=1)

        self.status = tk.Label(root, text="Ожидание", fg="gray")
        self.status.pack(pady=6)

        root.bind("<Configure>", self.on_configure)

        # --- слушатели мыши и клавиатуры ---
        mouse.Listener(on_move=self.on_move, on_click=self.on_click,
                       on_scroll=self.on_scroll).start()
        keyboard.Listener(on_press=self.on_key).start()

    # ---------- служебное ----------
    def set_status(self, text, color="gray"):
        self.root.after(0, lambda: self.status.config(text=text, fg=color))

    def on_configure(self, _):
        r = self.root
        self.bounds = (r.winfo_rootx(), r.winfo_rooty(),
                       r.winfo_rootx() + r.winfo_width(),
                       r.winfo_rooty() + r.winfo_height())

    def inside_window(self, x, y):
        x1, y1, x2, y2 = self.bounds
        return x1 <= x <= x2 and y1 <= y <= y2

    def on_key(self, key):
        if key == keyboard.Key.f8:
            self.root.after(0, self.toggle_record)
        elif key == keyboard.Key.f9:
            self.root.after(0, self.toggle_play)

    # ---------- запись ----------
    def add(self, kind, x, y, **data):
        if self.recording and not self.inside_window(x, y):
            self.events.append({"t": time.time() - self.t0, "type": kind,
                                "x": x, "y": y, **data})

    def on_move(self, x, y):
        self.add("move", x, y)

    def on_click(self, x, y, button, pressed):
        self.add("click", x, y, button=button.name, pressed=pressed)

    def on_scroll(self, x, y, dx, dy):
        self.add("scroll", x, y, dx=dx, dy=dy)

    def toggle_record(self):
        if self.playing:
            return
        if not self.recording:
            self.events = []
            self.t0 = time.time()
            self.recording = True
            self.btn_rec.config(text="■ Стоп (F8)")
            self.set_status("Идёт запись...", "red")
        else:
            self.recording = False
            self.btn_rec.config(text="● Запись (F8)")
            self.set_status(f"Записано событий: {len(self.events)}", "green")

    # ---------- воспроизведение ----------
    def toggle_play(self):
        if self.recording:
            return
        if self.playing:
            self.playing = False
            return
        if not self.events:
            messagebox.showinfo("Mouse Bot", "Нет записи. Сначала запишите (F8) или загрузите файл.")
            return
        try:
            loops = int(self.loops.get())
        except ValueError:
            loops = 1
        speed = float(self.speed.get())
        self.playing = True
        self.btn_play.config(text="■ Стоп (F9)")
        threading.Thread(target=self.play_worker, args=(loops, speed), daemon=True).start()

    def play_worker(self, loops, speed):
        try:
            n = 0
            while self.playing and (loops == 0 or n < loops):
                n += 1
                self.set_status(f"Воспроизведение... (проход {n})", "blue")
                start = time.time()
                for e in self.events:
                    if not self.playing:
                        break
                    delay = e["t"] / speed - (time.time() - start)
                    if delay > 0:
                        time.sleep(delay)
                    self.controller.position = (e["x"], e["y"])
                    if e["type"] == "click":
                        btn = getattr(mouse.Button, e["button"])
                        if e["pressed"]:
                            self.controller.press(btn)
                        else:
                            self.controller.release(btn)
                    elif e["type"] == "scroll":
                        self.controller.scroll(e["dx"], e["dy"])
        finally:
            # если остановили посреди зажатия - отпускаем все кнопки
            for b in (mouse.Button.left, mouse.Button.right, mouse.Button.middle):
                self.controller.release(b)
            self.playing = False
            self.root.after(0, lambda: self.btn_play.config(text="▶ Играть (F9)"))
            self.set_status("Воспроизведение завершено", "gray")

    # ---------- файлы ----------
    def save(self):
        if not self.events:
            messagebox.showinfo("Mouse Bot", "Нечего сохранять.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("Запись мыши", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.events, f)
            self.set_status("Сохранено", "green")

    def load(self):
        path = filedialog.askopenfilename(filetypes=[("Запись мыши", "*.json")])
        if path:
            try:
                with open(path, encoding="utf-8") as f:
                    self.events = json.load(f)
                self.set_status(f"Загружено событий: {len(self.events)}", "green")
            except (OSError, ValueError):
                messagebox.showerror("Mouse Bot", "Не удалось прочитать файл.")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
