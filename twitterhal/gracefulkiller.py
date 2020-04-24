import logging
import signal
import time


logger = logging.getLogger(__name__)


class GracefulKiller:
    kill_now = False
    alarm = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        signal.signal(signal.SIGALRM, self.set_alarm)

    def set_alarm(self, *args, **kwargs):
        self.alarm = True

    def exit_gracefully(self, *args, **kwargs):
        logger.info("Received signal to exit")
        self.kill_now = True

    def sleep(self, seconds: int) -> bool:
        # A "friendlier" sleep method, that always takes <= 1 sec to wake up
        # after a signal has been received.
        # Returns True if we caught SIGALRM, False otherwise
        alarm = False
        for _ in range(seconds):
            if self.alarm:
                self.alarm = False
                alarm = True
            if not self.kill_now:
                time.sleep(1)
        return alarm


killer = GracefulKiller()
