"""Händler-Registry. Neuer Händler: ``retailers/<key>.py`` anlegen und hier eintragen."""

from .base import Retailer
from .lidl import LIDL
from .rewe import REWE

RETAILERS = {r.key: r for r in (LIDL, REWE)}


def get(key):
    return RETAILERS[key]
