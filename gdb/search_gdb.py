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

    def print_node(self, limit: int = 10000):
        query = """
        MATCH (c:Content)
        RETURN c.title AS title, c.self_ref AS self_ref, c.id AS id, c.content AS content
        LIMIT $limit
        """
        
        params = {'limit': limit}
        
        try:
            results = self.execute_query(query, params)
            
            if results:
                for i, result in enumerate(results, 1):
                        if result['self_ref'] == '104-5':
                            print(f"{i}. Title: {result['title']}")
                            print(f"   ID: {result['id']}")
                            # print(f"   Self Ref: {result['self_ref']}")
                            print(f"   Content Preview: {result['content']}")
                            print()
            else:
                print("No nodes found")
            
        except Exception as e:
            print(f"An error occurred: {str(e)}")

    def by_embedding(self,
                doc_id: str, 
                embedding: List[float], 
                index_name: str, 
                top_k: int = 5, 
                depth: List[int] = None, 
                cluster: int = None,
                id_startswith: str = None,
                return_refs: bool = False,
                clean_output: bool = True) -> List[Dict[str, Any]]:
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

        if index_name != "section_embedding":
            query += " AND NOT toLower(node.title) CONTAINS 'division'"

        if return_refs:
            query += """
            WITH node, score
            OPTIONAL MATCH (node)-[r:REFERENCES]->(ref:Content)
            WITH node, score, COLLECT(DISTINCT CASE WHEN ref IS NOT NULL 
                    THEN {
                        id: ref.id, 
                        title: ref.title, 
                        self_ref: ref.self_ref,
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
            RETURN node.id AS id, node.title AS title, node.self_ref as self_ref, node.cluster as cluster, node.content AS content, score
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

        results = self.execute_query(query, parameters)

        # only return unique nodes
        # NOTE this may lose some content nodes (refs of refs)
        processed_results = []
        unique_nodes = set()
        def process_node(node):
            return {
                'id': node['id'].split('||', 1)[-1] if '||' in node['id'] else node['id'],
                'self_ref': node.get('self_ref'),
                'title': node['title'],
                'content': node['content']
            }
        for result in results:
            if result['id'] not in unique_nodes:
                if clean_output:
                    processed_results.append(process_node(result))
                else:
                    processed_results.append(result)
                unique_nodes.add(result['id'])
                if 'references' in result and result['references']:
                    for ref in result['references']:
                        if ref['id'] not in unique_nodes:
                            if clean_output:
                                processed_results.append(process_node(ref))
                            else:
                                processed_results.append(ref)
                            unique_nodes.add(ref['id'])
        return processed_results
    
    def section(self, 
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
            exclude_division: bool = False, # skip: What this Division is about, Effect of this Division etc
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

        if exclude_division:
            query += "AND NOT toLower(c.title) CONTAINS 'division' "

        query += """
        WITH c ORDER BY c.added DESC
        OPTIONAL MATCH (c)-[r:REFERENCES]->(ref:Content)
        WITH c, COLLECT(DISTINCT CASE WHEN ref IS NOT NULL 
                        THEN {
                            id: ref.id, 
                            title: ref.title, 
                            self_ref: ref.self_ref,
                            content: ref.content, 
                            cluster: ref.cluster
                        }
                        ELSE NULL END) AS refs
        RETURN c.id AS id, c.title AS title, c.self_ref AS self_ref,
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
                result = self.content(cluster=cluster, exclude_division=True)
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
                result = self.content(cluster=cluster, exclude_division=True)
                if result:
                    cluster_results[cluster] = result
                    processed_clusters.add(cluster)

        return cluster_results
    
    def tree_section(self,
             doc_id: str, 
             embedding: List[float]) -> List[Dict[str, Any]]:
        section_results = self.by_embedding(doc_id, embedding, "section_embedding", top_k=2, depth=[0, 1])
        content_results = []
        for section in section_results:
            section_id = section['id']
            content_nodes = self.by_embedding(doc_id, embedding, "content_embedding", top_k=50, id_startswith=section_id, return_refs=True)
            content_results.extend(content_nodes)

        return content_results
    
    def tree(self,
             doc_id: str, 
             embedding: List[float],
             top_k: int = 50,
             return_refs: bool = True) -> List[Dict[str, Any]]:
        # NOTE simple but probably the best
        content_nodes = self.by_embedding(doc_id, embedding, "content_embedding", top_k=top_k, return_refs=return_refs)
        return content_nodes
    
    def tree_branch(self, 
            doc_id: str, 
            embedding: List[float]) -> Dict[str, List[Dict[str, Any]]]:
        section_results = self.by_embedding(doc_id, embedding, "section_embedding", top_k=2, depth=[0, 1])
        branch_results = {}

        for section in section_results:
            section_id = section['id']
            content_nodes = self.by_embedding(doc_id, embedding, "content_embedding", top_k=50, id_startswith=section_id, return_refs=True)
            branch_results[section_id] = content_nodes

        return branch_results