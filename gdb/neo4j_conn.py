import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import asyncio
from neo4j import GraphDatabase, AsyncGraphDatabase
from neo4j.exceptions import TransientError

class Neo4jConnectionBase(ABC):
    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None):
        pass
    
class AsyncNeo4jConnection:
    def __init__(self, uri: str, user: str, pwd: str):
        self.__uri = uri
        self.__user = user
        self.__pwd = pwd
        self.__driver = None
        self.logger = logging.getLogger(__name__)

    async def connect(self):
        try:
            self.__driver = AsyncGraphDatabase.driver(self.__uri, auth=(self.__user, self.__pwd))
            await self.__driver.verify_connectivity()
            self.logger.info("Successfully connected to Neo4j database.")
        except Exception as e:
            self.logger.error(f"Failed to connect to Neo4j: {str(e)}")
            raise

    async def close(self):
        if self.__driver is not None:
            await self.__driver.close()
            self.logger.info("Neo4j connection closed.")

    async def retry_with_backoff(self, func, *args, **kwargs):
        max_retries = 5
        base_delay = 1
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                delay = base_delay * (2 ** attempt)
                self.logger.error(f"Transient error occurred: {type(e).__name__}: {str(e)}. Retrying in {delay} seconds. Attempt {attempt+1}/{max_retries}")
                await asyncio.sleep(delay)


    async def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if self.__driver is None:
            await self.connect()

        async def run_query():
            async with self.__driver.session() as session:
                result = await session.run(query, parameters)
                records = await result.fetch(n=-1)  # Fetch all records
                return [record.data() for record in records]

        try:
            return await self.retry_with_backoff(run_query)
        except Exception as e:
            self.logger.error(f"Query execution failed: {query}")
            self.logger.error(f"Parameters: {parameters}")
            self.logger.error(f"Error: {str(e)}")
            raise

    async def execute_write_transaction(self, transaction_function, *args, **kwargs):
        if self.__driver is None:
            await self.connect()

        async def run_transaction():
            async with self.__driver.session() as session:
                return await session.execute_write(transaction_function, *args, **kwargs)

        try:
            return await self.retry_with_backoff(run_transaction)
        except Exception as e:
            self.logger.error(f"Write transaction failed: {transaction_function.__name__}")
            self.logger.error(f"Args: {args}, Kwargs: {kwargs}")
            self.logger.error(f"Error: {str(e)}")
            raise

    async def execute_read_transaction(self, transaction_function, *args, **kwargs):
        if self.__driver is None:
            await self.connect()

        async def run_transaction():
            async with self.__driver.session() as session:
                return await session.execute_read(transaction_function, *args, **kwargs)

        try:
            return await self.retry_with_backoff(run_transaction)
        except Exception as e:
            self.logger.error(f"Read transaction failed: {transaction_function.__name__}")
            self.logger.error(f"Args: {args}, Kwargs: {kwargs}")
            self.logger.error(f"Error: {str(e)}")
            raise

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

class SyncNeo4jConnection(Neo4jConnectionBase):
    def __init__(self, uri: str, user: str, pwd: str):
        self.__uri = uri
        self.__user = user
        self.__pwd = pwd
        self.__driver = None
        try:
            self.__driver = GraphDatabase.driver(self.__uri, auth=(self.__user, self.__pwd))
            logging.info("Sync Neo4j connection initialised")
        except Exception as e:
            logging.error(f"Failed to create the sync driver: {e}")
            raise

    def close(self):
        if self.__driver is not None:
            self.__driver.close()
            logging.info("Sync Neo4j connection closed")

    def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if self.__driver is None:
            raise ValueError("Driver not initialised!")
        with self.__driver.session() as session:
            return session.execute_write(self.__execute_query, query, parameters)

    @staticmethod
    def __execute_query(tx, query: str, parameters: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = tx.run(query, parameters)
        return [record.data() for record in result]

class AsyncNeo4jConnectionOLD(Neo4jConnectionBase):
    def __init__(self, uri: str, user: str, pwd: str):
        self.__uri = uri
        self.__user = user
        self.__pwd = pwd
        self.__driver = None
        try:
            self.__driver = AsyncGraphDatabase.driver(self.__uri, auth=(self.__user, self.__pwd))
            logging.info("Async Neo4j connection initialised")
        except Exception as e:
            logging.error(f"Failed to create the async driver: {e}")
            raise

    async def close(self):
        if self.__driver is not None:
            await self.__driver.close()
            logging.info("Async Neo4j connection closed")

    async def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if self.__driver is None:
            raise ValueError("Driver not initialised!")
        async with self.__driver.session() as session:
            return await session.execute_write(self.__execute_query, query, parameters)

    @staticmethod
    async def __execute_query(tx, query: str, parameters: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = await tx.run(query, parameters)
        return [record.data() async for record in result]
