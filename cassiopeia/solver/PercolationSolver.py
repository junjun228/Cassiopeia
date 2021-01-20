from collections import defaultdict
import itertools
import networkx as nx
import pandas as pd
from typing import Callable, Dict, List, Optional, Tuple, Union

from cassiopeia.solver import GreedySolver
from cassiopeia.solver import NeighborJoiningSolver
from cassiopeia.solver import graph_utilities
from cassiopeia.solver import similarity_functions
from cassiopeia.solver import solver_utilities


class PercolationSolver(GreedySolver.GreedySolver):
    """
    TODO: Experiment to find the best default similarity function
    The PercolationSolver implements a top-down algorithm that recursively
    partitions the sample set based on similarity in the observed mutations.
    It is an implicit version of Aho's algorithm for tree discovery (1981).
    At each recursive step, the similarities of each sample pair are embedded
    in a graph. The graph is then percolated by removing the minimum edges
    until multiple connected components are produced. The algorithm enforces
    binary partitions if there are more than two connected components using a
    neighbor-joining procedure.

    Args:
        character_matrix: A character matrix of observed character states for
            all samples
        missing_char: The character representing missing values
        meta_data: Any meta data associated with the samples
        priors: Prior probabilities of observing a transition from 0 to any
            state for each character
        prior_function: A function defining a transformation on the priors
            in forming weights to scale the contribution of each mutation in
            the similarity graph
        similarity_function: A function that calculates a similarity score
            between two given samples and their observed mutations
        threshold: A minimum similarity threshold to include an edge in the
            similarity graph

    Attributes:
        character_matrix: The character matrix describing the samples
        missing_char: The character representing missing values
        meta_data: Data table storing meta data for each sample
        priors: Prior probabilities of character state transitions
        tree: The tree built by `self.solve()`. None if `solve` has not been
            called yet
        unique_character_matrix: A character matrix with duplicate rows filtered
            out, converted to a numpy array for efficient indexing
        node_mapping: A mapping of node names to their integer indices in the
            original character matrix, for efficient indexing
        weights: Weights on character/mutation pairs, derived from priors
        similarity_function: A function that calculates a similarity score
            between two given samples and their observed mutations
        threshold: A minimum similarity threshold
    """

    def __init__(
        self,
        character_matrix: pd.DataFrame,
        missing_char: str,
        meta_data: Optional[pd.DataFrame] = None,
        priors: Optional[Dict[int, Dict[int, float]]] = None,
        prior_function: Optional[Callable[[float], float]] = None,
        similarity_function: Optional[
            Callable[
                [
                    List[int],
                    List[int],
                    int,
                    Optional[Dict[int, Dict[int, float]]],
                ],
                float,
            ]
        ] = None,
        threshold: Optional[int] = 0,
    ):

        super().__init__(character_matrix, missing_char, meta_data, priors)

        self.threshold = threshold
        if similarity_function:
            self.similarity_function = similarity_function
        else:
            self.similarity_function = similarity_functions.hamming_similarity

    def perform_split(
        self,
        samples: List[int],
    ) -> Tuple[List[int], List[int]]:
        """The function used by the percolation algorithm to generate a
        partition of the samples.

        First, a pairwise similarity graph is generated with samples as nodes
        such that edges between a pair of nodes is some provided function on
        the number of character/state mutations shared. Then, the algorithm
        removes the minimum edge (in the case of ties all are removed) until
        the graph is split into multiple connected components. If there are more
        than two connected components, the procedure joins them until two remain.
        This is done by inferring the mutations of the LCA of each sample set
        obeying Camin-Sokal Parsimony, and then performing a neighbor-joining
        procedure on these LCAs using the provided similarity function.

        Args:
            samples: A list of samples, represented as integer indices

        Returns:
            A tuple of lists, representing the left and right partition groups
        """
        G = nx.Graph()
        for v in samples:
            G.add_node(v)

        # Add edge weights into the similarity graph
        edge_weights_to_pairs = defaultdict(list)
        for i, j in itertools.combinations(samples, 2):
            similarity = self.similarity_function(
                self.unique_character_matrix[i],
                self.unique_character_matrix[j],
                self.missing_char,
                self.weights,
            )
            if similarity >= self.threshold:
                edge_weights_to_pairs[similarity].append((i, j))
                G.add_edge(i, j)

        if len(G.edges) == 0:
            return samples, []

        connected_components = list(nx.connected_components(G))
        sorted_edge_weights = sorted(edge_weights_to_pairs, reverse=True)

        # Percolate the similarity graph by continuously removing the minimum
        # edge until at least two components exists
        while len(connected_components) <= 1:
            min_weight = sorted_edge_weights.pop()
            for edge in edge_weights_to_pairs[min_weight]:
                G.remove_edge(edge[0], edge[1])
            connected_components = list(nx.connected_components(G))
        for i in range(len(connected_components)):
            connected_components[i] = list(connected_components[i])

        # If the number of connected components > 2, merge components by
        # greedily joining the most similar LCAs of each component until
        # only 2 remain

        if len(connected_components) > 2:
            lcas = {}
            component_to_nodes = {}
            # Find the LCA of the nodes in each connected component
            for i in range(len(connected_components)):
                component_to_nodes[i] = list(connected_components[i])
                character_vectors = [
                    list(i)
                    for i in list(
                        self.unique_character_matrix[connected_components[i], :]
                    )
                ]
                lcas[i] = solver_utilities.get_lca_characters(
                    character_vectors, self.missing_char
                )
            # The NeighborJoiningSolver operates on a distance, so to have it
            # work on similarity simply use negative similarity
            negative_similarity = (
                lambda s1, s2, missing_char, w: -1
                * self.similarity_function(s1, s2, missing_char, w)
            )
            lca_character_matrix = pd.DataFrame.from_dict(lcas, orient="index")
            nj_solver = NeighborJoiningSolver(
                lca_character_matrix, dissimilarity_function=negative_similarity
            )
            nj_solver.solve()
            clusters = []
            root = [
                n for n in nj_solver.tree if nj_solver.tree.in_degree(n) == 0
            ][0]
            solver_utilities.collapse_unifurcations_newick(nj_solver.tree)
            # Take the bifurcation at the root as the two clusters of components
            # in the split
            for i in nj_solver.tree.successors(root):
                clusters.append(solver_utilities.get_leaves(nj_solver.tree, i))
            split = []
            # For each component in each cluster, take the nodes in that
            # component to form the final split
            for cluster in clusters:
                node_group = []
                for component in cluster:
                    node_group.extend(component_to_nodes[component])
                split.append(node_group)
            return split

        return connected_components