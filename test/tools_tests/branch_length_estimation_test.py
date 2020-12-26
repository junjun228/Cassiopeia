import networkx as nx
import numpy as np

from cassiopeia.tools import PoissonConvexBLE
from cassiopeia.tools.lineage_simulator import lineage_tracing_simulator
from cassiopeia.tools.tree import Tree


def estimate_branch_lengths(T):
    estimator = PoissonConvexBLE()
    return estimator.estimate_branch_lengths(T)


def test_no_mutations():
    r"""
    Tree topology is just a branch 0->1.
    There is one unmutated character i.e.:
        root [state = '0']
        |
        v
        child [state = '0']
    This is thus the simplest possible example of no mutations, and the MLE
    branch length should be 0
    """
    T = nx.DiGraph()
    T.add_node(0), T.add_node(1)
    T.add_edge(0, 1)
    T.nodes[0]["characters"] = '0'
    T.nodes[1]["characters"] = '0'
    T = Tree(T)
    log_likelihood = estimate_branch_lengths(T)
    np.testing.assert_almost_equal(T.get_edge_length(0, 1), 0.0)
    np.testing.assert_almost_equal(T.get_age(0), 0.0)
    np.testing.assert_almost_equal(T.get_age(1), 0.0)
    np.testing.assert_almost_equal(log_likelihood, 0.0)


def test_saturation():
    r"""
    Tree topology is just a branch 0->1.
    There is one mutated character i.e.:
        root [state = '0']
        |
        v
        child [state = '1']
    This is thus the simplest possible example of saturation, and the MLE
    branch length should be infinity (>15 for all practical purposes)
    """
    T = nx.DiGraph()
    T.add_nodes_from([0, 1])
    T.add_edge(0, 1)
    T.nodes[0]["characters"] = '0'
    T.nodes[1]["characters"] = '1'
    T = Tree(T)
    log_likelihood = estimate_branch_lengths(T)
    assert(T.get_edge_length(0, 1) > 15.0)
    assert(T.get_age(0) > 15.0)
    np.testing.assert_almost_equal(T.get_age(1), 0.0)
    np.testing.assert_almost_equal(log_likelihood, 0.0, decimal=5)


def test_hand_solvable_problem_1():
    r"""
    Tree topology is just a branch 0->1.
    There is one mutated character and one unmutated character, i.e.:
        root [state = '00']
        |
        v
        child [state = '01']
    The solution can be verified by hand. The optimization problem is:
        min_{r * t0} log(exp(-r * t0)) + log(1 - exp(-r * t0))
    The solution is r * t0 = ln(2) ~ 0.693
    """
    T = nx.DiGraph()
    T.add_nodes_from([0, 1])
    T.add_edge(0, 1)
    T.nodes[0]["characters"] = '00'
    T.nodes[1]["characters"] = '01'
    T = Tree(T)
    log_likelihood = estimate_branch_lengths(T)
    np.testing.assert_almost_equal(
        T.get_edge_length(0, 1), np.log(2), decimal=3)
    np.testing.assert_almost_equal(T.get_age(0), np.log(2), decimal=3)
    np.testing.assert_almost_equal(T.get_age(1), 0.0)
    np.testing.assert_almost_equal(log_likelihood, -1.386, decimal=3)


def test_hand_solvable_problem_2():
    r"""
    Tree topology is just a branch 0->1.
    There are two mutated characters and one unmutated character, i.e.:
        root [state = '000']
        |
        v
        child [state = '011']
    The solution can be verified by hand. The optimization problem is:
        min_{r * t0} log(exp(-r * t0)) + 2 * log(1 - exp(-r * t0))
    The solution is r * t0 = ln(3) ~ 1.098
    """
    T = nx.DiGraph()
    T.add_nodes_from([0, 1])
    T.add_edge(0, 1)
    T.nodes[0]["characters"] = '000'
    T.nodes[1]["characters"] = '011'
    T = Tree(T)
    log_likelihood = estimate_branch_lengths(T)
    np.testing.assert_almost_equal(
        T.get_edge_length(0, 1), np.log(3), decimal=3)
    np.testing.assert_almost_equal(T.get_age(0), np.log(3), decimal=3)
    np.testing.assert_almost_equal(T.get_age(1), 0.0)
    np.testing.assert_almost_equal(log_likelihood, -1.909, decimal=3)


