from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
import gdb, utils

def sync_vector_search(uri, user, password, embedding, index_name, top_k):
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session() as session:
            query = """
            CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
            YIELD node, score
            RETURN node.id AS id, node.title AS title, node.content AS content, score
            ORDER BY score DESC
            """
            parameters = {
                'index_name': index_name,
                'top_k': top_k,
                'embedding': embedding
            }
            result = session.run(query, parameters)
            return [record.data() for record in result]

class Neo4jSearch(gdb.SyncNeo4jConnection):
    def __init__(self, uri: str, user: str, pwd: str):
        super().__init__(uri, user, pwd)

    def by_embedding(self,
                doc_id: str, 
                embedding: List[float], 
                index_name: str, 
                top_k: int = 5, 
                depth: List[int] = None, 
                cluster: int = None,
                id_startswith: str = None,
                return_refs: bool = False) -> List[Dict[str, Any]]:
        query = """
        CALL db.index.vector.queryNodes($index_name, 10000, $embedding)
        YIELD node, score
        WHERE 1=1
        """

        if depth is not None:
            query += " AND node.depth IN $depth"
        
        if cluster is not None:
            query += " AND node.cluster = $cluster"

        if id_startswith is not None:
            query += " AND node.id STARTS WITH $id_startswith"
        else:
            query += " AND node.id STARTS WITH $doc_id"

        if return_refs:
            query += """
            WITH node, score
            OPTIONAL MATCH (node)-[r:REFERENCES]->(ref:Content)
            WITH node, score, COLLECT(DISTINCT CASE WHEN ref IS NOT NULL 
                    THEN {
                        id: ref.id, 
                        title: ref.title, 
                        content: ref.content, 
                        cluster: ref.cluster
                    }
                    ELSE NULL END) AS refs
            """

        if index_name == "section_embedding":
            query += """
            RETURN node.id AS id, node.title AS title, node.depth AS depth, node.cluster as cluster, node.content AS content, score
            """
        else:
            query += """
            RETURN node.id AS id, node.title AS title, node.cluster as cluster, node.content AS content, score
            """

        if return_refs:
            query += ", [ref IN refs WHERE ref IS NOT NULL] AS references"

        query += """
        ORDER BY score DESC
        LIMIT $top_k
        """

        parameters = {
            'doc_id': f"{doc_id}||",
            'index_name': index_name,
            'top_k': top_k,
            'embedding': embedding,
            'depth': depth,
            'cluster': cluster,
            'id_startswith': id_startswith
        }

        return self.execute_query(query, parameters)
    
    def sections(self, 
                        doc_id: Optional[str] = None,
                        title: Optional[str] = None,
                        depth: Optional[List[int]] = None,
                        cluster: Optional[int] = None,
                        self_ref: Optional[str] = None,
                        content_contains: Optional[str] = None,
                        added_after: Optional[str] = None,
                        added_before: Optional[str] = None,
                        limit: int = 100) -> List[Dict[str, Any]]:
        
        query = "MATCH (s:Section) WHERE 1=1 "
        params = {}

        if doc_id:
            query += "AND s.id STARTS WITH $doc_id "
            params['doc_id'] = f"{doc_id}||"

        if title:
            query += "AND s.title CONTAINS $title "
            params['title'] = title

        if depth:
            query += "AND s.depth IN $depth "
            params['depth'] = depth

        if cluster is not None:
            query += "AND s.cluster = $cluster "
            params['cluster'] = cluster

        if self_ref:
            query += "AND s.self_ref = $self_ref "
            params['self_ref'] = self_ref

        if content_contains:
            query += "AND s.content CONTAINS $content_contains "
            params['content_contains'] = content_contains

        if added_after:
            query += "AND s.added >= $added_after "
            params['added_after'] = added_after

        if added_before:
            query += "AND s.added <= $added_before "
            params['added_before'] = added_before

        query += """
        RETURN s.id AS id, s.title AS title, s.depth AS depth, 
               s.cluster AS cluster, s.self_ref AS self_ref, 
               s.content AS content, s.added AS added
        ORDER BY s.added DESC
        LIMIT $limit
        """
        params['limit'] = limit

        return self.execute_query(query, params)
    
    def content(self, 
                       doc_id: Optional[str] = None,
                       title: Optional[str] = None,
                       content_contains: Optional[str] = None,
                       self_ref: Optional[str] = None,
                       cluster: Optional[int] = None,
                       summary_contains: Optional[str] = None,
                       added_after: Optional[str] = None,
                       added_before: Optional[str] = None,
                       limit: int = 100) -> List[Dict[str, Any]]:
        
        query = """
        MATCH (c:Content)
        WHERE 1=1 
        """
        params = {}

        if doc_id:
            query += "AND c.id STARTS WITH $doc_id "
            params['doc_id'] = f"{doc_id}||"

        if title:
            query += "AND c.title CONTAINS $title "
            params['title'] = title

        if content_contains:
            query += "AND c.content CONTAINS $content_contains "
            params['content_contains'] = content_contains

        if self_ref:
            query += "AND c.self_ref = $self_ref "
            params['self_ref'] = self_ref

        if cluster is not None:
            query += "AND c.cluster = $cluster "
            params['cluster'] = cluster

        if summary_contains:
            query += "AND c.summary CONTAINS $summary_contains "
            params['summary_contains'] = summary_contains

        if added_after:
            query += "AND c.added >= $added_after "
            params['added_after'] = added_after

        if added_before:
            query += "AND c.added <= $added_before "
            params['added_before'] = added_before

        # query += """
        # WITH c
        # OPTIONAL MATCH (c)-[r:REFERENCES]->(ref:Content)
        # RETURN c.id AS id, c.title AS title, 
        #         c.content AS content, c.cluster AS cluster, 
        #        COLLECT(DISTINCT {
        #            id: ref.id, 
        #            title: ref.title, 
        #            content: ref.content, 
        #            cluster: ref.cluster
        #        }) AS references
        # LIMIT $limit
        # """
        query += """
        WITH c ORDER BY c.added DESC
        OPTIONAL MATCH (c)-[r:REFERENCES]->(ref:Content)
        WITH c, COLLECT(DISTINCT CASE WHEN ref IS NOT NULL 
                        THEN {
                            id: ref.id, 
                            title: ref.title, 
                            content: ref.content, 
                            cluster: ref.cluster
                        }
                        ELSE NULL END) AS refs
        RETURN c.id AS id, c.title AS title, 
                c.content AS content, c.cluster AS cluster, 
            [ref IN refs WHERE ref IS NOT NULL] AS references
        LIMIT $limit
        """
        params['limit'] = limit

        return self.execute_query(query, params)
    
    def tree_cluster(self,
             doc_id: str, 
             embedding: List[float]) -> List[Dict[str, Any]]:
        section_results = self.by_embedding(doc_id, embedding, "section_embedding", top_k=2, depth=[0, 1])
        content_results = []
        for section in section_results:
            section_id = section['id']
            content_nodes = self.by_embedding(doc_id, embedding, "content_embedding", top_k=10, id_startswith=section_id)
            content_results.extend(content_nodes)
        
        final_results = []
        processed_clusters = set()
        for content in content_results:
            cluster = content['cluster']
            if cluster not in processed_clusters:
                result = self.content(cluster=cluster)
                if result:
                    final_results.extend(result)
                    processed_clusters.add(cluster)

        return final_results
    
    def tree_cluster_branch(self,
             doc_id: str, 
             embedding: List[float]) -> Dict[int, List[Dict[str, Any]]]:
        section_results = self.by_embedding(doc_id, embedding, "section_embedding", top_k=2, depth=[0, 1])
        content_results = []
        for section in section_results:
            section_id = section['id']
            content_nodes = self.by_embedding(doc_id, embedding, "content_embedding", top_k=10, id_startswith=section_id)
            content_results.extend(content_nodes)
        
        cluster_results = {}
        processed_clusters = set()
        for content in content_results:
            cluster = content['cluster']
            if cluster not in processed_clusters:
                result = self.content(cluster=cluster)
                if result:
                    cluster_results[cluster] = result
                    processed_clusters.add(cluster)

        return cluster_results
    
    def tree(self,
             doc_id: str, 
             embedding: List[float]) -> List[Dict[str, Any]]:
        section_results = self.by_embedding(doc_id, embedding, "section_embedding", top_k=2, depth=[0, 1])
        content_results = []
        for section in section_results:
            section_id = section['id']
            content_nodes = self.by_embedding(doc_id, embedding, "content_embedding", top_k=50, id_startswith=section_id, return_refs=True)
            content_results.extend(content_nodes)

        return content_results

        formatted_final_result = ""
        processed_ids = set()
        for final_result in final_results:
            result_id = final_result['id']
            if result_id not in processed_ids:
                processed_ids.add(result_id)
                stripped_id = result_id.replace(f"{doc_id}||", "")
            
                formatted_final_result += f"{stripped_id}\n"
                formatted_final_result += f"{final_result.get('content', 'N/A')}\n"
                
                references = final_result.get('references', [])
                if references:
                    formatted_final_result += "References:\n"
                    for ref in references:
                        ref_id = ref.get('id')
                        if ref_id and ref_id not in processed_ids and '995' not in ref_id:
                            processed_ids.add(ref_id)
                            ref_id = ref_id.replace(f"{doc_id}||", "")
                            formatted_final_result += f"  - {ref_id}:\n"
                            formatted_final_result += f"    {ref.get('content', 'N/A')}\n"
                
                formatted_final_result += "\n"

        return formatted_final_result.strip() 