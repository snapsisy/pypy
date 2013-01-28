"""
A color print.
"""

import sys
from py.io import ansi_print
from rpython.tool.ansi_mandelbrot import Driver as MandelbrotDriver

class SpinningDriver(object):
    def __init__(self):
        self.states = ['|', '/', '-', '\\']
        self.state = 0
    def reset(self):
        self.state = 0
    def dot(self):
        sys.stderr.write(self.states[self.state] + '\b')
        self.state += 1
        self.state %= len(self.states)

class AnsiLog:
    wrote_dot = False # XXX sharing state with all instances

    KW_TO_COLOR = {
        # color supress
        'red': ((31,), True),
        'bold': ((1,), True),
        'WARNING': ((31,), False),
        'event': ((1,), True),
        'ERROR': ((1, 31), False),
        'Error': ((1, 31), False),
        'info': ((35,), False),
        'stub': ((34,), False),
        'init': ((1, 34), False),
    }
    
    log_on_quiet = [
        "ERROR",
        "Error",
        "init",
    ]

    def __init__(self, kw_to_color={}, file=None):
        self.kw_to_color = self.KW_TO_COLOR.copy()
        self.kw_to_color.update(kw_to_color)
        self.file = file
        self.isatty = getattr(sys.stderr, 'isatty', lambda: False)
        self.driver = None
        self.set_option(fancy=True, quiet=False)

    def set_option(self, fancy=None, quiet=None):
        if fancy is not None:
            self.fancy = fancy
        if quiet is not None:
            self.quiet = quiet
        
        self.driver = None
        if self.isatty and self.fancy:
            self.driver = MandelbrotDriver()
        if self.isatty and self.quiet:
            self.driver = SpinningDriver()

    def __call__(self, msg):
        tty = self.isatty()
        flush = False
        newline = True
        keywords = []
        esc = []
        for kw in msg.keywords:
            color, supress = self.kw_to_color.get(kw, (None, False))
            if color:
                esc.extend(color)
            if not supress:
                keywords.append(kw)
        if 'start' in keywords:
            if tty:
                newline = False
                flush = True
                keywords.remove('start')
        elif 'done' in keywords:
            if tty:
                print >> sys.stderr
                return
        elif 'dot' in keywords:
            if tty:
                if self.driver is not None:
                    if not AnsiLog.wrote_dot:
                        self.driver.reset()
                    self.driver.dot()
                else:
                    ansi_print(".", tuple(esc), file=self.file, newline=False, flush=flush)
                AnsiLog.wrote_dot = True
                return
        if AnsiLog.wrote_dot:
            AnsiLog.wrote_dot = False
            sys.stderr.write("\n")
        esc = tuple(esc)
        if not self.quiet or any([kw in self.log_on_quiet for kw in keywords]):
            for line in msg.content().splitlines():
                ansi_print("[%s] %s" %(":".join(keywords), line), esc, 
                            file=self.file, newline=newline, flush=flush)

ansi_log = AnsiLog()
