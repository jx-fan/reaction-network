"Implementation of reaction network interface"
import logging
from typing import List

import graph_tool.all as gt

from rxn_network.core import Network
from rxn_network.entries.entry_set import GibbsEntrySet
from rxn_network.network.adaptors.gt import (
    initialize_graph,
    update_vertex_props,
    yens_ksp,
)
from rxn_network.network.entry import NetworkEntry, NetworkEntryType
from rxn_network.network.utils import get_loopback_edges, get_rxn_nodes_and_edges
from rxn_network.pathways.basic import BasicPathway
from rxn_network.reactions.computed import ComputedReaction
from rxn_network.reactions.reaction_set import ReactionSet


class ReactionNetwork(Network):
    """
    Main reaction network class for building graphs of reactions and performing
    pathfinding.
    """

    def __init__(
        self,
        entries: GibbsEntrySet,
        enumerators,
        cost_function,
        open_elem=None,
        chempot=None,
    ):
        super().__init__(
            entries=entries, enumerators=enumerators, cost_function=cost_function
        )
        self.open_elem = open_elem
        self.chempot = chempot

    def build(self):
        """

        Returns:

        """
        rxn_set = self._get_rxns()
        costs = rxn_set.calculate_costs(self.cost_function)
        rxns = rxn_set.get_rxns(self.open_elem, self.chempot)

        nodes, rxn_edges = get_rxn_nodes_and_edges(rxns)

        g = initialize_graph()
        g.add_vertex(len(nodes))
        for i, network_entry in enumerate(nodes):
            props = {"entry": network_entry, "type": network_entry.description.value}
            update_vertex_props(g, g.vertex(i), props)

        edge_list = []
        for edge, cost, rxn in zip(rxn_edges, costs, rxns):
            v1 = g.vertex(edge[0])
            v2 = g.vertex(edge[1])
            edge_list.append((v1, v2, cost, rxn, "reaction"))

        loopback_edges = get_loopback_edges(g, nodes)
        edge_list.extend(loopback_edges)

        g.add_edge_list(edge_list, eprops=[g.ep["cost"], g.ep["rxn"], g.ep["type"]])

        self._g = g

    def find_pathways(self, targets, k=15):
        """

        Args:
            targets:
            k:

        Returns:

        """
        if not self.precursors:
            raise AttributeError("Must call set_precursors() before pathfinding!")

        paths = []
        for target in targets:
            if type(target) == str:
                target = self.entries.get_min_entry_by_formula(target)
            self.set_target(target)
            print(f"PATHS to {target.composition.reduced_formula} \n")
            print("--------------------------------------- \n")
            pathways = self._shortest_paths(k=k)
            paths.extend(pathways)

        return paths

    def set_precursors(self, precursors):
        """

        Args:
            precursors:

        Returns:

        """
        g = self._g

        precursors = set(precursors)
        if precursors == self.precursors:
            return
        elif self.precursors:
            precursors_v = gt.find_vertex(g, g.vp["type"],
                                          NetworkEntryType.Precursors.value)[0]
            g.remove_vertex(precursors_v)
            loopback_edges = gt.find_edge(g, g.ep["type"], "loopback_precursors")
            for e in loopback_edges:
                g.remove_edge(e)
        elif not all([p in self.entries for p in precursors]):
            raise ValueError("One or more precursors are not included in network!")

        precursors_v = g.add_vertex()
        precursors_entry = NetworkEntry(precursors, NetworkEntryType.Precursors)
        props = {"entry": precursors_entry, "type": precursors_entry.description.value}
        update_vertex_props(g, precursors_v, props)

        add_edges = []
        for v in g.vertices():
            entry = g.vp["entry"][v]
            if not entry:
                continue
            if entry.description.value == NetworkEntryType.Reactants.value:
                if entry.entries.issubset(precursors):
                    add_edges.append((precursors_v, v, 0.0, None, "precursors"))
            elif entry.description.value == NetworkEntryType.Products.value:
                for v2 in g.vertices():
                    entry2 = g.vp["entry"][v2]
                    if entry2.description.value == NetworkEntryType.Reactants.value:
                        if precursors.issuperset(entry2.entries):
                            continue
                        if precursors.union(entry.entries).issuperset(entry2.entries):
                            add_edges.append((v, v2, 0.0, None, "loopback_precursors"))

        g.add_edge_list(add_edges, eprops=[g.ep["cost"], g.ep["rxn"], g.ep["type"]])

        self.precursors = precursors

    def set_target(self, target):
        """

        Args:
            target:

        Returns:

        """
        g = self._g
        if target == self.target:
            return
        elif self.target or target==None:
            target_v = gt.find_vertex(g, g.vp["type"], NetworkEntryType.Target.value)[0]
            g.remove_vertex(target_v)

        target_v = g.add_vertex()
        target_entry = NetworkEntry([target], NetworkEntryType.Target)
        props = {"entry": target_entry, "type": target_entry.description.value}
        update_vertex_props(g, target_v, props)

        add_edges = []
        for v in g.vertices():
            entry = g.vp["entry"][v]
            if not entry:
                continue
            if entry.description.value != NetworkEntryType.Products.value:
                continue
            if target in entry.entries:
                add_edges.append([v, target_v, 0.0, None, "target"])

        g.add_edge_list(add_edges, eprops=[g.ep["cost"], g.ep["rxn"], g.ep["type"]])

        self.target = target

    def _shortest_paths(self, k=15):
        " Finds the k shortest paths using Yen's algorithm and returns BasicPathways"
        g = self._g
        paths = []

        precursors_v = gt.find_vertex(
            g, g.vp["type"], NetworkEntryType.Precursors.value
        )[0]
        target_v = gt.find_vertex(g, g.vp["type"], NetworkEntryType.Target.value)[0]

        for path in yens_ksp(g, k, precursors_v, target_v):
            paths.append(BasicPathway.from_graph_path(g, path))

        for path in paths:
            print(path, "\n")

        return paths

    def _get_rxns(self) -> ReactionSet:
        " Gets reaction set by running all enumerators"
        rxns = []
        for enumerator in self.enumerators:
            rxns.extend(enumerator.enumerate(self.entries))

        rxns = ReactionSet.from_rxns(rxns, self.entries)
        return rxns

    @property
    def graph(self):
        return self._g

    @property
    def chemsys(self):
        return "-".join(sorted(self.entries.chemsys))

    def __repr__(self):
        return (
            f"ReactionNetwork for chemical system: "
            f"{self.chemsys}, "
            f"with Graph: {str(self._g)}"
        )
