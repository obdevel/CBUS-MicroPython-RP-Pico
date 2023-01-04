# CBUS event history

import time

import uasyncio as asyncio
from micropython import const

import canmessage
import logger

ORDER_ANY = const(0)
ORDER_GIVEN = const(1)
ORDER_REVERSE = const(2)

ORDER_BEFORE = const(3)
ORDER_AFTER = const(4)

TIME_NOT_FOUND = const(-1)
TIME_ANY = const(-1)
WINDOW_ANY = const(-1)

WHICH_ANY = const(0)
WHICH_EARLIEST = const(1)
WHICH_LATEST = const(2)


class historyitem:
    """CBUS message history item"""

    def __init__(self, msg):
        self.msg = msg
        self.arrival_time = time.ticks_ms()


class cbushistory:
    """CBUS message history"""

    def __init__(self, bus, max_size: int = -1, time_to_live: int = 10000, query_type: int = canmessage.QUERY_ALL,
                 query=None) -> None:
        self.logger = logger.logger()
        self.history = []
        self.max_size = max_size
        self.time_to_live = time_to_live
        self.query_type = query_type
        self.query = query
        self.bus = bus
        self.add_evt = asyncio.Event()
        self.last_update = 0
        self.last_item_received = None
        self.bus.add_history(self)

        asyncio.create_task(self.reaper())

    def set_ttl(self, time_to_live) -> None:
        self.time_to_live = time_to_live

    def add(self, msg: canmessage.canmessage) -> None:
        if not (self.max_size == -1 or len(self.history) < self.max_size):
            del self.history[0]

        if msg.matches(self.query_type, self.query):
            h = historyitem(msg)
            self.history.append(h)
            self.last_item_received = h
            self.last_update = time.ticks_ms()
            self.add_evt.set()

    async def wait(self):
        await self.add_evt.wait()
        self.add_evt.clear()

    async def reaper(self, freq: int = 500) -> None:
        while True:
            tnow = time.ticks_ms()
            for i in range(len(self.history) - 1, -1, -1):
                if self.history[i].arrival_time + self.time_to_live < tnow:
                    del self.history[i]
            await asyncio.sleep_ms(min(freq, self.time_to_live))

    def count(self) -> int:
        return len(self.history)

    def clear(self) -> None:
        self.history = []

    def display(self) -> None:
        for i, h in enumerate(self.history):
            sc = tuple(h.msg)
            it = h.arrival_time
            ds = f"{i} {sc} {it}"
            self.logger.log(ds)

    def last_update_time(self) -> int:
        return self.last_update

    def event_received(self, event: tuple, within: int = TIME_ANY) -> bool:
        for h in self.history:
            if h.msg.get_node_number == event[1] and h.msg.get_event_number() == event[2]:
                if event[0] == canmessage.POLARITY_EITHER or (
                        event[0] == canmessage.POLARITY_ON and not (h.msg.data[0] & 1)) or (
                        event[0] == canmessage.POLARITY_OFF and (h.msg.data[0] & 1)):
                    if within == TIME_ANY or h.arrival_time > (time.ticks_ms() - within):
                        return True
        return False

    def count_of_event(self, event: tuple, within: int = TIME_ANY) -> int:
        count = 0
        for h in self.history:
            if h.msg.get_node_number() == event[1] and h.msg.get_event_number() == event[2]:
                if event[0] == canmessage.POLARITY_EITHER or (
                        event[0] == canmessage.POLARITY_ON and not (h.msg.data[0] & 1)) or (
                        event[0] == canmessage.POLARITY_OFF and (h.msg.data[0] & 1)):
                    if within == TIME_ANY or h.arrival_time > (time.ticks_ms() - within):
                        count += 1
        return count

    def event_exists(self, event: tuple, within: int = TIME_ANY) -> bool:
        return self.count_of_event(event, within) > 0

    def time_received(self, event: tuple, which: int = WHICH_ANY) -> int:
        times = []
        for h in self.history:
            if h.msg.get_node_number() == event[1] and h.msg.get_event_number() == event[2]:
                if event[0] == canmessage.POLARITY_EITHER or (
                        event[0] == canmessage.POLARITY_ON and not (h.msg.data[0] & 1)) or (
                        event[0] == canmessage.POLARITY_OFF and (h.msg.data[0] & 1)):
                    if which == WHICH_ANY:
                        return h.arrival_time
                    else:
                        times.append(h.arrival_time)

        if len(times) > 0:
            times.sort()
            if which == WHICH_EARLIEST:
                return times[0]
            elif which == WHICH_LATEST:
                return times[-1]

        return TIME_NOT_FOUND

    def received_before(self, event1: tuple, event2: tuple) -> bool:
        return self.time_received(event1) < self.time_received(event2)

    def received_after(self, event1: tuple, event2: tuple) -> bool:
        return self.time_received(event1) > self.time_received(event2)

    def received_in_order(self, event1: tuple, event2: tuple, order: int = ORDER_BEFORE) -> bool:
        if order == ORDER_BEFORE:
            return self.received_before(event1, event2)
        else:
            return self.received_after(event1, event2)

    def current_event_state(self, event: tuple) -> int:
        state = canmessage.POLARITY_UNKNOWN
        earliest_time = 0

        for h in self.history:
            if h.msg.get_node_number() == event[1] and h.msg.get_event_number() == event[2]:
                if h.arrival_time > earliest_time:
                    earliest_time = h.arrival_time
                    state = (canmessage.POLARITY_OFF if (h.msg.data[0] & 1) else canmessage.POLARITY_ON)

        return state

    def time_of_last_message(self, polarity: int = canmessage.POLARITY_EITHER, match_events_only: bool = True) -> int:
        latest_time = 0

        for h in self.history:
            match = False

            if match_events_only and h.msg.is_event():
                if polarity == canmessage.POLARITY_EITHER or (
                        polarity == canmessage.POLARITY_OFF and h.msg.data[0] & 1) or (
                        polarity == canmessage.POLARITY_ON and not (h.msg.data[0] & 1)):
                    match = True
            elif not match_events_only:
                match = True

            if match and latest_time < h.arrival_time:
                latest_time = h.arrival_time

        return latest_time

    def time_diff(self, events: tuple, within: int = TIME_ANY, timespan: int = WINDOW_ANY,
                  which: int = WHICH_ANY) -> int | None:
        atimes = []

        if len(events) < 2:
            return None

        for event in events:
            etime = self.time_received(event, which)

            if etime == TIME_NOT_FOUND:
                return None
            else:
                if within == TIME_ANY or (etime > time.ticks_ms() - within):
                    atimes.append(etime)

        if timespan == WINDOW_ANY or abs(atimes[-1] - atimes[0]) <= timespan:
            return atimes[-1] - atimes[0]
        else:
            return None

    def sequence_received(self, events: tuple, order: int = ORDER_ANY, within: int = TIME_ANY, window: int = TIME_ANY,
                          which: int = WHICH_ANY) -> bool:
        times = []

        if self.count() < 1 or len(events) < 1:
            return False

        for event in events:
            etime = self.time_received(event, which)

            if etime == TIME_NOT_FOUND:
                return False
            else:
                if within == TIME_ANY or (etime > time.ticks_ms() - within):
                    times.append(etime)

        if len(times) == len(events):
            if order == ORDER_GIVEN:
                for i in range(len(times) - 1):
                    if times[i] > times[i + 1]:
                        return False
            elif order == ORDER_REVERSE:
                for i in range(len(times) - 1):
                    if times[i] < times[i + 1]:
                        return False
        else:
            return False

        if window != WINDOW_ANY:
            times.sort()
            if times[len(times) - 1] - times[0] > window:
                return False

        return True

    def any_received(self, events: tuple, within: int = TIME_ANY) -> bool:
        for ev in events:
            if self.event_exists(ev, within):
                return True
        return False
