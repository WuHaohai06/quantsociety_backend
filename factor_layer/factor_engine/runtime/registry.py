class Registry:
    def __init__(self) -> None:
        self._items: dict[str, object] = {}

    def register(self, name: str, item: object) -> None:
        self._items[name] = item

    def get(self, name: str) -> object:
        return self._items[name]
