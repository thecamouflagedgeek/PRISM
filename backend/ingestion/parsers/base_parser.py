from abc import ABC, abstractmethod

class BaseParser(ABC):
    @abstractmethod
    def extract(self, file_path:str):
        pass
    @abstractmethod
    def validate(self, df):
        pass
    @abstractmethod
    def transform(self, df):
        pass