# -*- coding: utf-8 -*-
"""
Empirical Stress Test Suite: Milestone 1 Causal DAG & Master Graph Architecture
(Independent Empirical Verification by Challenger M1_1)

Requirements Tested:
1. Multi-seed Generation: 30+ seeds across various volume counts, chapter lengths, and complexities.
   - Independent oracle verification (DFS / 3-color cycle finder) to confirm cycle_count == 0.
2. Adversarial Synthetic Cycles:
   - Self-loops, 2-node, 3-node, N-node (5, 10, 25, 50), disconnected, multi-cycle, and random back-edges.
   - Verify 100% detection rate by validate_causal_dag().
3. Non-Causal Cycle Exemption:
   - ECHOES, PARALLELS, CONTRASTS, SETS_UP, PAYS_OFF, CHARACTER_ARC, etc.
   - Intertwined causal path + non-causal back-edges and non-causal self-loops.
   - Verify 100% exemption (0 false positives).
4. Boundary Nodes:
   - In-degree 0 (start nodes), Out-degree 0 (end nodes), isolated nodes, empty graphs, single-node graphs.
   - Check distribution of start and end nodes on generated graphs.
5. Multi-Thread Memberships Under Heavy Load:
   - 500 and 1000 chapters, 24 core threads (6 main + 18 sub), crossover nodes.
"""

from collections import deque
import random
import time
from typing import Dict, List, Set, Tuple
import pytest

from backend.geometry.models import (
    CAUSAL_EDGE_TYPES,
    NON_CAUSAL_EDGE_TYPES,
    EdgeType,
    GeometryComplexity,
    GeometryEdge,
    GeometryGraph,
    GeometryNode,
    GeometryParams,
    NodeHierarchy,
    StructuralRole,
    ThreadType,
)
from backend.geometry.generator import GeometryGenerator


# =============================================================================
# Independent Oracle for Cycle Detection (Adversarial Reference Standard)
# =============================================================================

def independent_oracle_find_cycles(graph: GeometryGraph) -> List[List[str]]:
    """
    Independent 3-color DFS cycle detection algorithm on CAUSAL edges.
    WHITE = 0 (unvisited), GRAY = 1 (in current recursion stack), BLACK = 2 (completed).
    Returns list of detected cycles (node id paths).
    Used as an external oracle to verify validate_causal_dag().
    """
    causal_edges = [e for e in graph.edges if e.edge_type in CAUSAL_EDGE_TYPES]
    adj: Dict[str, List[str]] = {nid: [] for nid in graph.nodes}

    # Detect self loops directly
    self_loops = []
    for e in causal_edges:
        if e.source in adj and e.target in adj:
            if e.source == e.target:
                self_loops.append([e.source, e.source])
            else:
                adj[e.source].append(e.target)

    color: Dict[str, int] = {nid: 0 for nid in graph.nodes}
    parent: Dict[str, str] = {}
    cycles: List[List[str]] = list(self_loops)

    def dfs(u: str, path: List[str]):
        color[u] = 1
        path.append(u)
        for v in adj[u]:
            if color[v] == 1:
                # Cycle found: reconstruct path
                cycle_idx = path.index(v)
                cycles.append(path[cycle_idx:] + [v])
            elif color[v] == 0:
                parent[v] = u
                dfs(v, path)
        path.pop()
        color[u] = 2

    for node_id in graph.nodes:
        if color[node_id] == 0:
            dfs(node_id, [])

    return cycles


# =============================================================================
# 1. Multi-Seed Generation & Cycle Acyclicity Verification (20+ Seeds)
# =============================================================================

