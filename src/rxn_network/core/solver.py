" Basic interface for a pathway Solver "
import logging
from abc import ABCMeta, abstractmethod
from typing import List

from monty.json import MSONable

from rxn_network.core.pathway import Pathway


class Solver(MSONable, metaclass=ABCMeta):
    " Base definition for a pathway solver class. "
    def __init__(self, entries, pathways):
        self.logger = logging.getLogger(str(self.__class__.__name__))
        self.logger.setLevel("INFO")

        self._entries = entries
        self._pathways = pathways
        self._reactions = list(
            {rxn for path in self._pathways for rxn in path.reactions}
        )

        self._costs = [cost for path in self._pathways for cost in path.costs]

    @abstractmethod
    def solve(self, net_rxn) -> List[Pathway]:
        "Solve paths"

    @property
    def entries(self):
        return self._entries

    @property
    def pathways(self):
        return self._pathways

    @property
    def reactions(self):
        return self._reactions

    @property
    def costs(self):
        return self._costs

    @property
    def num_rxns(self):
        return len(self.reactions)

    @property
    def num_entries(self):
        return len(self._entries)
