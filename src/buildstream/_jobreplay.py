import multiprocessing
import pickle

import click

from ._scheduler.jobs.job import _do_pickled_child_job


@click.command(name='bst-job-replay', short_help="Replay a bst job")
@click.argument('replayfile', type=click.File("rb"))
def cli(replayfile):
    queue = multiprocessing.Queue()
    _do_pickled_child_job(replayfile, queue)