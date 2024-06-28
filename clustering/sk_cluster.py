import numpy as np
from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
from sklearn.mixture import GaussianMixture
from sklearn.metrics import silhouette_score, pairwise_distances
from sklearn.decomposition import PCA
from operator import itemgetter
from joblib import Parallel, delayed
import matplotlib.pyplot as plt
from tqdm import tqdm

def calculate_score(n, vectors, method):
    if method == 'kmeans':
        clusterer = KMeans(n_clusters=n, random_state=42)
    elif method == 'agglomerative':
        clusterer = AgglomerativeClustering(n_clusters=n)
    else:  # gmm
        clusterer = GaussianMixture(n_components=n, random_state=42)
    
    labels = clusterer.fit_predict(vectors)
    
    if len(np.unique(labels)) > 1:
        score = silhouette_score(vectors, labels, metric='cosine')
        return n, score, labels
    else:
        return n, -1, labels

def cluster_vectors(vectors, method='kmeans', eps=0.5, min_samples=5, n_clusters=None):
    """
    Cluster vectors using different algorithms and find optimal number of clusters when applicable.
    
    :param vectors: numpy array of shape (n_samples, n_features)
    :param method: clustering method to use ('kmeans', 'dbscan', 'agglomerative', 'gmm')
    :param eps: The maximum distance between two samples for DBSCAN
    :param min_samples: The number of samples in a neighborhood for a point to be considered as a core point for DBSCAN
    :param n_clusters: Number of clusters to use (if None, it will be calculated)
    :return: cluster labels, number of clusters, and cluster proximities
    """
    best_score = -1
    best_labels = None

    if method in ['kmeans', 'agglomerative', 'gmm']:
        if n_clusters is None:
            ## BED TEMPORARY LOGIC
            if len(vectors) < 1000:
                min_clusters = 2
                max_clusters = len(vectors)
            else:
                min_clusters = len(vectors) // 100
                max_clusters = len(vectors) // 10
            # NOTE parallel computation of silhouette scores cooks cpus
            results = Parallel(n_jobs=-1)(delayed(calculate_score)(n, vectors, method) 
                                          for n in tqdm(range(min_clusters, max_clusters), desc="Calculating silhouette scores"))
            best_n, best_score, best_labels = max(results, key=lambda x: x[1])
            
            if best_score > -1:
                print(f"Optimal number of clusters for {method}: {best_n}")
                print(f"Best Silhouette Score: {best_score}")
            else:
                print(f"No valid clustering found for {method}")
                return None, 0, None
            
            optimal_clusters = best_n
        else:
            if method == 'kmeans':
                clusterer = KMeans(n_clusters=n_clusters, random_state=42)
            elif method == 'agglomerative':
                clusterer = AgglomerativeClustering(n_clusters=n_clusters)
            else:  # gmm
                clusterer = GaussianMixture(n_components=n_clusters, random_state=42)
            
            best_labels = clusterer.fit_predict(vectors)
            optimal_clusters = n_clusters

    elif method == 'dbscan':
        clusterer = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
        best_labels = clusterer.fit_predict(vectors)
        optimal_clusters = len(set(best_labels)) - (1 if -1 in best_labels else 0)
        
        if optimal_clusters > 1:
            score = silhouette_score(vectors, best_labels)
            print(f"Number of clusters for DBSCAN: {optimal_clusters}")
            print(f"Silhouette Score: {score}")
        else:
            print("DBSCAN resulted in 0 or 1 cluster. Try adjusting eps and min_samples parameters.")

    else:
        raise ValueError("Invalid clustering method. Choose from 'kmeans', 'dbscan', 'agglomerative', or 'gmm'")

    if optimal_clusters > 1:
        cluster_centers = np.array([vectors[best_labels == i].mean(axis=0) for i in range(optimal_clusters)])
        cluster_proximities = pairwise_distances(cluster_centers, metric='cosine')
    else:
        cluster_proximities = np.array([[0]])

    return best_labels, optimal_clusters, cluster_proximities

def get_closest_clusters(cluster, proximities, top_n=3):
    distances = [(i, dist) for i, dist in enumerate(proximities[cluster]) if i != cluster]
    return sorted(distances, key=itemgetter(1))[:top_n]

def plot_clusters_with_titles(embeddings, cluster_labels, titles, n_clusters, cluster_proximities, figsize=(20, 20)):
    #clustering.plot_clusters_with_titles(embeddings_array, cluster_labels, filtered_depth_df['title'].values, n_clusters, cluster_proximities)
    cluster_centers = np.array([embeddings[cluster_labels == i].mean(axis=0) for i in range(n_clusters)])
    
    pca = PCA(n_components=2)
    reduced_centers = pca.fit_transform(cluster_centers)

    plt.figure(figsize=figsize)
    
    colors = plt.cm.rainbow(np.linspace(0, 1, n_clusters))
    for i in range(n_clusters):
        plt.scatter(reduced_centers[i, 0], reduced_centers[i, 1], c=[colors[i]], s=200, label=f'C{i}')
        
        plt.annotate(f'C{i}', (reduced_centers[i, 0], reduced_centers[i, 1]), fontsize=8, fontweight='bold')

        cluster_titles = titles[cluster_labels == i]
        for j, title in enumerate(cluster_titles[:3]):
            offset = j * 0.3 
            plt.annotate(title, (reduced_centers[i, 0] + offset, reduced_centers[i, 1] + offset), fontsize=8, alpha=0.7)
        
        if len(cluster_titles) > 3:
            plt.annotate(f'... and {len(cluster_titles) - 3} more', 
                         (reduced_centers[i, 0], reduced_centers[i, 1] - 0.1), fontsize=8, alpha=0.7)

    max_proximity = np.max(cluster_proximities)
    for i in range(n_clusters):
        for j in range(i+1, n_clusters):
            normalised_proximity = cluster_proximities[i, j] / max_proximity
            plt.plot([reduced_centers[i, 0], reduced_centers[j, 0]],
                     [reduced_centers[i, 1], reduced_centers[j, 1]],
                     'k-', alpha=max(0.1, 1 - normalised_proximity), linewidth=1)

    plt.title('Cluster Visualisation with Titles and Proximities')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.show()

