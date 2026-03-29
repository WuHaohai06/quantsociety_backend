from abc import ABC, abstractmethod


class ResultStore(ABC):
    @abstractmethod
    def write(self, factor_name: str, result) -> None:
        raise NotImplementedError
