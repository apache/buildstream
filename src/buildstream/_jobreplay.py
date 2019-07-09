import multiprocessing

import click

from ._scheduler.jobs.job import _unpickle_child_job


@click.command(name='bst-job-replay', short_help="Replay a bst job")
@click.argument('replayfile', type=click.File("rb"))
def cli(replayfile):
    job = _unpickle_child_job(replayfile)
    queue = multiprocessing.Queue()
    job._queue = queue
    job._scheduler_context.set_message_handler(job._child_message_handler)
    job.child_process()
