import asyncio
from contextlib import suppress

from .checker import HealthChecker
from .notifier import EmailNotifier
from .store import MonitorStore


class MonitorScheduler:
    def __init__(self, store: MonitorStore, checker: HealthChecker, notifier: EmailNotifier) -> None:
        self._store = store
        self._checker = checker
        self._notifier = notifier
        self._stopping = asyncio.Event()

    async def run(self) -> None:
        self._store.scheduler_running = True
        try:
            while not self._stopping.is_set():
                monitors = await self._store.claim_due_monitors()
                if monitors:
                    await asyncio.gather(*(self._check_and_notify(monitor.id, monitor) for monitor in monitors))
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
        finally:
            self._store.scheduler_running = False

    async def stop(self) -> None:
        self._stopping.set()

    async def check_now(self, monitor_id: str):
        monitor = await self._store.claim_monitor(monitor_id)
        await self._check_and_notify(monitor_id, monitor)
        return await self._store.get_monitor_response(monitor_id)

    async def _check_and_notify(self, monitor_id: str, monitor) -> None:
        try:
            result = await self._checker.check(monitor)
            event = await self._store.finish_check(monitor_id, result)
            if event is not None:
                config = await self._store.get_email_config()
                recipients = await self._store.get_enabled_recipient_emails()
                error = await self._notifier.send_event(config, recipients, event)
                await self._store.record_notification_error(monitor_id, error)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Network failures are handled by HealthChecker. This only protects the scheduler loop.
            await self._store.record_notification_error(monitor_id, "Scheduler task failed: {}".format(type(exc).__name__))
