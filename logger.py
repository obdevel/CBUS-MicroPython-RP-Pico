# simple logging facility

import time
import sys


class logger:
    def __new__(cls):
        if not hasattr(cls, "instance"):
            cls.instance = super(logger, cls).__new__(cls)
        return cls.instance

    def __init__(self):
        pass

    def log(self, msg=""):
        t = time.localtime()
        tstr = f"{t[3]:02}:{t[4]:02}:{t[5]:02}  {msg}"
        sys.stdout.write(tstr)
        sys.stdout.write("\n")
