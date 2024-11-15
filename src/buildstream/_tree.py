import os
import pickle as pkl

from typing import List

class Tree:
    def __init__(self):
        self.nodes = set()
        self.links = dict()
    
    def link(self, predecessor: str, successor: str) -> None:
        self.links.setdefault(successor, [])
        self.links.setdefault(predecessor, [])

        if successor == predecessor:
            raise ValueError(f'Predecessor and successor are identical: {successor}={predecessor}')
        elif successor in self.links[predecessor]:
            raise ValueError(f'Cycle detected - not valid tree: {successor}<=>{predecessor}')

        for n in [predecessor, successor]:
            self.nodes.add(n)

        self.links[successor].append(predecessor)

    def save(self, path: str, format_: str = 'dot') -> None:
        """Saves the tree to disk.

        dot: A graphviz .dot file.
        pkl: A treelib compatible dictionary .pkl file.
        """
        with open(f'{path}.{format_}', 'w+') as file:
            if format_ == 'pkl':
                pkl.dump(self.links, file) 
            elif format_ == 'dot':
                lines = [f'digraph "{path}" {{']
                lines.extend(f'    "{n}" [label="{n}"]' for n in self.nodes)
                lines.extend(f'    "{p}" -> "{s}"' for s, ps in self.links.items() for p in ps)
                lines.append(f'}}')

                file.writelines([f'{l}\n' for l in lines])
            else:
                raise ValueError(f'Unknown format: {format_}')