def test_hand_solvable_problem_3():
    r"""
    Tree topology is just a branch 0->1.
    There are two unmutated characters and one mutated character, i.e.:
        root [state = '000']
        |
        v
        child [state = '001']
    The solution can be verified by hand. The optimization problem is:
        min_{r * t0} 2 * log(exp(-r * t0)) + log(1 - exp(-r * t0))
    The solution is r * t0 = ln(1.5) ~ 0.405
    """
    T = nx.DiGraph()
    T.add_nodes_from([0, 1])
    T.add_edge(0, 1)
    T.nodes[0]["characters"] = '000'
    T.nodes[1]["characters"] = '001'
    T = Tree(T)
    log_likelihood = estimate_branch_lengths(T)
    np.testing.assert_almost_equal(
        T.get_edge_length(0, 1), np.log(1.5), decimal=3)
    np.testing.assert_almost_equal(T.get_age(0), np.log(1.5), decimal=3)
    np.testing.assert_almost_equal(T.get_age(1), 0.0)
    np.testing.assert_almost_equal(log_likelihood, -1.909, decimal=3)


def test_small_tree_with_no_mutations():
    r"""
    Perfect binary tree with no mutations: Should give edges of length 0
    """
    T = nx.DiGraph()
    T.add_nodes_from([0, 1, 2, 3, 4, 5, 6])
    T.add_edges_from([(0, 1), (0, 2), (1, 3), (1, 4), (2, 5), (2, 6)])
    T.nodes[0]["characters"] = '0000'
    T.nodes[1]["characters"] = '0000'
    T.nodes[2]["characters"] = '0000'
    T.nodes[3]["characters"] = '0000'
    T.nodes[4]["characters"] = '0000'
    T.nodes[5]["characters"] = '0000'
    T.nodes[6]["characters"] = '0000'
    T = Tree(T)
    log_likelihood = estimate_branch_lengths(T)
    for edge in T.edges():
        np.testing.assert_almost_equal(T.get_edge_length(*edge), 0, decimal=3)
    np.testing.assert_almost_equal(log_likelihood, 0.0, decimal=3)


def test_small_tree_with_one_mutation():
    r"""
    Perfect binary tree with one mutation at a node 6: Should give very short
    edges 1->3,1->4,0->2 and very long edges 0->1,2->5,2->6.
    The problem can be solved by hand: it trivially reduces to a 1-dimensional
    problem:
        min_{r * t0} 2 * log(exp(-r * t0)) + log(1 - exp(-r * t0))
    The solution is r * t0 = ln(1.5) ~ 0.405
    """
    T = nx.DiGraph()
    T.add_nodes_from([0, 1, 2, 3, 4, 5, 6]),
    T.add_edges_from([(0, 1), (0, 2), (1, 3), (1, 4), (2, 5), (2, 6)])
    T.nodes[0]["characters"] = '0'
    T.nodes[1]["characters"] = '0'
    T.nodes[2]["characters"] = '0'
    T.nodes[3]["characters"] = '0'
    T.nodes[4]["characters"] = '0'
    T.nodes[5]["characters"] = '0'
    T.nodes[6]["characters"] = '1'
    T = Tree(T)
    log_likelihood = estimate_branch_lengths(T)
    np.testing.assert_almost_equal(T.get_edge_length(0, 1), 0.405, decimal=3)
    np.testing.assert_almost_equal(T.get_edge_length(0, 2), 0.0, decimal=3)
    np.testing.assert_almost_equal(T.get_edge_length(1, 3), 0.0, decimal=3)
    np.testing.assert_almost_equal(T.get_edge_length(1, 4), 0.0, decimal=3)
    np.testing.assert_almost_equal(T.get_edge_length(2, 5), 0.405, decimal=3)
    np.testing.assert_almost_equal(T.get_edge_length(2, 6), 0.405, decimal=3)
    np.testing.assert_almost_equal(log_likelihood, -1.909, decimal=3)


