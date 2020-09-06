from concurrent.futures import Future
from threading import Lock
from typing import Any, Callable, Dict, List, Optional


class Task:
    function: Callable
    kwargs: Dict[str, Any]
    name: str

    def __call__(self): ...
    def __init__(self, function: Callable, **kwargs): ...
    def __repr__(self) -> str: ...


class Worker(Task):
    future: Future


class LoopTask(Task):
    lock: Lock
    sleep: Optional[int]
    seconds_until_forced_unlock: Optional[int]
    last_run = Optional[int]

    def __init__(self, function, sleep: Optional[int], seconds_until_forced_unlock: Optional[int], **kwargs): ...


class Runner:
    loop_tasks: List[LoopTask]
    post_loop_tasks: List[Task]
    sleep_seconds: int
    workers: List[Worker]

    def __init__(self, sleep_seconds: int): ...
    def register_loop_task(self, function: Callable, sleep: Optional[int], **kwargs): ...
    def register_post_loop_task(self, function: Callable, **kwargs): ...
    def register_worker(self, function: Callable, **kwargs): ...
    def restart_stopped_workers(self): ...
    def run_loop_tasks(self): ...
    def run_post_loop_tasks(self): ...
    def run(self, test: bool): ...
    def start_workers(self): ...


runner: Runner
