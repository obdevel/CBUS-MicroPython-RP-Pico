# cbuspubsub.py
# publish/subscribe implementation of the observer pattern

import re
from random import randint

import uasyncio as asyncio

import canmessage
import logger
from primitives import Queue


class subscription:
    def __init__(self, name: str, cbus, query_type: int, query):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.id = randint(0, 65535)  # TODO: check unique
        self.query = query
        self.query_type = query_type
        self.regex = None
        self.evt = asyncio.Event()
        self.queue = Queue()
        if type == canmessage.QUERY_REGEX:
            self.regex = re.compile(query)
        self.subscribe()

        self.logger.log(f'subscription: query_type = {self.query_type}, query = {self.query}')

    def subscribe(self) -> None:
        self.cbus.add_subscription(self)

    def unsubscribe(self) -> None:
        self.cbus.remove_subscription(self)

    def publish(self, msg: canmessage.canmessage) -> None:
        self.logger.log(f'subscription: publish, query_type = {self.query_type}, query = {self.query}')

        if msg.matches(self.query_type, self.query):
            self.queue.put_nowait(msg)
            self.evt.set()

    async def wait(self):
        self.evt.clear()
        item = await self.queue.get()
        self.evt.set()
        return item
