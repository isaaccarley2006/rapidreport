#!/usr/bin/env python3
"""CLI entry point: send the latest report via email (run via cron on Sundays)."""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.report import send_weekly_report

if __name__ == "__main__":
    send_weekly_report()
