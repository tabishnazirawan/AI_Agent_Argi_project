import threading

class KeyManager:
    def __init__(self, keys: list):
        self._keys = keys
        self._index = 0
        self._lock = threading.Lock()  # Multi-threading safe

    def get_key(self) -> str:
        with self._lock:
            key = self._keys[self._index]
            self._index = (self._index + 1) % len(self._keys)
            return key

    def get_next_key(self) -> str:
        """429 par call karein — ek aur advance karta hai"""
        return self.get_key()
