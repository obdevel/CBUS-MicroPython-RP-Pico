# module.py
# cbus application base class

class cbusmodule():
    
    def __init__(self):
        print('** cbusmodule constructor')
        pass

    def initialise(self):
        pass

    def run_cbus_loop(self):
        pass

    def run(self):
        pass

    def event_handler(self, msg, idx):
        print(f'-- user event handler: idx = {idx}')
        print(msg)

    def frame_handler(self, msg):
        print('-- user frame handler:')
        print(msg)

    def long_message_handler(self, message, streamid, status):
        print(f'-- user long message handler: status = {status}, streamid = {streamid}, msg = <{message}>')
        print()