class TestEmpiricalDAGGenerationAcrossSeeds:
    """Task 1: Generate graphs across 30+ random seeds with varied configurations."""

    @pytest.mark.parametrize("seed_idx,chapters,vol_count,complexity", [
        (0, 30, 2, GeometryComplexity.SPARSE),
        (1, 50, 5, GeometryComplexity.STANDARD),
        (2, 60, 6, GeometryComplexity.DENSE),
        (3, 80, 8, GeometryComplexity.VERY_DENSE),
        (4, 100, 10, GeometryComplexity.STANDARD),
        (5, 120, 12, GeometryComplexity.DENSE),
        (6, 150, 10, GeometryComplexity.SPARSE),
        (7, 200, 15, GeometryComplexity.STANDARD),
        (8, 250, 10, GeometryComplexity.DENSE),
        (9, 300, 20, GeometryComplexity.VERY_DENSE),
        (10, 40, 4, GeometryComplexity.STANDARD),
        (11, 75, 5, GeometryComplexity.DENSE),
        (12, 90, 9, GeometryComplexity.SPARSE),
        (13, 110, 11, GeometryComplexity.STANDARD),
        (14, 130, 13, GeometryComplexity.VERY_DENSE),
        (15, 160, 16, GeometryComplexity.STANDARD),
        (16, 180, 12, GeometryComplexity.DENSE),
        (17, 220, 11, GeometryComplexity.SPARSE),
        (18, 260, 13, GeometryComplexity.STANDARD),
        (19, 320, 16, GeometryComplexity.VERY_DENSE),
        (20, 45, 3, GeometryComplexity.STANDARD),
        (21, 65, 5, GeometryComplexity.DENSE),
        (22, 85, 7, GeometryComplexity.SPARSE),
        (23, 105, 10, GeometryComplexity.STANDARD),
        (24, 125, 12, GeometryComplexity.VERY_DENSE),
        (25, 140, 14, GeometryComplexity.DENSE),
        (26, 175, 15, GeometryComplexity.STANDARD),
        (27, 210, 14, GeometryComplexity.SPARSE),
        (28, 280, 14, GeometryComplexity.DENSE),
        (29, 350, 18, GeometryComplexity.VERY_DENSE),
    ])
    def test_multi_seed_generation_strict_dag_acyclicity(
        self, seed_idx: int, chapters: int, vol_count: int, complexity: GeometryComplexity
    ):
        """Verify across 30 distinct seeds/configurations that causal DAG has 0 cycles."""
        seed_name = f"empirical_stress_seed_{seed_idx}_{chapters}ch_{vol_count}v"
        params = GeometryParams(
            target_chapters=chapters,
            volume_count=vol_count,
            complexity=complexity,
            seed_for_rng=seed_name,
        )
        generator = GeometryGenerator(params)
        graph = generator.generate()

        # 1. Implementation Kahn's algorithm check
        cycle_errors = graph.validate_causal_dag()
        assert cycle_errors == [], f"Seed {seed_name} produced causal cycles: {cycle_errors}"

        # 2. Independent DFS Oracle cross-verification
        oracle_cycles = independent_oracle_find_cycles(graph)
        assert len(oracle_cycles) == 0, f"Oracle detected causal cycles in {seed_name}: {oracle_cycles}"


# =============================================================================
# 2. Adversarial Synthetic Cycle Injection (100% Detection Rate)
# =============================================================================

