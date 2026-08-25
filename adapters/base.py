from abc import ABC, abstractmethod

class GoldAdapter(ABC):
    @abstractmethod
    def login(self): pass

    @abstractmethod
    def get_price(self): pass

    @abstractmethod
    def buy(self, amount): pass

    @abstractmethod
    def sell(self, amount): pass
