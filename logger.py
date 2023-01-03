# simple logging facility

import sys
import time

from micropython import const

INFO = const(0)
WARN = const(1)
ERROR = const(2)
DEBUG = const(3)


class logger:
    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls.instance = super(logger, cls).__new__(cls)
        return cls.instance

    @staticmethod
    def log(msg=''):
        tstr = f'{time.ticks_ms():10} {msg}'
        sys.stdout.write(tstr)
        sys.stdout.write(b'\n')