class TestEmpiricalAdversarialCycleDetection:
    """Task 2: Inject adversarial synthetic causal cycles and verify 100% detection rate."""

    @pytest.fixture
    def base_graph(self) -> GeometryGraph:
        """Create a clean 100-chapter master graph."""
        params = GeometryParams(target_chapters=100, volume_count=10, seed_for_rng="adv_cycle_fixture")
        return GeometryGenerator(params).generate()

    @pytest.mark.parametrize("causal_edge_type", [
        EdgeType.CAUSES,
        EdgeType.ENABLES,
        EdgeType.ESCALATES,
    ])
    def test_detects_adversarial_self_loop(self, base_graph: GeometryGraph, causal_edge_type: EdgeType):
        """Self loop: u -> u on any causal edge type must be detected."""
        node_id = list(base_graph.nodes.keys())[10]
        base_graph.add_edge(GeometryEdge(
            edge_id="ADV_SELF_LOOP",
            source=node_id,
            target=node_id,
            edge_type=causal_edge_type,
            distance=0,
        ))
        errors = base_graph.validate_causal_dag()
        assert len(errors) > 0, f"Failed to detect causal self-loop with {causal_edge_type}"
        assert any("self-loop" in e.lower() or "cycle" in e.lower() for e in errors)

    @pytest.mark.parametrize("causal_edge_type", [
        EdgeType.CAUSES,
        EdgeType.ENABLES,
        EdgeType.ESCALATES,
    ])
    def test_detects_adversarial_2_node_cycle(self, base_graph: GeometryGraph, causal_edge_type: EdgeType):
        """2-node cycle: u -> v and v -> u."""
        nodes = list(base_graph.nodes.keys())
        u, v = nodes[5], nodes[6]
        base_graph.add_edge(GeometryEdge(
            edge_id="ADV_2NODE_FWD",
            source=u,
            target=v,
            edge_type=causal_edge_type,
            distance=1,
        ))
        base_graph.add_edge(GeometryEdge(
            edge_id="ADV_2NODE_BWD",
            source=v,
            target=u,
            edge_type=causal_edge_type,
            distance=1,
        ))
        errors = base_graph.validate_causal_dag()
        assert len(errors) > 0, f"Failed to detect 2-node cycle with {causal_edge_type}"

    def test_detects_adversarial_mixed_3_node_cycle(self, base_graph: GeometryGraph):
        """3-node cycle with mixed causal edge types: CAUSES -> ENABLES -> ESCALATES."""
        nodes = list(base_graph.nodes.keys())
        u, v, w = nodes[15], nodes[20], nodes[25]
        base_graph.add_edge(GeometryEdge("ADV_3N_1", u, v, EdgeType.CAUSES, 1))
        base_graph.add_edge(GeometryEdge("ADV_3N_2", v, w, EdgeType.ENABLES, 1))
        base_graph.add_edge(GeometryEdge("ADV_3N_3", w, u, EdgeType.ESCALATES, 1))

        errors = base_graph.validate_causal_dag()
        assert len(errors) > 0, "Failed to detect 3-node mixed causal cycle"

    @pytest.mark.parametrize("cycle_length", [5, 10, 25, 50])
    def test_detects_adversarial_large_n_node_cycle(self, base_graph: GeometryGraph, cycle_length: int):
        """Long directed cycle spanning across N nodes and multiple chapters."""
        nodes = list(base_graph.nodes.keys())[:cycle_length]
        for i in range(cycle_length):
            src = nodes[i]
            tgt = nodes[(i + 1) % cycle_length]
            edge_type = [EdgeType.CAUSES, EdgeType.ENABLES, EdgeType.ESCALATES][i % 3]
            base_graph.add_edge(GeometryEdge(
                edge_id=f"ADV_N_{cycle_length}_{i}",
                source=src,
                target=tgt,
                edge_type=edge_type,
                distance=1,
            ))
        errors = base_graph.validate_causal_dag()
        assert len(errors) > 0, f"Failed to detect {cycle_length}-node cycle"

    def test_detects_adversarial_disconnected_subgraph_cycle(self, base_graph: GeometryGraph):
        """Cycle placed in a completely disconnected subcomponent outside the main story graph."""
        c1 = GeometryNode("DISC_1", NodeHierarchy(99, 1, 1), (999, 999), StructuralRole.DEVELOP, "TM01")
        c2 = GeometryNode("DISC_2", NodeHierarchy(99, 1, 1), (999, 999), StructuralRole.DEVELOP, "TM01")
        base_graph.add_node(c1)
        base_graph.add_node(c2)

        base_graph.add_edge(GeometryEdge("ADV_DISC_1", "DISC_1", "DISC_2", EdgeType.CAUSES, 0))
        base_graph.add_edge(GeometryEdge("ADV_DISC_2", "DISC_2", "DISC_1", EdgeType.ENABLES, 0))

        errors = base_graph.validate_causal_dag()
        assert len(errors) > 0, "Failed to detect cycle in disconnected subgraph"

    def test_detects_multiple_disjoint_cycles_simultaneously(self, base_graph: GeometryGraph):
        """Multiple disjoint cycles in distinct parts of the graph."""
        nodes = list(base_graph.nodes.keys())
        # Cycle A: nodes[0] <-> nodes[1]
        base_graph.add_edge(GeometryEdge("ADV_DISJ_A1", nodes[0], nodes[1], EdgeType.CAUSES, 1))
        base_graph.add_edge(GeometryEdge("ADV_DISJ_A2", nodes[1], nodes[0], EdgeType.ENABLES, 1))
        # Cycle B: nodes[30] <-> nodes[31]
        base_graph.add_edge(GeometryEdge("ADV_DISJ_B1", nodes[30], nodes[31], EdgeType.ESCALATES, 1))
        base_graph.add_edge(GeometryEdge("ADV_DISJ_B2", nodes[31], nodes[30], EdgeType.CAUSES, 1))

        errors = base_graph.validate_causal_dag()
        assert len(errors) > 0, "Failed to detect multiple disjoint cycles"

    def test_adversarial_random_back_edge_cycle_sweep(self):
        """
        Adversarially sweep across 20 distinct graphs:
        Find a forward causal path u ~> v, then add reverse edge v -> u to close a cycle.
        Verify validate_causal_dag() detects it 100% of the time.
        """
        detected_count = 0
        total_trials = 20

        for trial in range(total_trials):
            params = GeometryParams(target_chapters=40, volume_count=4, seed_for_rng=f"adv_sweep_{trial}")
            graph = GeometryGenerator(params).generate()

            # Find a valid causal forward path
            causal_edges = [e for e in graph.edges if e.edge_type in CAUSAL_EDGE_TYPES]
            assert len(causal_edges) > 0

            # Pick a causal edge (u -> v), reverse it (v -> u)
            target_edge = causal_edges[trial % len(causal_edges)]
            u, v = target_edge.source, target_edge.target

            adv_edge = GeometryEdge(
                edge_id=f"ADV_REVERSE_{trial}",
                source=v,
                target=u,
                edge_type=EdgeType.CAUSES,
                distance=1,
            )
            graph.add_edge(adv_edge)

            errors = graph.validate_causal_dag()
            if len(errors) > 0:
                detected_count += 1

        assert detected_count == total_trials, (
            f"Adversarial sweep detection rate: {detected_count}/{total_trials} (Expected 100%)"
        )


