from fastapi import Request

from .scheduler import MonitorScheduler
from .store import MonitorStore


def get_store(request: Request) -> MonitorStore:
    return request.app.state.store


def get_scheduler(request: Request) -> MonitorScheduler:
    return request.app.state.scheduler
