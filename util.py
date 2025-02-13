import time


class timer():
    def __init__(self):
        self.t0 = time.time()
    
    def elapsed(self):
        return time.time() - self.t0
    
    def reset(self):
        t1 = time.time()
        elapsed = t1 - self.t0
        self.t0 = t1
        return elapsed