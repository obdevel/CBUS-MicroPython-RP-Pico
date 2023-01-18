# canio.py
import canmessage
import logger


class canio:
    def __init__(self):
        self.logger = logger.logger()
        self.rx_queue = None
        self.tx_queue = None

    def begin(self) -> None:
        pass

    def send_message(self, msg: canmessage) -> int:
        pass

    async def get_next_message(self) -> canmessage.canmessage:
        pass

    async def available(self) -> bool:
        pass

    def poll_for_messages(self) -> None:
        pass

    def reset(self) -> None:
        pass
