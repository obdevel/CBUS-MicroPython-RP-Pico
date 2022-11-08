# cbuspubsub.py
# publish/subscribe pattern from coroutines

import canmessage
import cbus
import logger
import uasyncio as asyncio
import queue
import random
import re


class subscription:
    def __init__(self, cbus, query, type):
        self.logger = logger.logger()
        self.cbus = cbus
        self.id = random.randint(0, 65535)
        self.type = type
        self.query = query
        self.regex = None
        self.queue = queue.Queue()
        if type == canmessage.QUERY_REGEX:
            self.regex = re.compile(query)
        self.subscribe()

    def subscribe(self):
        self.cbus.add_subscription(self)

    def unsubscribe(self, request):
        self.logger.log("unsubscribe")
        self.cbus.remove_subscription(request)

    def publish(self, msg):
        if msg.matches(self.type, self.query):
            self.queue.put_nowait(msg)

    async def wait(self):
        return await self.queue.get()


