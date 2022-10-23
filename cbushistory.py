# CBUS event history

import time
import logger

POLARITY_OFF = 0
POLARITY_ON = 1
POLARITY_DONT_CARE = 2


class historyitem:

    """CBUS meesage history item"""

    def __init__(self, msg):
        self.msg = msg
        self.insert_time = time.ticks_ms()


class cbushistory:

    """CBUS message history"""

    def __init__(self, bus, max_size=64, time_to_live=10000, store_all_messages=False):
        self.logger = logger.logger
        self.history = []
        self.max_size = max_size
        self.time_to_live = time_to_live
        self.store_all_messages = store_all_messages
        self.bus = bus
        self.bus.set_history(self)

    def add(self, msg):
        added = False

        for i in range(len(self.history)):
            if self.history[i] is None:
                self.history[i] = historyitem(msg)
                added = True
                break

        if not added and len(self.history) < self.max_size:
            self.history.append(historyitem(msg))

    def reap(self):
        for i in range(len(self.history)):
            if (self.history[i] is not None) and (
                self.history[i].insert_time + self.time_to_live < time.ticks_ms()
            ):
                self.history[i] = None

    def count(self):
        c = 0

        for i in range(len(self.history)):
            if self.history[0] is not None:
                c += 1
        return c

    def clear(self):
        self.history = []

    def display(self):
        for i in range(len(self.history)):
            if self.history[i] is not None:
                str = f"{i} - {self.history[i].msg}, {self.history[i].insert_time}"
                self.logger.log(str)

    def find_event(self, nn, en, polarity=POLARITY_DONT_CARE, within=1000):
        for i in range(len(self.history)):
            if self.history[i] is not None:
                if (self.history[i].msg.data[1] * 256) + self.history[i].msg.data[2] == nn and (self.history[i].msg.data[3] * 256) + self.history[i].msg.data[4] == en:
                    if polarity == POLARITY_DONT_CARE or (polarity == POLARITY_ON and not (self.history[i].msg.data[0] & 1)) or (polarity == POLARITY_OFF and (self.history[i].msg.data[0] & 1)):
                        if self.history[i].insert_time > (time.ticks_ms() - within):
                            return True
        return False

