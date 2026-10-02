"""Händler-Registry. Neuer Händler: ``retailers/<key>.py`` anlegen und hier eintragen."""

from .base import Retailer
from .lidl import LIDL
from .penny import PENNY
from .rewe import REWE

RETAILERS = {r.key: r for r in (LIDL, REWE, PENNY)}


def get(key):
    return RETAILERS[key]
