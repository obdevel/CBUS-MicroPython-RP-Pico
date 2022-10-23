# simple logging facility

import time
import sys

INFO = 0
WARN = 1
ERROR = 2
DEBUG = 3


class logger:
    def __new__(cls):
        if not hasattr(cls, "instance"):
            cls.instance = super(logger, cls).__new__(cls)
        return cls.instance

    def __init__(self):
        pass

    def log(self, msg="", severity=DEBUG):
        t = time.localtime()
        tstr = f"{t[3]:02}:{t[4]:02}:{t[5]:02}  {msg}"
        sys.stdout.write(tstr)
        sys.stdout.write("\n")
