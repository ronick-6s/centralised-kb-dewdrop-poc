from abc import ABC, abstractmethod
from typing import List
from core.document import Document

class BaseConnector(ABC):
    @abstractmethod
    def connect(self) -> None:
        pass

    @abstractmethod
    def fetch_documents(self) -> List[Document]:
        pass