# =============================================================================
# 3. Non-Causal Cycle Exemption (Strict Isolation, 0 False Positives)
# =============================================================================

class TestEmpiricalNonCausalCycleExemption:
    """Task 3: Verify that non-causal edges (ECHOES, PARALLELS, CONTRASTS, etc.) are exempted."""

    @pytest.fixture
    def base_clean_graph(self) -> GeometryGraph:
        params = GeometryParams(target_chapters=50, volume_count=5, seed_for_rng="non_causal_fixture")
        return GeometryGenerator(params).generate()

    @pytest.mark.parametrize("non_causal_type", [
        EdgeType.ECHOES,
        EdgeType.PARALLELS,
        EdgeType.CONTRASTS,
        EdgeType.SETS_UP,
        EdgeType.PAYS_OFF,
        EdgeType.CONVERGES,
        EdgeType.RELATIONSHIP_CHANGE,
        EdgeType.CHARACTER_ARC,
        EdgeType.SHARED_ENTITY,
        EdgeType.REACTIVATES,
        EdgeType.TRANSFORMS,
    ])
    def test_non_causal_2_node_bidirectional_cycle_exempted(
        self, base_clean_graph: GeometryGraph, non_causal_type: EdgeType
    ):
        """Two nodes mutually linked by non-causal edges (e.g. u <-> v via PARALLELS) must NOT raise cycle errors."""
        nodes = list(base_clean_graph.nodes.keys())
        u, v = nodes[10], nodes[11]

        base_clean_graph.add_edge(GeometryEdge(f"NC_FWD_{non_causal_type}", u, v, non_causal_type, 1))
        base_clean_graph.add_edge(GeometryEdge(f"NC_BWD_{non_causal_type}", v, u, non_causal_type, 1))

        errors = base_clean_graph.validate_causal_dag()
        assert errors == [], f"Non-causal type {non_causal_type} falsely raised cycle errors: {errors}"

    def test_mixed_non_causal_ring_exempted(self, base_clean_graph: GeometryGraph):
        """Ring of 4 nodes connected solely by non-causal edge types."""
        nodes = list(base_clean_graph.nodes.keys())
        u, v, w, z = nodes[20], nodes[21], nodes[22], nodes[23]

        base_clean_graph.add_edge(GeometryEdge("NC_RING_1", u, v, EdgeType.ECHOES, 1))
        base_clean_graph.add_edge(GeometryEdge("NC_RING_2", v, w, EdgeType.PARALLELS, 1))
        base_clean_graph.add_edge(GeometryEdge("NC_RING_3", w, z, EdgeType.CONTRASTS, 1))
        base_clean_graph.add_edge(GeometryEdge("NC_RING_4", z, u, EdgeType.SHARED_ENTITY, 1))

        errors = base_clean_graph.validate_causal_dag()
        assert errors == [], f"Mixed non-causal ring falsely triggered cycle errors: {errors}"

    def test_causal_path_with_non_causal_backward_echo_exempted(self, base_clean_graph: GeometryGraph):
        """
        Classic narrative motif:
        Forward causal chain: Chapter 10 -> Chapter 20 -> Chapter 30 (CAUSES)
        Backward literary motif: Chapter 30 echoes Chapter 10 (ECHOES)
        This MUST pass validate_causal_dag().
        """
        nodes = list(base_clean_graph.nodes.keys())
        c10, c20, c30 = nodes[10], nodes[20], nodes[30]

        base_clean_graph.add_edge(GeometryEdge("C_PATH_1", c10, c20, EdgeType.CAUSES, 10))
        base_clean_graph.add_edge(GeometryEdge("C_PATH_2", c20, c30, EdgeType.ENABLES, 10))
        # Non-causal backward echo
        base_clean_graph.add_edge(GeometryEdge("NC_ECHO_BACK", c30, c10, EdgeType.ECHOES, 20))

        errors = base_clean_graph.validate_causal_dag()
        assert errors == [], f"Backward ECHOES motif falsely flagged as causal cycle: {errors}"

        # Counter-test: If ECHOES is converted to ESCALATES (causal), it MUST fail immediately
        base_clean_graph.edges[-1].edge_type = EdgeType.ESCALATES
        errors_mutated = base_clean_graph.validate_causal_dag()
        assert len(errors_mutated) > 0, "Mutating backward ECHOES to ESCALATES failed to trigger cycle error"

    def test_non_causal_self_loop_exempted(self, base_clean_graph: GeometryGraph):
        """A self-loop on a non-causal edge (e.g. self-thematic ECHOES) must not trigger causal cycle error."""
        node_id = list(base_clean_graph.nodes.keys())[5]
        base_clean_graph.add_edge(GeometryEdge(
            edge_id="NC_SELF_ECHO",
            source=node_id,
            target=node_id,
            edge_type=EdgeType.ECHOES,
            distance=0,
        ))
        errors = base_clean_graph.validate_causal_dag()
        assert errors == [], f"Non-causal self loop falsely triggered causal cycle error: {errors}"


