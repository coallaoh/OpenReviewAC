"""
Configuration Example for OpenReview AC Workflow

This file demonstrates how to customize the configuration constants in main_ac_tasks.py
Copy and modify these values in main_ac_tasks.py to match your needs.
"""

# ============================================================================
# CONFERENCE SELECTION
# ============================================================================
# Choose which conference you're working with
# Options: "ICLR2026", "NeurIPS2025", "ICCV2025", "ICML2025"
CONFERENCE_NAME = "ICLR2026"

# ============================================================================
# CACHE CONFIGURATION
# ============================================================================
# Directory where OpenReview data will be cached
CACHE_ROOT = f"data/{CONFERENCE_NAME}/"

# ============================================================================
# GOOGLE SHEETS CONFIGURATION
# ============================================================================
# Path to your Google Sheets service account JSON key file
# Get this from Google Cloud Console: https://console.cloud.google.com/
GSHEET_JSON = "your-service-account-key.json"

# Title of your Google Sheet (will be created if it doesn't exist)
GSHEET_TITLE = f"{CONFERENCE_NAME} AC DB"

# Name of the worksheet/tab within the Google Sheet
GSHEET_SHEET = "Sheet1"

# ============================================================================
# INITIALIZATION OPTIONS
# ============================================================================
# Set to True to clear the sheet and start fresh
# Set to False to update existing data
INITIALIZE_SHEET = False

# ============================================================================
# NOTES ON ADDING NEW CONFERENCES
# ============================================================================
# To add support for a new conference, you need to add an entry to CONFERENCE_INFO
# in main_ac_tasks.py with the following keys:
#
# Required keys:
# - CONFERENCE_ID: str - The OpenReview conference ID (e.g., 'ICLR.cc/2026/Conference')
# - PAPER_NUMBER_EXTRACTOR: function - Lambda to extract paper number from paper object
# - NOTE_EXTRACTORS: dict - Dictionary of note type extractors
#
# Optional keys:
# - RATING_EXTRACTOR: function - Lambda to extract rating from review
# - FINAL_RATING_EXTRACTOR: function - Lambda to extract final rating from review
#
# See existing entries in main_ac_tasks.py for examples.

