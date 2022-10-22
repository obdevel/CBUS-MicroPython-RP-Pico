# CBUS event history

import time

EVENT_OFF = 0
EVENT_ON = 1
EVENT_DONT_CARE = 2


class historyitem:

    """CBUS meesage history item"""

    def __init__(self, msg):
        self.msg = msg
        self.insert_time = time.ticks_ms()


class cbushistory:

    """CBUS message history"""

    def __init__(self, bus, max_size=64, max_age=10000, store_all_messages=False):
        self.history = []
        self.max_size = max_size
        self.max_age = max_age
        self.store_all_messages = store_all_messages
        self.bus = bus
        self.bus.set_history(self)

    def add(self, msg):
        added = False
        item = historyitem(msg)

        for i in range(len(self.history)):
            if self.history[i] is None:
                self.history[i] = item
                added = True
                break

        if not added and len(self.history) < self.max_size:
            self.history.append(item)

    def reap(self):
        for i in range(len(self.history)):
            if (self.history[i] is not None) and (
                self.history[i].insert_time + self.max_age < time.ticks_ms()
            ):
                self.history[i] = None

    def count(self):
        c = 0

        for i in range(len(self.history)):
            if self.history[0] is not None:
                c += 1
        return c

    def find_event(self, nn, en, polarity=EVENT_DONT_CARE, within=1000):
        for i in range(len(self.history)):
            pass