# =============================================================================
# 4. Boundary Nodes: In-Degree=0 and Out-Degree=0 Verification
# =============================================================================

class TestEmpiricalBoundaryNodes:
    """Task 4: Boundary testing for start nodes (in-degree=0) and end nodes (out-degree=0)."""

    def test_multiple_in_degree_zero_start_nodes_allowed(self):
        """DAG with multiple independent start nodes (forest of storylines)."""
        graph = GeometryGraph(GeometryParams(target_chapters=10, volume_count=1))
        # 5 start nodes merging into 1 central convergence node
        for i in range(5):
            graph.add_node(GeometryNode(f"START_{i}", NodeHierarchy(1, 1, 1), (1, 1), StructuralRole.OPEN_THREAD, f"TM0{i+1}"))
        graph.add_node(GeometryNode("CONVERGE_NODE", NodeHierarchy(1, 1, 1), (5, 5), StructuralRole.CONVERGE, "TM01"))

        for i in range(5):
            graph.add_edge(GeometryEdge(f"E_START_{i}", f"START_{i}", "CONVERGE_NODE", EdgeType.CAUSES, 4))

        assert graph.validate_causal_dag() == []

    def test_multiple_out_degree_zero_end_nodes_allowed(self):
        """DAG with 1 start node branching out into multiple end nodes (story divergence/resolutions)."""
        graph = GeometryGraph(GeometryParams(target_chapters=10, volume_count=1))
        graph.add_node(GeometryNode("ROOT_START", NodeHierarchy(1, 1, 1), (1, 1), StructuralRole.OPEN_THREAD, "TM01"))
        for i in range(5):
            graph.add_node(GeometryNode(f"END_{i}", NodeHierarchy(1, 1, 1), (10, 10), StructuralRole.PAYOFF, f"TM0{i+1}"))
            graph.add_edge(GeometryEdge(f"E_END_{i}", "ROOT_START", f"END_{i}", EdgeType.ENABLES, 9))

        assert graph.validate_causal_dag() == []

    def test_completely_isolated_nodes_allowed(self):
        """Nodes with both in-degree=0 and out-degree=0 (isolated scenes or background setups)."""
        graph = GeometryGraph(GeometryParams(target_chapters=10, volume_count=1))
        for i in range(10):
            graph.add_node(GeometryNode(f"ISO_{i}", NodeHierarchy(1, 1, 1), (i+1, i+1), StructuralRole.DEVELOP, "TM01"))
        # Add 1 causal edge between ISO_0 and ISO_1, leave the rest isolated
        graph.add_edge(GeometryEdge("E_ISO", "ISO_0", "ISO_1", EdgeType.CAUSES, 1))

        assert graph.validate_causal_dag() == []

    def test_empty_and_single_node_graphs_allowed(self):
        """Empty graph and single-node boundary graph must validate cleanly."""
        empty_graph = GeometryGraph(GeometryParams(target_chapters=1, volume_count=1))
        assert empty_graph.validate_causal_dag() == []

        single_node_graph = GeometryGraph(GeometryParams(target_chapters=1, volume_count=1))
        single_node_graph.add_node(GeometryNode("ONLY_ONE", NodeHierarchy(1, 1, 1), (1, 1), StructuralRole.DEVELOP, "TM01"))
        assert single_node_graph.validate_causal_dag() == []

    def test_generated_graphs_boundary_degree_distribution(self):
        """
        Verify on 10 realistic generated graphs:
        - In-degree 0 nodes (narrative entry points) exist.
        - Out-degree 0 nodes (narrative payoff/resolution points) exist.
        - Neither start nodes nor end nodes violate Kahn's topological sort.
        """
        for s in range(10):
            params = GeometryParams(target_chapters=50, volume_count=5, seed_for_rng=f"boundary_dist_{s}")
            graph = GeometryGenerator(params).generate()

            causal_edges = [e for e in graph.edges if e.edge_type in CAUSAL_EDGE_TYPES]
            in_deg = {nid: 0 for nid in graph.nodes}
            out_deg = {nid: 0 for nid in graph.nodes}

            for e in causal_edges:
                in_deg[e.target] += 1
                out_deg[e.source] += 1

            start_nodes = [nid for nid, deg in in_deg.items() if deg == 0]
            end_nodes = [nid for nid, deg in out_deg.items() if deg == 0]

            assert len(start_nodes) > 0, f"Graph seed {s} has no causal start nodes (in-degree=0)"
            assert len(end_nodes) > 0, f"Graph seed {s} has no causal end nodes (out-degree=0)"
            assert graph.validate_causal_dag() == []


