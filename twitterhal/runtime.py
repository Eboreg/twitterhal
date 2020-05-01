import inspect
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from twitterhal.gracefulkiller import killer


logger = logging.getLogger(__name__)


class Task:
    def __init__(self, function, **kwargs):
        self.function = function
        self.kwargs = kwargs

    def __call__(self):
        self.function(**self.kwargs)

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name}>"

    @property
    def name(self):
        return self.function.__name__


class Worker(Task):
    def __init__(self, function, **kwargs):
        if "restart" in kwargs:
            raise ValueError("kwargs to Worker.__init__ cannot contain `restart`")
        sig = inspect.signature(function)
        try:
            sig.bind(restart=True, **kwargs)
        except TypeError:
            self.accepts_restart_kwarg = False
        else:
            self.accepts_restart_kwarg = True
        super().__init__(function, **kwargs)

    def __call__(self, restart=False):
        if restart and self.accepts_restart_kwarg:
            self.function(restart=True, **self.kwargs)
        else:
            self.function(**self.kwargs)


class LoopTask(Task):
    def __init__(self, function, sleep=None, **kwargs):
        self.sleep = sleep
        self.lock = Lock()
        super().__init__(function, **kwargs)

    def __call__(self):
        # If we are to wait until the previous run has completed, *and* it
        # hasn't; return without doing anything.
        # In all other cases; run the function
        if self.sleep is not None:
            if not self.lock.locked():
                with self.lock:
                    self.function(**self.kwargs)
                    killer.sleep(self.sleep)
            else:
                logger.debug(f"Loop task {self.name} still locked by previous run (sleep={self.sleep})")
        else:
            self.function(**self.kwargs)


class Runner:
    """
    TODO:
    Gör task- och worker-listor "interna" genom att döpa till _*
    """

    def __init__(self, sleep_seconds):
        self.sleep_seconds = sleep_seconds
        self.loop_tasks = []
        self.post_loop_tasks = []
        self.workers = []

    def start_workers(self):
        for worker in self.workers:
            logger.info(f"Starting worker: {worker.name} ...")
            worker.future = self.executor.submit(worker)

    def restart_stopped_workers(self):
        for worker in self.workers:
            if not worker.future.running():
                exc = worker.future.exception()
                if exc is not None:
                    logger.error(f"Worker {worker.name} raised exception: {exc}. Restarting ...")
                else:
                    logger.error(f"Worker {worker.name} exited without exception. Restarting ...")
                worker.future = self.executor.submit(worker, restart=True)

    def register_worker(self, function, **kwargs):
        assert callable(function), "`function` must be a callable"
        logger.info(f"Registering {function.__name__} as Worker ...")
        self.workers.append(Worker(function, **kwargs))

    def register_loop_task(self, function, sleep=None, **kwargs):
        assert callable(function), "`function` must be a callable"
        assert sleep is None or (isinstance(sleep, int) and sleep >= 0), "`sleep` must be None or a positive integer"
        logger.info(f"Registering {function.__name__} as LoopTask with sleep={sleep} ...")
        self.loop_tasks.append(LoopTask(function, sleep, **kwargs))

    def register_post_loop_task(self, function, **kwargs):
        assert callable(function), "`function` must be a callable"
        logger.info(f"Registering {function.__name__} as PostLoopTask ...")
        self.post_loop_tasks.append(Task(function, **kwargs))

    def run_loop_tasks(self):
        for task in self.loop_tasks:
            logger.debug(f"Starting loop task: {task.name} ...")
            self.executor.submit(task)

    def run_post_loop_tasks(self):
        for task in self.post_loop_tasks:
            logger.info(f"Starting post loop task: {task.name} ...")
            task()

    def run(self):
        with ThreadPoolExecutor() as self.executor:
            self.start_workers()
            while not killer.kill_now:
                self.run_loop_tasks()
                self.restart_stopped_workers()
                alarm = killer.sleep(self.sleep_seconds)
                if alarm:
                    logger.info("Pong!")
            self.run_post_loop_tasks()
            logger.info("Waiting for threads to finish ...")


runner: "Runner" = Runner(5)
