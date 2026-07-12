import tkinter as tk
from tkinter import filedialog
import gdb_bridge
import CodeLine

class GUI:
    def __init__(self):
        self.main_window = tk.Tk()
        # Frame that holds the code that is being run by gdb
        self.code_frame = tk.Frame(self.main_window)
        self.code_canvas = tk.Canvas(self.code_frame)
        self.code_scroll = tk.Scrollbar(self.code_frame)
        self.code_inner = tk.Frame(self.code_canvas)
        self.init_label_color = tk.Label(self.code_canvas).cget("background")
        self.code_lines = dict()
        self.current_run_line = None

        # Frame that holds memory visualizations
        self.memory_frame = tk.Frame(self.main_window)
        self.memory_canvas = tk.Canvas(self.memory_frame)
        self.memory_scroll = tk.Scrollbar(self.memory_frame)
        self.memory_inner = tk.Frame(self.memory_canvas)
        self.memory_locals_column = tk.Frame(self.memory_inner)
        self.memory_stack_column = tk.Frame(self.memory_inner)

        # Frame to hold all the interactable elements like buttons
        self.options_frame = tk.Frame(self.main_window)
        self.file_label = tk.Label(self.options_frame)
        self.options_choose_file_bt = tk.Button(self.options_frame)
        self.options_load_file_bt = tk.Button(self.options_frame)
        self.options_close_gdb_bt = tk.Button(self.options_frame)
        self.options_cont_bt = tk.Button(self.options_frame)
        self.options_step_bt = tk.Button(self.options_frame)
        self.options_command_entry = tk.Entry(self.options_frame)
        self.options_command_send_bt = tk.Button(self.options_frame)
        self.options_gdb_response_label = tk.Label(self.options_frame)

        self.code_file_path = ""
        self.bridge = None

    def scrollbar_setup(self, canvas, bar, inner):
        bar.pack(side = "right", fill = "y")
        canvas.pack(side = "left", expand = True, fill = "both")

        window_id = canvas.create_window((0, 0), window = inner, anchor = "nw")

        canvas.config(yscrollcommand = bar.set)
        bar.config(command = canvas.yview)
        inner.bind("<Configure>", lambda e: canvas.config(scrollregion = canvas.bbox("all")))

        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window_id, width = e.width))

    def init_code_frame(self):
        # Border styling
        self.code_frame.config(borderwidth = 4, relief = "raised")

        # Scrollbar setup
        self.scrollbar_setup(self.code_canvas, self.code_scroll, self.code_inner)

    def init_memory_frame(self):
        # Border styling
        self.memory_frame.config(borderwidth = 4, relief = "raised")

        # Scrollbar setup
        self.scrollbar_setup(self.memory_canvas, self.memory_scroll, self.memory_inner)

        # Two equal columns, locals on the left and the stack on the right
        self.memory_inner.columnconfigure(0, weight = 1, uniform = "memory")
        self.memory_inner.columnconfigure(1, weight = 1, uniform = "memory")
        self.memory_locals_column.grid(row = 0, column = 0, sticky = "nsew")
        self.memory_stack_column.grid(row = 0, column = 1, sticky = "nsew")

    def init_options_frame(self):
        # Preventing resizing
        self.options_frame.pack_propagate(False)

        # Border styling
        self.options_frame.config(borderwidth = 4, relief = "raised")
        self.file_label.config(text = "")
        self.file_label.pack(side = "top", fill = "x")

        # Setting buttons
        self.options_choose_file_bt.config(text = "Choose file...", command = self.open_file_dialog)
        self.options_choose_file_bt.pack(side = "top")
        self.options_load_file_bt.config(text = "Load file", command = self.load_file)
        self.options_load_file_bt.pack(side = "top")
        self.options_close_gdb_bt.config(text = "Close GDB", command = self.close_gdb_bridge)
        self.options_close_gdb_bt.pack(side = "top")
        self.options_cont_bt.config(text = "Continue", command = self.cont, state = "disabled")
        self.options_cont_bt.pack(side = "top")
        self.options_step_bt.config(text = "Step", command = self.step, state = "disabled")
        self.options_step_bt.pack(side = "top")

        # Text box for typing commands straight to gdb
        self.options_command_entry.config(state = "disabled")
        self.options_command_entry.pack(side = "top", fill = "x")
        self.options_command_entry.bind("<Return>", lambda e: self.send_user_command())
        self.options_command_send_bt.config(text = "Send Command", command = self.send_user_command, state = "disabled")
        self.options_command_send_bt.pack(side = "top")

        self.options_gdb_response_label.config(text = "GDB Messages")
        self.options_gdb_response_label.pack(side = "top", fill = "x")
        self.options_gdb_response_label.bind("<Configure>", lambda e: self.options_gdb_response_label.config(wraplength = self.options_gdb_response_label.winfo_width()))
        self.file_label.bind("<Configure>", lambda e: self.file_label.config(wraplength = self.file_label.winfo_width()))
    
    def step(self):
        response, stopped_line = self.bridge.step()
        self.options_gdb_response_label.config(text = "".join(response))
        self.update_run_line(stopped_line)
    
    def cont(self):
        response, stopped_line = self.bridge.cont()
        self.options_gdb_response_label.config(text = "".join(response))
        self.update_run_line(stopped_line)

    def send_user_command(self):
        command = self.options_command_entry.get().strip()
        if (command == ""):
            return
        response, stopped_line, ran = self.bridge.user_command(command)
        self.options_gdb_response_label.config(text = "".join(response))
        # Only moving the run highlight if the command actually ran the program,
        # otherwise commands like info locals would wrongly clear it
        if (ran):
            self.update_run_line(stopped_line)
        self.options_command_entry.delete(0, "end")

    def update_run_line(self, line_number):
        # Clearing the highlight on the previously run line
        if (self.current_run_line is not None):
            prev_line = self.code_lines.get(self.current_run_line)
            if (prev_line is not None):
                prev_line.set_state(False, prev_line.break_state)
        
        # Highlighting the newly run line, None means the program is not stopped on a line
        self.current_run_line = line_number
        if (line_number is not None):
            new_line = self.code_lines.get(line_number)
            if (new_line is not None):
                new_line.set_state(True, new_line.break_state)
        
        self.update_memory()

    def update_memory(self):
        # Clearing out the previous frame's memory display
        for child in self.memory_locals_column.winfo_children():
            child.destroy()
        for child in self.memory_stack_column.winfo_children():
            child.destroy()
        if (self.bridge is None):
            return
        
        self.populate_locals_column()
        self.populate_stack_column()

    def populate_locals_column(self):
        tk.Label(self.memory_locals_column, text = "Locals", font = "TkHeadingFont").grid(row = 0, column = 0, columnspan = 3)
        
        locals_list = self.bridge.get_locals()
        if (len(locals_list) == 0):
            tk.Label(self.memory_locals_column, text = "No Locals", anchor = "w").grid(row = 1, column = 0, columnspan = 3, sticky = "w")
            return
        
        for i in range(3):
            self.memory_locals_column.columnconfigure(i, weight = 1)
        tk.Label(self.memory_locals_column, text = "Name", anchor = "w").grid(row = 1, column = 0, sticky = "w")
        tk.Label(self.memory_locals_column, text = "Address", anchor = "w").grid(row = 1, column = 1, sticky = "w")
        tk.Label(self.memory_locals_column, text = "Size", anchor = "w").grid(row = 1, column = 2, sticky = "w")
        
        for i in range(len(locals_list)):
            name, address, size = locals_list[i]
            if address != None and address != "":
                address_text = hex(address)
            else:
                address_text = "?"
            if size != None and size != "":
                size_text = str(size)
            else:
                size_text = "?"
            tk.Label(self.memory_locals_column, text = name, anchor = "w").grid(row = i + 2, column = 0, sticky = "w")
            tk.Label(self.memory_locals_column, text = address_text, anchor = "w", font = "TkFixedFont").grid(row = i + 2, column = 1, sticky = "w")
            tk.Label(self.memory_locals_column, text = size_text, anchor = "w").grid(row = i + 2, column = 2, sticky = "w")

    def populate_stack_column(self):
        BYTES_PER_ROW = 4
        tk.Label(self.memory_stack_column, text = "Stack", font = "TkHeadingFont").grid(row = 0, column = 0, columnspan = 2)
        
        stack_pointer, stack_bytes = self.bridge.get_stack()
        if (stack_pointer is None or len(stack_bytes) == 0):
            tk.Label(self.memory_stack_column, text = "No Stack", anchor = "w").grid(row = 1, column = 0, columnspan = 2, sticky = "w")
            return
        
        self.memory_stack_column.columnconfigure(1, weight = 1)
        for i in range(0, len(stack_bytes), BYTES_PER_ROW):
            row_bytes = stack_bytes[i : i + BYTES_PER_ROW]
            binary_text = " ".join(format(b, "08b") for b in row_bytes)
            row = (i // BYTES_PER_ROW) + 1
            tk.Label(self.memory_stack_column, text = hex(stack_pointer + i), anchor = "w", font = "TkFixedFont").grid(row = row, column = 0, sticky = "w")
            tk.Label(self.memory_stack_column, text = binary_text, anchor = "w", font = "TkFixedFont").grid(row = row, column = 1, sticky = "w", padx = (10, 0))

    def click_breakpoint(self, line):
        if (line.break_state):
            self.bridge.remove_break(line.line_number)
        else:
            self.bridge.add_break(line.line_number)
        line.toggle_break()

    def populate_code(self, code_lines):
        # Clear any lines from a previous load so files don't stack up
        for child in self.code_inner.winfo_children():
            child.destroy()
        self.code_lines.clear()
        
        # Checking if any source was detected
        if (len(code_lines) == 0):
            new_line = tk.Label(self.code_inner, text = "No Source Code Found", name = "message", anchor = "w")
            new_line.pack(side = "top", anchor = "nw", fill = "x")
            return
        
        # Numbering from 1 so line numbers match gdb's
        for i in range(len(code_lines)):
            line = CodeLine.CodeLine(self.code_inner, i + 1, code_lines[i], self.init_label_color, on_click = self.click_breakpoint)
            self.code_lines[i + 1] = line
    
    def set_code_line_state(self, line_number, run_state, break_state):
        line = self.code_lines.get(line_number)
        if (line is not None):
            line.set_state(run_state, break_state)

    def load_file(self):
        if (self.code_file_path != ""):
            self.code_lines.clear()
            self.current_run_line = None
            self.bridge = gdb_bridge.gdb_bridge(self.code_file_path)
            self.populate_code(self.bridge.list_program())
            self.options_load_file_bt.config(state = "disabled")
            self.options_choose_file_bt.config(state = "disabled")
            self.options_cont_bt.config(state = "normal")
            self.options_step_bt.config(state = "normal")
            self.options_command_entry.config(state = "normal")
            self.options_command_send_bt.config(state = "normal")
        else:
            self.file_label.config(text = "No File Was Chosen")

    def open_file_dialog(self):
        self.code_file_path = tk.filedialog.askopenfilename(initialdir = ".")
        if (self.code_file_path != ""):
            self.file_label.config(text = self.code_file_path)
    
    def close_gdb_bridge(self):
        if (self.bridge != None):
            self.bridge.close_gdb()
        if (self.main_window != None):
            self.main_window.destroy()

    def init_main_window(self):
        # Setting frames to be in the top left, top right, and bottom center
        self.code_frame.grid(row = 0, column = 0, sticky = "nsew")
        self.memory_frame.grid(row = 1, column = 0, columnspan = 2, sticky = "nsew")
        self.options_frame.grid(row = 0, column = 1, sticky = "nsew")
        self.main_window.columnconfigure(0, weight = 1)
        self.main_window.columnconfigure(1, weight = 1)
        self.main_window.rowconfigure(0, weight = 1)
        self.main_window.rowconfigure(1, weight = 1)

        # Setting the window to open maximized
        self.main_window.attributes("-zoomed", 1)

        # Route the window's X button through the GDB cleanup instead of a bare destroy
        self.main_window.protocol("WM_DELETE_WINDOW", self.close_gdb_bridge)

        # Frame inits
        self.init_code_frame()
        self.init_options_frame()
        self.init_memory_frame()

        self.main_window.mainloop()

gui = GUI()
gui.init_main_window()