# =============================================================================
# 5. Heavy Load & Multi-Thread Memberships Verification
# =============================================================================

class TestEmpiricalHeavyLoadAndThreadMemberships:
    """Stress testing scale (500 and 1000 chapters), thread memberships, and execution performance."""

    @pytest.mark.parametrize("target_chapters,volume_count", [
        (500, 20),
        (1000, 30),
    ])
    def test_heavy_load_generation_and_dag_integrity(self, target_chapters: int, volume_count: int):
        """Stress-test massive novel scale with 500 and 1000 chapters."""
        start_time = time.time()
        params = GeometryParams(
            target_chapters=target_chapters,
            volume_count=volume_count,
            complexity=GeometryComplexity.STANDARD,
            seed_for_rng=f"heavy_load_{target_chapters}",
        )
        generator = GeometryGenerator(params)
        graph = generator.generate()
        duration = time.time() - start_time

        # Performance assertion: 1000 chapters must generate within reasonable time (< 15 seconds)
        assert duration < 15.0, f"Generation took too long: {duration:.2f}s"

        # 1. Volume count invariant
        assert len(graph.volumes) >= volume_count

        # 2. 24 Core Threads invariant
        main_threads = [t for t in graph.threads.values() if t.thread_id.startswith("TM")]
        sub_threads = [t for t in graph.threads.values() if t.thread_id.startswith("TS")]
        assert len(main_threads) == 6, f"Expected 6 main threads, got {len(main_threads)}"
        assert len(sub_threads) == 18, f"Expected 18 sub threads, got {len(sub_threads)}"

        # 3. 100% of nodes have thread memberships populated
        nodes_with_memberships = 0
        crossover_nodes = 0
        for n in graph.nodes.values():
            memberships = getattr(n, "thread_memberships", [])
            assert len(memberships) >= 1, f"Node {n.node_id} has empty thread_memberships"
            nodes_with_memberships += 1
            if len(memberships) >= 2:
                crossover_nodes += 1

        assert nodes_with_memberships == len(graph.nodes)
        assert crossover_nodes > 0, "No crossover nodes found in heavy load graph"

        # 4. Strict Causal DAG validation
        assert graph.validate_causal_dag() == []
