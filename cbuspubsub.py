# cbuspubsub.py
# publish/subscribe implementation of the observer pattern

import random
import re

import canmessage
import logger
from primitives import Queue


class subscription:
    def __init__(self, name: str, cbus, query, query_type: int):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.id = random.randint(0, 65535)      # TODO: check unique
        self.query = query
        self.query_type = query_type
        self.regex = None
        self.queue = Queue()
        if type == canmessage.QUERY_REGEX:
            self.regex = re.compile(query)
        self.subscribe()

    def subscribe(self) -> None:
        self.cbus.add_subscription(self)

    def unsubscribe(self) -> None:
        self.cbus.remove_subscription(self)

    def publish(self, msg: canmessage.canmessage) -> None:
        if msg.matches(self.query_type, self.query):
            self.queue.put_nowait(msg)

    async def wait(self):
        return await self.queue.get()
