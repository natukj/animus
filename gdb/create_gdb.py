import logging
import ast
import datetime
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
import gdb

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
    return [ref.strip() for ref in refs if '995' not in ref]

def convert_embedding(embedding):
    if isinstance(embedding, str):
        try:
            return [float(x) for x in ast.literal_eval(embedding)]
        except:
            return None
    elif isinstance(embedding, (list, np.ndarray)):
        return [float(x) for x in embedding]
    return None

class SyncGraphDatabaseBuilder(gdb.SyncNeo4jConnection):
    def __init__(self, uri: str, user: str, pwd: str, batch_size: int = 100):
        super().__init__(uri, user, pwd)
        self.batch_size = batch_size
        self.logger = logging.getLogger(__name__)

    def clear_database(self):
        queries = [
            "MATCH (n) DETACH DELETE n"
        ]
        for query in queries:
            self.execute_query(query)
        print("Database cleared, all constraints and indexes dropped")

    def create_constraints_and_indexes(self):
        queries = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Section) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Content) REQUIRE c.id IS UNIQUE",
            "CREATE INDEX IF NOT EXISTS FOR (s:Section) ON (s.id)",
            "CREATE INDEX IF NOT EXISTS FOR (c:Content) ON (c.id)",
            "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.title)",
            "CREATE INDEX IF NOT EXISTS FOR (s:Section) ON (s.title)",
            "CREATE INDEX IF NOT EXISTS FOR (c:Content) ON (c.title)",
            "CREATE FULLTEXT INDEX IF NOT EXISTS content_fulltext FOR (c:Content) ON EACH [c.content]",
        ]
        for query in queries:
            self.execute_query(query)
        self.logger.info("Constraints and indexes created")

    def create_vector_index(self, index_name: str, label: str, property_name: str, dimensions: int = 1536):
        query = f"""
        CREATE VECTOR INDEX {index_name} IF NOT EXISTS
        FOR (n:{label})
        ON n.{property_name}
        OPTIONS {{indexConfig: {{
            `vector.dimensions`: {dimensions},
            `vector.similarity_function`: 'cosine'
        }}}}
        """
        self.execute_query(query)

    def create_relationship_vector_index(self, index_name: str, rel_type: str, property_name: str, dimensions: int = 1536):
        query = f"""
        CREATE VECTOR INDEX {index_name} IF NOT EXISTS
        FOR ()-[r:{rel_type}]-() ON (r.{property_name})
        OPTIONS {{indexConfig: {{
            `vector.dimensions`: {dimensions},
            `vector.similarity_function`: 'cosine'
        }}}}
        """
        self.execute_query(query)

    def add_document(self, doc_id: str, title: str, doc_tags: List[str], metadata: Dict[str, Any]):
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
        self.execute_query(query, params)

    def add_nodes_batch(self, nodes):
        query = """
        UNWIND $nodes AS node
        MERGE (n {id: node.id})
        SET n = node
        """
        self.execute_query(query, {'nodes': nodes})

    def add_relationships_batch(self, relationships):
        query = """
        UNWIND $relationships AS rel
        MATCH (source {id: rel.source_id})
        MATCH (target {id: rel.target_id})
        MERGE (source)-[:CONTAINS]->(target)
        """
        self.execute_query(query, {'relationships': relationships})

    def add_references_batch(self, references):
        query = """
        UNWIND $references AS ref
        MATCH (source {id: ref.source_id})
        MATCH (target)
        WHERE target.self_ref = ref.target_ref AND target.id STARTS WITH ref.doc_id
        MERGE (source)-[:REFERENCES]->(target)
        """
        self.execute_query(query, {'references': references})

    def build_document_graph_from_df(self, df: pd.DataFrame, doc_id: str, title: str, doc_tags: List[str], 
                                     metadata: Dict[str, Any]):
        self.logger.info(f"Building graph for document {doc_id}: {title}")
        current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.add_document(doc_id, title, doc_tags, {**metadata, 'added': current_date})

        nodes = []
        relationships = []
        references = []

        for _, row in df.iterrows():
            node = {
                'id': f"{doc_id}||{row['path']}",
                'title': row['title'],
                'depth': int(row['depth']),
                'self_ref': row['self_ref'],
                'content': row['content'],
                'cluster': int(row['d_cluster'] if row['hierarchy_level'] > 0 else row['hl_cluster']),
                'added': current_date
            }
            
            if pd.notna(row['embedding']):
                node['embedding'] = convert_embedding(row['embedding'])

            if row['hierarchy_level'] == 0:
                node['summary'] = row['summary']
                node['labels'] = ':Content'
            else:
                node['labels'] = ':Section'

            nodes.append(node)

            if pd.notna(row['parent_path']):
                relationships.append({
                    'source_id': f"{doc_id}||{row['parent_path']}",
                    'target_id': f"{doc_id}||{row['path']}"
                })
            else:
                relationships.append({
                    'source_id': doc_id,
                    'target_id': f"{doc_id}||{row['path']}"
                })

            refs = parse_references(row['references'])
            for ref in refs:
                references.append({
                    'source_id': f"{doc_id}||{row['path']}",
                    'target_ref': ref,
                    'doc_id': doc_id
                })

        for i in range(0, len(nodes), self.batch_size):
            batch = nodes[i:i+self.batch_size]
            self.add_nodes_batch(batch)

        for i in range(0, len(relationships), self.batch_size):
            batch = relationships[i:i+self.batch_size]
            self.add_relationships_batch(batch)

        for i in range(0, len(references), self.batch_size):
            batch = references[i:i+self.batch_size]
            self.add_references_batch(batch)

        #self.create_constraints_and_indexes()
        
        embedding_dim = len(df['embedding'].iloc[0]) if pd.notna(df['embedding'].iloc[0]) else 1536
        self.create_vector_index("section_embedding", "Section", "embedding", dimensions=embedding_dim)
        self.create_vector_index("content_embedding", "Content", "embedding", dimensions=embedding_dim)

        self.logger.info(f"Graph built for document {doc_id}")
