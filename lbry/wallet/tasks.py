import asyncio
from asyncio import Event


class TaskGroup:

    def __init__(self, loop=None):
        self._loop = loop
        self._tasks = set()
        self.done = Event()
        self.started = Event()

    @property
    def loop(self):
        """Get the event loop, preferring the running loop if available."""
        if self._loop:
            return self._loop
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.get_event_loop()

    def __len__(self):
        return len(self._tasks)

    def add(self, coro):
        task = self.loop.create_task(coro)
        self._tasks.add(task)
        self.started.set()
        self.done.clear()
        task.add_done_callback(self._remove)
        return task

    def _remove(self, task):
        self._tasks.remove(task)
        if len(self._tasks) < 1:
            self.done.set()
            self.started.clear()

    def cancel(self):
        for task in self._tasks:
            task.cancel()
        self.done.set()
        self.started.clear()