def test_small_tree_with_saturation():
    r"""
    Perfect binary tree with saturation. The edges which saturate should thus
    have length infinity (>15 for all practical purposes)
    """
    T = nx.DiGraph()
    T.add_nodes_from([0, 1, 2, 3, 4, 5, 6]),
    T.add_edges_from([(0, 1), (0, 2), (1, 3), (1, 4), (2, 5), (2, 6)])
    T.nodes[0]["characters"] = '0'
    T.nodes[1]["characters"] = '0'
    T.nodes[2]["characters"] = '1'
    T.nodes[3]["characters"] = '1'
    T.nodes[4]["characters"] = '1'
    T.nodes[5]["characters"] = '1'
    T.nodes[6]["characters"] = '1'
    T = Tree(T)
    _ = estimate_branch_lengths(T)
    assert(T.get_edge_length(0, 2) > 15.0)
    assert(T.get_edge_length(1, 3) > 15.0)
    assert(T.get_edge_length(1, 4) > 15.0)


def test_small_tree_regression():
    r"""
    Regression test. Cannot be solved by hand. We just check that this solution
    never changes.
    """
    # Perfect binary tree with normal amount of mutations on each edge
    T = nx.DiGraph()
    T.add_nodes_from([0, 1, 2, 3, 4, 5, 6]),
    T.add_edges_from([(0, 1), (0, 2), (1, 3), (1, 4), (2, 5), (2, 6)])
    T.nodes[0]["characters"] = '000000000'
    T.nodes[1]["characters"] = '100000000'
    T.nodes[2]["characters"] = '000006000'
    T.nodes[3]["characters"] = '120000000'
    T.nodes[4]["characters"] = '103000000'
    T.nodes[5]["characters"] = '000056700'
    T.nodes[6]["characters"] = '000406089'
    T = Tree(T)
    log_likelihood = estimate_branch_lengths(T)
    np.testing.assert_almost_equal(T.get_edge_length(0, 1), 0.203, decimal=3)
    np.testing.assert_almost_equal(T.get_edge_length(0, 2), 0.082, decimal=3)
    np.testing.assert_almost_equal(T.get_edge_length(1, 3), 0.175, decimal=3)
    np.testing.assert_almost_equal(T.get_edge_length(1, 4), 0.175, decimal=3)
    np.testing.assert_almost_equal(T.get_edge_length(2, 5), 0.295, decimal=3)
    np.testing.assert_almost_equal(T.get_edge_length(2, 6), 0.295, decimal=3)
    np.testing.assert_almost_equal(log_likelihood, -22.689, decimal=3)


def test_small_symmetric_tree():
    r"""
    Symmetric tree should have equal length edges.
    """
    T = nx.DiGraph()
    T.add_nodes_from([0, 1, 2, 3, 4, 5, 6]),
    T.add_edges_from([(0, 1), (0, 2), (1, 3), (1, 4), (2, 5), (2, 6)])
    T.nodes[0]["characters"] = '000'
    T.nodes[1]["characters"] = '100'
    T.nodes[2]["characters"] = '100'
    T.nodes[3]["characters"] = '110'
    T.nodes[4]["characters"] = '110'
    T.nodes[5]["characters"] = '110'
    T.nodes[6]["characters"] = '110'
    T = Tree(T)
    _ = estimate_branch_lengths(T)
    np.testing.assert_almost_equal(
        T.get_edge_length(0, 1), T.get_edge_length(0, 2))
    np.testing.assert_almost_equal(
        T.get_edge_length(1, 3), T.get_edge_length(1, 4))
    np.testing.assert_almost_equal(
        T.get_edge_length(1, 4), T.get_edge_length(2, 5))
    np.testing.assert_almost_equal(
        T.get_edge_length(2, 5), T.get_edge_length(2, 6))


