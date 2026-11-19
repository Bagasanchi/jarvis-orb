"""Conversation and workspace controls, pumped on the orb's UI thread."""
import queue
import time


class ControlPanel:
    def __init__(self, state):
        import tkinter as tk
        from tkinter import ttk
        from tkinter.scrolledtext import ScrolledText
        self.state = state
        self.root = tk.Tk()
        self.root.title('Jarvis — Conversation & Projects')
        self.root.geometry('820x660')
        self.root.protocol('WM_DELETE_WINDOW', self.root.withdraw)
        self.status = tk.StringVar(value='Connecting…')
        ttk.Label(self.root, textvariable=self.status, wraplength=790).pack(fill='x', padx=12, pady=8)
        self.history = ScrolledText(self.root, state='disabled', wrap='word', font=('Segoe UI', 11))
        self.history.pack(fill='both', expand=True, padx=12)
        self.entry = ttk.Entry(self.root, font=('Segoe UI', 12))
        self.entry.pack(fill='x', padx=12, pady=8)
        self.entry.bind('<Return>', lambda event: self.send())
        buttons = ttk.Frame(self.root); buttons.pack(fill='x', padx=12, pady=4)
        ttk.Button(buttons, text='Send', command=self.send).pack(side='left')
        ttk.Button(buttons, text='Edit last request', command=self.edit_last).pack(side='left', padx=5)
        ttk.Button(buttons, text='Mute / unmute mic', command=state.toggle_mute).pack(side='left', padx=5)
        ttk.Button(buttons, text='Add project shortcut', command=self.add_workspace).pack(side='left', padx=5)
        ttk.Label(self.root, text='Editing resends a request; it does not undo actions. History stays in memory.').pack(anchor='w', padx=12, pady=6)
        self.version = -1
        self.history_epoch = state.history.epoch
        self.last_poll = 0.0

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.entry.focus_set()

    def send(self):
        text = self.entry.get().strip()
        if text and self.state.submit(text):
            self.entry.delete(0, 'end')

    def edit_last(self):
        _, items = self.state.history.snapshot()
        last = next((i for i in reversed(items) if i['role'] == 'You'), None)
        if last:
            self.entry.delete(0, 'end')
            self.entry.insert(0, last['text'])
            self.entry.focus_set()

    def add_workspace(self):
        from tkinter import filedialog, simpledialog, messagebox
        from jarvis.workspaces import Workspaces
        name = simpledialog.askstring('Project nickname', 'Say “open my [nickname]” to launch it.', parent=self.root)
        if not name:
            return
        folder = filedialog.askdirectory(title='Choose your project folder', parent=self.root)
        if not folder:
            return
        editor = simpledialog.askstring('Editor', 'Enter explorer, vscode, or godot:', initialvalue='vscode', parent=self.root)
        if not editor:
            return
        try:
            Workspaces().save(name, folder, editor.strip().lower())
        except (ValueError, OSError) as error:
            messagebox.showerror('Project shortcut', str(error), parent=self.root)

    def poll(self):
        from tkinter import messagebox
        self.root.update()
        if time.monotonic() - self.last_poll < .1:
            return
        self.last_poll = time.monotonic()
        self.status.set(('MIC MUTED | ' if self.state.muted.is_set() else 'MIC ENABLED | ') + self.state.status_text())
        version, items = self.state.history.snapshot()
        if self.history_epoch != self.state.history.epoch:
            self.history_epoch = self.state.history.epoch
            self.entry.delete(0, 'end')
        if version != self.version:
            self.version = version
            self.history.configure(state='normal')
            self.history.delete('1.0', 'end')
            for item in items:
                label = item['role'] + (f" ({item['source']})" if item['source'] else '')
                self.history.insert('end', label + ': ' + item['text'] + '\n\n')
            self.history.configure(state='disabled')
            self.history.see('end')
        try:
            request = self.state.confirmations.requests.get_nowait()
        except queue.Empty:
            return
        if request.done.is_set() or request.invalid():
            self.state.confirmations.decide(request, False)
            return
        self.state.paused.set()
        try:
            self.show()
            result = messagebox.askyesno('Confirm Jarvis action', request.message, parent=self.root, default='no')
            self.state.confirmations.decide(request, result)
        finally:
            self.state.paused.clear()

    def close(self):
        self.root.destroy()
