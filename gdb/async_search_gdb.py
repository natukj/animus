import asyncio
import ast
import datetime
import pandas as pd
from typing import List, Dict, Any, Optional
import gdb

class AsyncNeo4jSearch(gdb.AsyncNeo4jConnectionSimple):
    def __init__(self, uri: str, user: str, pwd: str):
        super().__init__(uri, user, pwd)

    # async def init(self):
    #     await self.connect()
    #     print("Connected to Neo4j")

    async def close(self):
        await super().close()

    async def check_num_nodes(self):
        query = """
        MATCH (n)
        RETURN count(n) AS count
        """
        results = await self.execute_query(query)
        return results

    async def check_index(self, index_name: str):
        query = """
        SHOW VECTOR INDEXES
        WHERE name = $index_name
        """
        print(f"Checking index: {index_name}")
        params = {'index_name': index_name}
        results = await self.execute_query(query, params)
        print(f"Index information: {results}")
        return results
    
    async def basic_vector_search(self, embedding: List[float], top_k: int = 5):
        query = """
        MATCH (n)
        WHERE n.embedding IS NOT NULL
        WITH n, gds.similarity.cosine(n.embedding, $embedding) AS similarity
        ORDER BY similarity DESC
        LIMIT $top_k
        RETURN n.id AS id, n.title AS title, similarity
        """
        parameters = {'embedding': embedding, 'top_k': top_k}
        return await self.execute_query(query, parameters)
    
    async def search_by_embedding(self, embedding: List[float], index_name: str, top_k: int = 5) -> List[Dict[str, Any]]:
        query = f"""
        CALL db.index.vector.queryNodes(
        '{index_name}',
        {top_k},
        {embedding}
        )
        YIELD node, score
        RETURN node.id AS id, node.title AS title, node.content AS content, score
        ORDER BY score DESC
        """
        return await self.execute_query(query)



    async def check_embedding_status(self):
        count_query = "MATCH (n) WHERE n.embedding IS NOT NULL RETURN count(n) AS count"
        sample_query = "MATCH (n) WHERE n.embedding IS NOT NULL RETURN n.embedding AS sample LIMIT 1"
        
        count_result = await self.execute_query(count_query)
        sample_result = await self.execute_query(sample_query)

        count = count_result
        sample = sample_result

        return {
            'total_nodes_with_embedding': count,
            'sample_embedding_type': type(sample).__name__,
            'sample_embedding_length': len(sample) if isinstance(sample, (list, str)) else None
        }
    
    async def convert_string_embeddings_to_lists(self):
        query = """
        MATCH (n)
        WHERE n.embedding IS NOT NULL AND n.embedding STARTS WITH '['
        SET n.embedding = [x IN split(substring(n.embedding, 1, size(n.embedding)-2), ',') | toFloat(trim(x))]
        RETURN count(n) AS converted
        """
        result = await self.execute_query(query)
        return result

    async def search_by_cluster(self, cluster: int, label: str) -> List[Dict[str, Any]]:
        query = f"""
        MATCH (n:{label}) WHERE n.cluster = $cluster
        RETURN n.id AS id, n.title AS title, n.content AS content
        """
        params = {'cluster': cluster}
        results = await self.execute_query(query, params)
        return results

    async def search_by_attributes(self, label: str, attributes: Dict[str, Any]) -> List[Dict[str, Any]]:
        conditions = ' AND '.join([f"n.{k} = ${k}" for k in attributes.keys()])
        query = f"""
        MATCH (n:{label})
        WHERE {conditions}
        RETURN n.id AS id, n.title AS title, n.content AS content
        """
        results = await self.execute_query(query, attributes)
        return results

    async def combined_search(self, embedding: List[float], cluster: int, index_name: str, label: str, top_k: int = 5) -> List[Dict[str, Any]]:
        query = f"""
        CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
        YIELD node, score
        WHERE node:{label} AND node.cluster = $cluster
        RETURN node.id AS id, node.title AS title, node.content AS content, score
        ORDER BY score DESC
        """
        params = {'index_name': index_name, 'top_k': top_k, 'embedding': embedding, 'cluster': cluster}
        results = await self.execute_query(query, params)
        return results

    async def search_related_nodes(self, node_id: str, relationship_type: str, direction: str = 'OUTGOING') -> List[Dict[str, Any]]:
        direction_arrow = '->' if direction == 'OUTGOING' else '<-'
        query = f"""
        MATCH (n {{id: $node_id}}){direction_arrow}[r:{relationship_type}](related)
        RETURN related.id AS id, related.title AS title, related.content AS content, type(r) AS relationship_type
        """
        params = {'node_id': node_id}
        results = await self.execute_query(query, params)
        return results

    async def get_node_by_id(self, node_id: str) -> Optional[Dict[str, Any]]:
        query = """
        MATCH (n {id: $node_id})
        RETURN n
        """
        params = {'node_id': node_id}
        results = await self.execute_query(query, params)
        return results[0]['n'] if results else None