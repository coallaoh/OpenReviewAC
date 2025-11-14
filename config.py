"""
Configuration for OpenReview AC Workflow
=========================================

This file contains all configuration settings for the OpenReview AC workflow automation.
Update these values to match your conference and environment.

Quick Start:
    1. Set CONFERENCE_NAME to your conference
    2. Add GSHEET_CREDENTIALS_PATH to your .env file
    3. Optionally customize other settings below
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
# This is loaded from the .env file
# Get this from Google Cloud Console: https://console.cloud.google.com/
GSHEET_CREDENTIALS_PATH = os.getenv('GSHEET_CREDENTIALS_PATH', 'your-service-account-key.json')

# Title of your Google Sheet (will be created if it doesn't exist)
GSHEET_TITLE = f"{CONFERENCE_NAME} AC DB"

# Name of the worksheet/tab within the Google Sheet
GSHEET_SHEET = "Sheet1"

# Title template for Author DB Google Sheet (will be formatted with conference name)
GSHEET_AUTHOR_TITLE_TEMPLATE = "{conference} Author DB"

# Name of the worksheet/tab for Author DB
GSHEET_AUTHOR_SHEET = "Sheet1"

# ============================================================================
# INITIALIZATION OPTIONS
# ============================================================================
# Set to True to clear the sheet and start fresh
# Set to False to update existing data based on paper_number
INITIALIZE_SHEET = True

# Batch size for writing rows to Google Sheets
GSHEET_BATCH_SIZE = 1000

# ============================================================================
# CONFERENCE INFORMATION
# ============================================================================
# This dictionary defines conference-specific extractors and identifiers.
# Each conference may have different OpenReview API structures, so we need
# custom extractors to handle variations in how ratings, notes, and other
# data are structured.
#
# Key components for each conference:
#   - CONFERENCE_ID: OpenReview identifier for the conference
#   - RATING_EXTRACTOR: Function to extract initial review ratings
#   - FINAL_RATING_EXTRACTOR: Function to extract final/updated ratings (optional)
#   - PAPER_NUMBER_EXTRACTOR: Function to extract paper number from paper object
#   - NOTE_EXTRACTORS: Dictionary of functions to identify different note types
#
# To add a new conference, copy an existing entry and modify the extractors
# to match your conference's OpenReview structure.
# ============================================================================

CONFERENCE_INFO = {
    "ICML2025": dict(
        CONFERENCE_ID = 'ICML.cc/2025/Conference',
        RATING_EXTRACTOR = lambda review: review.content["overall_recommendation"]['value'],
        PAPER_NUMBER_EXTRACTOR = lambda paper: paper.number,
        NOTE_KEYS = {
            'review': 'summary',
            'comment': 'comment',
            'acknowledgement': 'acknowledgement',
            'rebuttal': 'rebuttal'
        }
    ),
    "ICCV2025": dict(
        CONFERENCE_ID = 'thecvf.com/ICCV/2025/Conference',
        # RATING_EXTRACTOR = lambda review: int(
        #     review.content["preliminary_recommendation"]['value'].split(":")[0]
        # )
        FINAL_RATING_EXTRACTOR = lambda review: (
            int(review.content["final_recommendation"]['value'].split(":")[0])
            if "final_recommendation" in review.content
            and "value" in review.content["final_recommendation"]
            else None
        ),
        PAPER_NUMBER_EXTRACTOR = lambda paper: paper.number,
        NOTE_EXTRACTORS = {
            'review': lambda note: 'preliminary_recommendation' in note.content,
            'comment': lambda note: 'comment' in note.content,
            'rebuttal': lambda note: ('pdf' in note.content and 'abstract' not in note.content),
            'ac_letter': lambda note: (
                'pdf' in note.content
                and 'abstract' not in note.content
                and 'value' in note.content['confidential_comments_to_AC']
            ),
        }
    ),
    "NeurIPS2025": dict(
        CONFERENCE_ID = 'NeurIPS.cc/2025/Conference',
        RATING_EXTRACTOR = lambda review: (
            int(review.content["rating"]['value'])
            if "rating" in review.content and "value" in review.content["rating"]
            else None
        ),
        PAPER_NUMBER_EXTRACTOR = lambda paper: paper.number,
        NOTE_EXTRACTORS = {
            'review': lambda note: any(
                invitation.endswith('Official_Review') for invitation in note.invitations
            ),
            'final_justification': lambda note: (
                "final_justification" in note.content
                and any(invitation.endswith('Official_Review') for invitation in note.invitations)
            ),
            'other_comment': lambda note: (
                any(invitation.endswith('Official_Comment') for invitation in note.invitations)
                and not (
                    any(
                        writer for writer in note.writers
                        if writer.split('/')[-1].startswith('Reviewer')
                    )
                    and any(
                        reader for reader in note.readers
                        if reader.split('/')[-1].startswith('Author')
                    )
                )
            ),
            'discussion_comment': lambda note: (
                any(
                    invitation.endswith('Official_Comment')
                    for invitation in note.invitations
                )
                and any(
                    writer for writer in note.writers
                    if writer.split('/')[-1].startswith('Reviewer')
                )
                and any(
                    reader for reader in note.readers
                    if reader.split('/')[-1].startswith('Author')
                )
            ),
            'rebuttal': lambda note: any(
                invitation.endswith('Rebuttal')
                for invitation in note.invitations
            ),
            'rebuttal_acknowledgement': lambda note: (
                any(
                    invitation.endswith('Mandatory_Acknowledgement')
                    for invitation in note.invitations
                )
            ),
            'ac_letter_author': lambda note: (
                any(
                    invitation.endswith('Author_AC_Confidential_Comment')
                    for invitation in note.invitations
                )
                and any(
                    writer for writer in note.writers
                    if writer.split('/')[-1].startswith('Author')
                )
            ),
            'ac_letter_ac': lambda note: (
                any(
                    invitation.endswith('Author_AC_Confidential_Comment')
                    for invitation in note.invitations
                )
                and any(
                    writer for writer in note.writers
                    if writer.split('/')[-1].startswith('Area_Chair')
                )
            ),
        }
    ),
    "ICLR2026": dict(
        CONFERENCE_ID = 'ICLR.cc/2026/Conference',
        RATING_EXTRACTOR = lambda review: (
            int(review.content["rating"]['value'])
            if "rating" in review.content and "value" in review.content["rating"]
            else None
        ),
        PAPER_NUMBER_EXTRACTOR = lambda paper: paper.number,
        NOTE_EXTRACTORS = {
            'review': lambda note: any(
                invitation.endswith('Official_Review') for invitation in note.invitations
            ),
            'final_justification': lambda note: (
                "final_justification" in note.content
                and any(invitation.endswith('Official_Review') for invitation in note.invitations)
            ),
            'other_comment': lambda note: (
                any(
                    invitation.endswith('Official_Comment')
                    for invitation in note.invitations
                )
                and not (
                    any(
                        writer for writer in note.writers
                        if writer.split('/')[-1].startswith('Reviewer')
                    )
                    and any(
                        reader for reader in note.readers
                        if reader.split('/')[-1].startswith('Author')
                    )
                )
            ),
            'discussion_comment': lambda note: (
                any(
                    invitation.endswith('Official_Comment')
                    for invitation in note.invitations
                )
                and any(
                    writer for writer in note.writers
                    if writer.split('/')[-1].startswith('Reviewer')
                )
                and any(
                    reader for reader in note.readers
                    if reader.split('/')[-1].startswith('Author')
                )
            ),
            'rebuttal': lambda note: any(
                invitation.endswith('Rebuttal')
                for invitation in note.invitations
            ),
            'rebuttal_acknowledgement': lambda note: (
                any(
                    invitation.endswith('Mandatory_Acknowledgement')
                    for invitation in note.invitations
                )
            ),
            'ac_letter_author': lambda note: (
                any(
                    invitation.endswith('Author_AC_Confidential_Comment')
                    for invitation in note.invitations
                )
                and any(
                    writer for writer in note.writers
                    if writer.split('/')[-1].startswith('Author')
                )
            ),
            'ac_letter_ac': lambda note: (
                any(
                    invitation.endswith('Author_AC_Confidential_Comment')
                    for invitation in note.invitations
                )
                and any(
                    writer for writer in note.writers
                    if writer.split('/')[-1].startswith('Area_Chair')
                )
            ),
        }
    )
}[CONFERENCE_NAME]

