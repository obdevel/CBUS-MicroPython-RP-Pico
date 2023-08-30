# circularQueue.py

import uasyncio as asyncio

import canmessage


class circularQueue:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.queue = [None] * capacity
        self.tail = -1
        self.head = 0
        self.size = 0
        self.hwm = 0
        self.dropped = 0
        self.puts = 0
        self.gets = 0
        self.lock = asyncio.Lock()

    async def available(self) -> bool:
        await self.lock.acquire()
        size = self.size
        self.lock.release()
        return size > 0

    async def enqueue(self, item: canmessage.canmessage) -> None:
        if self.size == self.capacity:
            self.dropped = self.dropped + 1
            print('queue is full')
        else:
            await self.lock.acquire()
            self.tail = (self.tail + 1) % self.capacity
            self.queue[self.tail] = item
            self.size = self.size + 1
            self.hwm = self.hwm + 1 if self.size > self.hwm else self.hwm
            self.puts += 1
            self.lock.release()
            # print('enqueued new message')

    async def dequeue(self) -> canmessage.canmessage | None:
        if self.size == 0:
            print('nothing to dequeue')
            return None
        else:
            await self.lock.acquire()
            tmp = self.queue[self.head]
            self.queue[self.head] = None
            self.head = (self.head + 1) % self.capacity
            self.size = self.size - 1
            self.gets += 1
            self.lock.release()
            # print('item dequeued')
            return tmp

    # def peek(self):
    #     if self.size == 0:
    #         return None
    #     else:
    #         return self.queue[self.head]

    # def empty(self):
    #     self.tail = -1
    #     self.head = 0
    #     self.size = 0
    #     self.hwm = 0
    #     self.dropped = 0

    # def display(self):
    #     index = self.head
    #
    #     for i in range(self.size):
    #         print(self.queue[index])
    #         index = (index + 1) % self.capacity