def test_small_tree_with_infinite_legs():
    r"""
    Perfect binary tree with saturated leaves. The first level of the tree
    should be normal (can be solved by hand, solution is log(2)),
    the branches for the leaves should be infinity (>15 for all practical
    purposes)
    """
    T = nx.DiGraph()
    T.add_nodes_from([0, 1, 2, 3, 4, 5, 6]),
    T.add_edges_from([(0, 1), (0, 2), (1, 3), (1, 4), (2, 5), (2, 6)])
    T.nodes[0]["characters"] = '00'
    T.nodes[1]["characters"] = '10'
    T.nodes[2]["characters"] = '10'
    T.nodes[3]["characters"] = '11'
    T.nodes[4]["characters"] = '11'
    T.nodes[5]["characters"] = '11'
    T.nodes[6]["characters"] = '11'
    T = Tree(T)
    _ = estimate_branch_lengths(T)
    np.testing.assert_almost_equal(T.get_edge_length(0, 1), 0.693, decimal=3)
    np.testing.assert_almost_equal(T.get_edge_length(0, 2), 0.693, decimal=3)
    assert(T.get_edge_length(1, 3) > 15)
    assert(T.get_edge_length(1, 4) > 15)
    assert(T.get_edge_length(2, 5) > 15)
    assert(T.get_edge_length(2, 6) > 15)


def test_on_simulated_data():
    T = nx.DiGraph()
    T.add_nodes_from([0, 1, 2, 3, 4, 5, 6]),
    T.add_edges_from([(0, 1), (0, 2), (1, 3), (1, 4), (2, 5), (2, 6)])
    T.nodes[0]["age"] = 1
    T.nodes[1]["age"] = 0.9
    T.nodes[2]["age"] = 0.1
    T.nodes[3]["age"] = 0
    T.nodes[4]["age"] = 0
    T.nodes[5]["age"] = 0
    T.nodes[6]["age"] = 0
    np.random.seed(1)
    T = Tree(T)
    lineage_tracing_simulator(T, mutation_rate=1.0, num_characters=100)
    for node in T.nodes():
        T.set_age(node, -1)
    estimate_branch_lengths(T)
    assert(0.9 < T.get_age(0) < 1.1)
    assert(0.8 < T.get_age(1) < 1.0)
    assert(0.05 < T.get_age(2) < 0.15)
    np.testing.assert_almost_equal(T.get_age(3), 0)
    np.testing.assert_almost_equal(T.get_age(4), 0)
    np.testing.assert_almost_equal(T.get_age(5), 0)
    np.testing.assert_almost_equal(T.get_age(6), 0)


def test_subtree_collapses_when_no_mutations():
    r"""
    A subtree with no mutations should collapse to 0. It reduces the problem to
    the same as in 'test_hand_solvable_problem_1'
    """
    T = nx.DiGraph()
    T.add_nodes_from([0, 1, 2, 3, 4]),
    T.add_edges_from([(0, 1), (1, 2), (1, 3), (0, 4)])
    T.nodes[0]["characters"] = '0'
    T.nodes[1]["characters"] = '1'
    T.nodes[2]["characters"] = '1'
    T.nodes[3]["characters"] = '1'
    T.nodes[4]["characters"] = '0'
    T = Tree(T)
    log_likelihood = estimate_branch_lengths(T)
    np.testing.assert_almost_equal(
        T.get_edge_length(0, 1), np.log(2), decimal=3)
    np.testing.assert_almost_equal(T.get_edge_length(1, 2), 0.0, decimal=3)
    np.testing.assert_almost_equal(T.get_edge_length(1, 3), 0.0, decimal=3)
    np.testing.assert_almost_equal(
        T.get_edge_length(0, 4), np.log(2), decimal=3)
    np.testing.assert_almost_equal(log_likelihood, -1.386, decimal=3)
