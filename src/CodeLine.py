import tkinter as tk

class CodeLine:
    HOVER_COLOR = "lightblue"
    BREAKPOINT_COLOR = "#e0071c"
    RUN_COLOR = "#1fcc36"

    def __init__(self, parent, line_number, text, default_color, on_click = None):
        self.line_number = line_number
        self.default_color = default_color
        self.on_click = on_click
        self.run_state = False
        self.break_state = False

        self.label = tk.Label(parent, text = text, name = str(line_number), anchor = "w")
        self.label.pack(side = "top", anchor = "nw", fill = "x")
        self.label.bind("<Enter>", lambda e: self.on_enter())
        self.label.bind("<Leave>", lambda e: self.on_leave())
        self.label.bind("<Button-1>", lambda e: self.click())

    def click(self):
        if (self.on_click is not None):
            self.on_click(self)

    def on_enter(self):
        self.label.config(background = CodeLine.HOVER_COLOR)

    def on_leave(self):
        self.resolve_background()

    def resolve_background(self):
        if (self.run_state):
            self.label.config(background = CodeLine.RUN_COLOR)
        elif (self.break_state):
            self.label.config(background = CodeLine.BREAKPOINT_COLOR)
        else:
            self.label.config(background = self.default_color)

    def toggle_break(self):
        self.break_state = not self.break_state
        self.resolve_background()
        return self.break_state

    def set_state(self, run_state, break_state):
        self.run_state = run_state
        self.break_state = break_state
        self.resolve_background()