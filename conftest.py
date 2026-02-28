"""Conftest: add repo root to sys.path so 'backend.*' imports resolve."""
import sys
import os

# Ensure the repo root (child-localization/) is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
