import subprocess

class gdb_bridge:
    def __init__(self, path):
        # Launching gdb
        self.gdb_process = subprocess.Popen(
            ["gdb", "-interpreter=mi",
            str(path)],
            text = True,
            bufsize = 1,
            stdin = subprocess.PIPE,
            stdout = subprocess.PIPE,
            stderr = subprocess.STDOUT
        )
        self.started = False
        self.read()
        self.send("set listsize unlimited")
        self.read()
        self.send("set debuginfod enabled off")
        self.read()
    
    def send(self, command):
        self.gdb_process.stdin.write(command + "\n")
        self.gdb_process.stdin.flush()
    
    def read(self):
        responses = []
        while (True):
            line = self.gdb_process.stdout.readline()
            line = line.strip()
            if (line == ""):
                raise EOFError("gdb stopped responding unexpectedly")
            if (line == "(gdb)"):
                return responses
            responses.append(line)
    
    def is_execution_done(self, data):
        # Execution is over once gdb reports a stop or refuses the command
        for entry in data:
            if (entry.startswith("*stopped") or entry.startswith("^error")):
                return True
        return False
    
    def read_execution(self):
        # Execution commands respond with ^running first and report the stop
        # asynchronously after a later prompt, so keep reading until it arrives
        responses = self.read()
        while (not self.is_execution_done(responses)):
            responses += self.read()
        return responses
    
    def unescape(self, data):
        unescape_dict = {"n": "\n", "t": "\t"}
        unescaped_data = ""
        i = 0
        while (i < len(data)):
            if (data[i] == "\\"):
                unescaped_data += unescape_dict.get(data[i + 1], data[i + 1])
                i += 1
            else:
                unescaped_data += data[i]
            i += 1
        return unescaped_data
    
    def extract_console_output(self, data):
        extracted_lines = []
        for i in range(len(data)):
            if (data[i][0] != "~"):
                continue
            else:
                line = data[i]
                extracted_line = line[2:len(line) - 1]
                unescaped_line = self.unescape(extracted_line)
                extracted_lines.append(unescaped_line)
        return extracted_lines
    
    def extract_error(self, data):
        for entry in data:
            if (entry.startswith("^error")):
                marker = "msg=\""
                start = entry.find(marker)
                if (start == -1):
                    return "gdb reported an error"
                start += len(marker)
                end = entry.rfind("\"")
                return self.unescape(entry[start:end])
    
    def extract_stopped_line(self, data):
        # Pulls the source line number out of a *stopped record, if present
        for entry in data:
            if (entry.startswith("*stopped")):
                if ("exited" in entry):
                    self.started = False
                    return None
                marker = "line=\""
                start = entry.find(marker)
                if (start == -1):
                    return None
                start += len(marker)
                end = entry.find("\"", start)
                return int(entry[start:end])
    
    def run_execution_command(self, command):
        self.send(command)
        recv = self.read_execution()
        output = self.extract_console_output(recv)
        error = self.extract_error(recv)
        if (error is not None):
            output.append(error)
        return output, self.extract_stopped_line(recv)
    
    def user_command(self, command):
        # Runs an arbitrary user-typed command. Since the command might be an
        # execution command (run, c, s, n, ...), check for ^running and if found
        # keep reading until the asynchronous stop record arrives
        self.send(command)
        recv = self.read()
        ran = False
        for entry in recv:
            if (entry.startswith("^running")):
                ran = True
                self.started = True
                break
        if (ran):
            while (not self.is_execution_done(recv)):
                recv += self.read()
        output = self.extract_console_output(recv)
        error = self.extract_error(recv)
        if (error is not None):
            output.append(error)
        return output, self.extract_stopped_line(recv), ran
    
    def list_program(self):
        self.send("list")
        recv = self.read()
        recv = self.extract_console_output(recv)
        return recv
    
    def parse_hex(self, text):
        # Finds the first hex number like 0x7ffc... in a piece of text
        start = text.find("0x")
        if (start == -1):
            return None
        end = start + 2
        while (end < len(text) and text[end] in "0123456789abcdefABCDEF"):
            end += 1
        if (end == start + 2):
            return None
        return int(text[start:end], 16)
    
    def get_value(self, expression):
        # Evaluates an expression with print and returns the text after " = ",
        # or None if gdb errored
        self.send("print " + expression)
        recv = self.read()
        if (self.extract_error(recv) is not None):
            return None
        joined = "".join(self.extract_console_output(recv))
        eq = joined.find(" = ")
        if (eq == -1):
            return None
        return joined[eq + 3:].strip()
    
    def get_locals(self):
        # Returns a list of (name, address, size) tuples for the current frame,
        # or an empty list if there is no frame
        self.send("info locals")
        recv = self.read()
        if (self.extract_error(recv) is not None):
            return []
        lines = self.extract_console_output(recv)
        
        locals_list = []
        for line in lines:
            # Locals print as "name = value", anything else (like continuation
            # lines of struct values or "No locals.") is skipped
            eq = line.find(" = ")
            if (eq == -1):
                continue
            name = line[:eq].strip()
            if (not name.isidentifier()):
                continue
            
            address_value = self.get_value("&" + name)
            address = ""
            if address_value == None:
                address = None
            else:
                address = self.parse_hex(address_value)
            size_text = self.get_value("sizeof(" + name + ")")
            if size_text == None:
                size_text = ""
            size = 0
            if size_text.isdigit() and address != None and address != "":
                size = int(size_text)
            else:
                size = None
            locals_list.append((name, address, size))
        return locals_list
    
    def get_stack(self):
        # Returns (stack_pointer, bytes) for the current frame's stack memory,
        # or (None, []) if the program is not stopped anywhere
        sp = self.parse_hex(self.get_value("$sp") or "")
        if (sp is None):
            return None, []
        fp = self.parse_hex(self.get_value("$fp") or "")
        
        # Reading from the stack pointer to the frame pointer covers the frame's
        # locals, plus 16 bytes for the saved base pointer and return address.
        # Falling back to 64 bytes if the frame pointer is unusable, and capping
        # the read so a huge frame doesn't freeze the GUI
        if (fp is not None and fp > sp):
            length = min((fp - sp) + 16, 512)
        else:
            length = 64
        
        self.send("x/" + str(length) + "xb $sp")
        recv = self.read()
        if (self.extract_error(recv) is not None):
            return sp, []
        
        stack_bytes = []
        for line in self.extract_console_output(recv):
            # Each line looks like "0x7ffc...:\t0x12\t0x34\t..." so everything
            # after the colon is byte values
            colon = line.find(":")
            if (colon == -1):
                continue
            for token in line[colon + 1:].split():
                if (token.startswith("0x")):
                    stack_bytes.append(int(token, 16))
        return sp, stack_bytes
    
    def add_break(self, line_number):
        self.send("b " + str(line_number))
        self.read()
    
    def remove_break(self, line_number):
        # clear takes a line number and deletes the breakpoint there,
        # unlike disable which takes a breakpoint number
        self.send("clear " + str(line_number))
        self.read()
    
    def cont(self):
        # The program has to be launched with run first, then continued with c
        if (not self.started):
            self.started = True
            return self.run_execution_command("run")
        return self.run_execution_command("c")
    
    def step(self):
        # start launches the program stopped at main so single stepping can begin
        if (not self.started):
            self.started = True
            return self.run_execution_command("start")
        return self.run_execution_command("s")
    
    def close_gdb(self):
        self.gdb_process.terminate()
        try:
            self.gdb_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.gdb_process.kill()
            self.gdb_process.wait()