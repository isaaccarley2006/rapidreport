#!/usr/bin/env python3
"""CLI entry point: generate this week's report (run via cron on Fridays)."""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.report import generate_weekly_report

if __name__ == "__main__":
    generate_weekly_report()
