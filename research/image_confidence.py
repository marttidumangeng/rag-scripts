"""Re-export shared confidence helpers for research scripts.

Research CLIs and tests must include the Django server root on ``PYTHONPATH`` so
``robots.image_confidence`` resolves, for example::

    PYTHONPATH=/path/to/robotaigeek-server python -m pytest tests/test_image_confidence.py -v
"""
from robots.image_confidence import *  # noqa: F403
