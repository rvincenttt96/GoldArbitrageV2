from abc import ABC, abstractmethod


class Exchange(ABC):


    @abstractmethod
    def get_price(self, side):
        pass


    @abstractmethod
    def get_balance(self):
        pass


    @abstractmethod
    def buy(self, amount):
        pass


    @abstractmethod
    def sell(self, amount):
        pass


    @abstractmethod
    def get_order(self, order_id):
        pass
