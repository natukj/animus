import logging
import asyncio
import ast
import datetime
import pandas as pd
from typing import List, Dict, Any, Optional
import gdb

@staticmethod
def parse_references(x):
    if pd.isna(x):
        return []
    if isinstance(x, str):
        try:
            refs = ast.literal_eval(x)
        except (ValueError, SyntaxError):
            refs = x.split(',') if ',' in x else [x]
    elif isinstance(x, list):
        refs = x
    else:
        return []
    return [ref.strip() for ref in refs if ref.strip() != '995-1']

class AsyncGraphDatabaseBuilder(gdb.AsyncNeo4jConnection):
    def __init__(self, uri: str, user: str, pwd: str, max_concurrency: int = 1):
        super().__init__(uri, user, pwd)
        # TODO WORK OUT WHY SEMAPHORE > 1 CAUSES DEADLOCK
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.logger = logging.getLogger(__name__)

    async def init(self):
        await self.connect()
        self.logger.info("Connected to Neo4j")

    async def close(self):
        await super().close()

    async def clear_database(self):
        queries = [
            "MATCH (n) DETACH DELETE n"
        ]
        for query in queries:
            await self.execute_query(query)
        print("Database cleared, all constraints and indexes dropped")

    async def process(self, coroutine):
        async with self.semaphore:
            task_id = id(coroutine)
            self.logger.debug(f"Starting task {task_id}")
            try:
                result = await coroutine
                self.logger.debug(f"Completed task {task_id}")
                return result
            except Exception as e:
                self.logger.error(f"Error in task {task_id}: {str(e)}")
                raise


    async def create_constraints_and_indexes(self):
        queries = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Section) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Content) REQUIRE c.id IS UNIQUE",
            # id to easily search by doc as id starts w doc id
            "CREATE INDEX IF NOT EXISTS FOR (s:Section) ON (s.id)",
            "CREATE INDEX IF NOT EXISTS FOR (c:Content) ON (c.id)",
            # title
            "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.title)",
            "CREATE INDEX IF NOT EXISTS FOR (s:Section) ON (s.title)",
            "CREATE INDEX IF NOT EXISTS FOR (c:Content) ON (c.title)",
            # fulltext
            "CREATE FULLTEXT INDEX IF NOT EXISTS content_fulltext FOR (c:Content) ON EACH [c.content]",
        ]
        for query in queries:
            await self.execute_query(query)
        self.logger.info("Constraints and indexes created")

    async def create_vector_index(self, index_name: str, label: str, property_name: str, dimensions: int = 1536):
        query = f"""
        CREATE VECTOR INDEX {index_name} IF NOT EXISTS
        FOR (n:{label})
        ON n.{property_name}
        OPTIONS {{indexConfig: {{
            `vector.dimensions`: {dimensions},
            `vector.similarity_function`: 'cosine'
        }}}}
        """
        await self.execute_query(query)

    async def create_relationship_vector_index(self, index_name: str, rel_type: str, property_name: str, dimensions: int = 1536):
        query = f"""
        CREATE VECTOR INDEX {index_name} IF NOT EXISTS
        FOR ()-[r:{rel_type}]-() ON (r.{property_name})
        OPTIONS {{indexConfig: {{
            `vector.dimensions`: {dimensions},
            `vector.similarity_function`: 'cosine'
        }}}}
        """
        await self.execute_query(query)

    async def add_document(self, doc_id: str, title: str, doc_tags: List[str], metadata: Dict[str, Any]):
        query = """
        MERGE (d:Document {id: $id})
        SET d.title = $title, 
            d.tags = [tag IN $tags WHERE tag IS NOT NULL],
            d.jurisdiction = $jurisdiction,
            d.year = $year,
            d.volumes = $volumes,
            d.added = $added
        """
        params = {
            'id': doc_id, 
            'title': title, 
            'tags': [str(tag) for tag in doc_tags if tag is not None],
            'jurisdiction': metadata.get('jurisdiction'),
            'year': metadata.get('year'),
            'volumes': metadata.get('volumes'),
            'added': metadata.get('added')
        }
        await self.execute_query(query, params)

    async def add_section_node(self, doc_id: str, section_path: str, title: str, depth: int, 
                           self_ref: str, cluster: int,
                           content: Optional[str] = None,
                           embedding: Optional[List[float]] = None,
                           metadata: Optional[Dict[str, Any]] = None):
        section_id = f"{doc_id}||{section_path}"
        
        query = """
        MERGE (s:Section {id: $section_id})
        SET s.title = $title,
            s.depth = $depth,
            s.self_ref = $self_ref,
            s.content = $content,
            s.cluster = $cluster,
            s.added = $added
        """
        
        if embedding is not None:
            query += ", s.embedding = $embedding"
        
        params = {
            'section_id': section_id,
            'title': title,
            'depth': depth,
            'self_ref': self_ref,
            'content': content,
            'cluster': cluster,
            'added': metadata.get('added') if metadata else None
        }
        
        if embedding is not None:
            params['embedding'] = embedding
        
        await self.execute_query(query, params)

    async def add_content_node(self, doc_id: str, content_path: str, title: str, 
                           content: str, self_ref: str, cluster: int, 
                           embedding: Optional[List[float]] = None,
                           metadata: Optional[Dict[str, Any]] = None):
        content_id = f"{doc_id}||{content_path}"
        
        query = """
        MERGE (c:Content {id: $content_id})
        SET c.title = $title,
            c.content = $content,
            c.self_ref = $self_ref,
            c.cluster = $cluster,
            c.summary = $summary,
            c.added = $added
        """
        
        if embedding is not None:
            query += ", c.embedding = $embedding"
        
        params = {
            'content_id': content_id,
            'title': title,
            'content': content,
            'self_ref': self_ref,
            'cluster': cluster,
            'summary': metadata.get('summary') if metadata else None,
            'added': metadata.get('added') if metadata else None
        }
        
        if embedding is not None:
            params['embedding'] = embedding
        
        await self.execute_query(query, params)

    async def add_contains_relationship(self, doc_id: str, path: str, parent_path: Optional[str] = None):
        child_id = f"{doc_id}||{path}"
        
        if parent_path is None:
            query = """
            MATCH (d:Document {id: $doc_id})
            MATCH (child {id: $child_id})
            MERGE (d)-[:CONTAINS]->(child)
            """
            params = {
                'doc_id': doc_id,
                'child_id': child_id
            }
        else:
            parent_id = f"{doc_id}||{parent_path}"
            query = """
            MATCH (parent {id: $parent_id})
            MATCH (child {id: $child_id})
            MERGE (parent)-[:CONTAINS]->(child)
            """
            params = {
                'parent_id': parent_id,
                'child_id': child_id
            }
        await self.execute_query(query, params)

    async def add_references(self, doc_id: str, path: str, references: List[str]):
        # NOTE not sure about this self_ref system
        source_id = f"{doc_id}||{path}"
        
        query = """
        MATCH (source {id: $source_id})
        UNWIND $references AS ref
        MATCH (target)
        WHERE target.self_ref = ref AND target.id STARTS WITH $doc_id
        MERGE (source)-[:REFERENCES]->(target)
        """
        
        params = {
            'source_id': source_id,
            'doc_id': doc_id,
            'references': references
        }
        await self.execute_query(query, params)

    async def build_document_graph_from_df(self,
                                           df: pd.DataFrame, 
                                           doc_id: str, title: str, doc_tags: List[str], 
                                           metadata: Dict[str, Any]):
        self.logger.info(f"Building graph for document {doc_id}: {title}")
        current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.process(self.add_document(doc_id, title, doc_tags, {**metadata, 'added': current_date}))

        section_tasks = []
        for _, row in df[df['hierarchy_level'] > 0].iterrows():
            task = self.process(self.add_section_node(
                doc_id=doc_id,
                section_path=row['path'],
                title=row['title'],
                depth=int(row['depth']),
                self_ref=row['self_ref'],
                cluster=int(row['d_cluster']),
                content=row['content'],
                embedding=row['embedding'],
                metadata={
                    'added': current_date
                }
            ))
            section_tasks.append(task)

        content_tasks = []
        for _, row in df[df['hierarchy_level'] == 0].iterrows():
            task = self.process(self.add_content_node(
                doc_id=doc_id,
                content_path=row['path'],
                title=row['title'],
                content=row['content'],
                self_ref=row['self_ref'],
                cluster=int(row['hl_cluster']),
                embedding=row['embedding'],
                metadata={
                    'summary': row['summary'],
                    'added': current_date
                }
            ))
            content_tasks.append(task)

        self.logger.info(f"Starting to create {len(section_tasks)} section nodes and {len(content_tasks)} content nodes")
        await asyncio.gather(*section_tasks, *content_tasks)
        self.logger.info(f"Nodes created for document {doc_id}")
        # CONTAINS relationships
        contain_tasks = []
        for _, row in df.iterrows():
            parent_path = row['parent_path'] if pd.notna(row['parent_path']) else None
            task = self.process(self.add_contains_relationship(doc_id, row['path'], parent_path))
            contain_tasks.append(task)
        self.logger.info(f"Starting to create {len(contain_tasks)} CONTAINS relationships")
        await asyncio.gather(*contain_tasks)
        self.logger.info(f"CONTAINS relationships created for document {doc_id}")
        # REFERENCES relationships
        reference_tasks = []
        df['references'] = df['references'].apply(parse_references)
        for _, row in df.iterrows():
            if row['references']:
                task = self.process(self.add_references(doc_id, row['path'], row['references']))
                reference_tasks.append(task)

        self.logger.info(f"Starting to create {len(reference_tasks)} REFERENCES relationships")
        await asyncio.gather(*reference_tasks)
        self.logger.info(f"REFERENCES relationships created for document {doc_id}")
        # create indexes
        await self.create_constraints_and_indexes()       
        embedding_dim = len(df['embedding'].iloc[0]) if pd.notna(df['embedding'].iloc[0]) else 1536
        await self.create_vector_index("section_embedding", "Section", "embedding", dimensions=embedding_dim)
        await self.create_vector_index("content_embedding", "Content", "embedding", dimensions=embedding_dim)

        self.logger.info(f"Graph built for document {doc_id}")