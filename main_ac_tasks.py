"""
OpenReview AC Workflow Automation
==================================

Automates the Area Chair (AC) workflow for OpenReview conferences by:
- Retrieving papers assigned to you as an Area Chair
- Extracting review scores, comments, and discussion activity
- Writing all data to a Google Sheet for easy tracking and management

Usage:
    1. Set up environment variables (see .env.example):
       - OPENREVIEW_USERNAME: Your OpenReview email
       - OPENREVIEW_PASSWORD: Your OpenReview password
    
    2. Configure the settings below (CONFERENCE_NAME, GSHEET_JSON, etc.)
    
    3. Run the script:
       python main_ac_tasks.py

Supported Conferences:
    - ICLR2026
    - NeurIPS2025
    - ICCV2025
    - ICML2025

For detailed setup instructions, see README.md
"""
import logging
from utils.gsheet import GSheetWithHeader
from utils.openreview import OpenReviewPapers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ============================================================================
# CONFIGURATION - Update these values for your use case
# ============================================================================

# Conference selection: Choose from "ICLR2026", "NeurIPS2025", "ICCV2025", "ICML2025"
CONFERENCE_NAME = "ICLR2026"

# Cache directory: Where to store cached OpenReview data
CACHE_ROOT = f"data/{CONFERENCE_NAME}/"

# Google Sheets service account key file
# Get this from Google Cloud Console after setting up a service account
# See README.md for detailed instructions
GSHEET_JSON = "your-service-account-key.json"

# Google Sheet configuration
GSHEET_TITLE = f"{CONFERENCE_NAME} AC DB"  # Name of the Google Sheet
GSHEET_SHEET = "Sheet1"                     # Name of the worksheet/tab

# Initialize sheet: Set to True to clear existing data and start fresh
# Set to False to update existing rows based on paper_number
INITIALIZE_SHEET = False

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


class OpenReviewACPapers(OpenReviewPapers):
    """
    OpenReviewACPapers handles operations for Area Chair-specific paper management
    for a particular conference in OpenReview. This includes retrieving lists of
    papers assigned to an Area Chair and extracting relevant review and discussion
    information using conference-specific logic as defined in CONFERENCE_INFO.
    """
    def get_ac_papers_list(self):
        """
        Retrieves a list of papers assigned to the Area Chair for a given conference.
        This includes:
        - Retrieving the list of Area Chair members
        - Checking if the current user is an Area Chair
        - Fetching all submissions assigned to the Area Chair
        - Extracting review scores and other relevant information
        """
        logging.info("Starting to retrieve AC papers list")
        ac_group_id = f'{self.conference_id}/Area_Chairs'
        ac_group_list = self.openreview_client.get_group(ac_group_id).members
        if not ac_group_list:
            logging.warning("No AC information for %s.", self.conference_id)
            return []

        profile = self.openreview_client.get_profile()
        if profile.id not in ac_group_list:
            logging.warning("You are not an area chair for %s.", self.conference_id)
            return []

        user_id = profile.id
        logging.info("Getting groups for user %s", user_id)
        user_groups = self.openreview_client.get_groups(member=user_id)
        # Get all AC-related groups (both Area_Chair and Area_Chairs)
        ac_groups = [g.id for g in user_groups if 'Area_Chair' in g.id]
        logging.info("Found %d AC groups for user", len(ac_groups))

        # Extract paper numbers from AC groups (e.g., "Submission10059" -> 10059)
        # Try two methods:
        # 1. Look for specific AC assignments (Area_Chair_{code}) - used by ICLR
        # 2. Fall back to checking paper.readers if method 1 finds nothing - used by others
        assigned_paper_numbers = set()
        specific_ac_groups = []
        pool_ac_groups = []
        
        for ac_group in ac_groups:
            # Method 1: Look for specific assignments like "ICLR.cc/2026/Conference/Submission10059/Area_Chair_wGtT"
            if (self.conference_id in ac_group and 
                '/Submission' in ac_group and 
                '/Area_Chair_' in ac_group):
                specific_ac_groups.append(ac_group)
                parts = ac_group.split('/Submission')
                if len(parts) > 1:
                    paper_num_str = parts[1].split('/')[0]
                    try:
                        assigned_paper_numbers.add(int(paper_num_str))
                    except ValueError:
                        pass
            # Method 2: Collect pool groups for fallback (e.g., ".../Submission123/Area_Chairs")
            elif (self.conference_id in ac_group and 
                  '/Submission' in ac_group and 
                  ac_group.endswith('/Area_Chairs')):
                pool_ac_groups.append(ac_group)
        
        use_specific_assignment = len(specific_ac_groups) > 0
        
        if use_specific_assignment:
            logging.info("Found %d specific AC assignment groups (Area_Chair_XXX) for %s", 
                         len(specific_ac_groups), self.conference_id)
            logging.info("Using specific AC assignment method")
        else:
            logging.info("No specific AC assignments found, will use paper.readers method (legacy)")
            logging.info("Found %d pool AC groups for %s", len(pool_ac_groups), self.conference_id)
        
        if assigned_paper_numbers:
            logging.info("Pre-filtered %d assigned paper numbers", len(assigned_paper_numbers))
            logging.info("Assigned papers: %s", sorted(list(assigned_paper_numbers)))

        # Retrieve submissions - optimize by fetching only assigned papers if possible
        if use_specific_assignment and assigned_paper_numbers:
            # Optimization: fetch only the papers we know are assigned
            logging.info("Retrieving only assigned submissions (optimized)")
            submissions = []
            for paper_num in sorted(assigned_paper_numbers):
                try:
                    paper_notes = self.openreview_client.get_notes(
                        invitation=f'{self.conference_id}/-/Submission',
                        details='replicated',
                        number=paper_num
                    )
                    if paper_notes:
                        submissions.extend(paper_notes)
                        logging.debug("Retrieved paper %d", paper_num)
                except Exception as e:
                    logging.warning("Failed to retrieve paper %d: %s", paper_num, e)
            logging.info("Retrieved %d assigned submissions", len(submissions))
        else:
            # Fallback: retrieve all submissions (needed for legacy method)
            logging.info("Retrieving all submissions (legacy method)")
            all_submissions = []
            offset = 0
            batch_size = 1000
            
            while True:
                submissions_batch = self.openreview_client.get_notes(
                    invitation=f'{self.conference_id}/-/Submission',
                    details='replicated',
                    limit=batch_size,
                    offset=offset
                )
                if not submissions_batch:
                    break
                all_submissions.extend(submissions_batch)
                logging.info("Retrieved %d submissions (total: %d)", len(submissions_batch), len(all_submissions))
                offset += batch_size
                
                # Stop if we got less than a full batch (means we're at the end)
                if len(submissions_batch) < batch_size:
                    break
            
            submissions = all_submissions
            logging.info("Found %d total submissions", len(submissions))

        paper_data = []
        logging.info("Processing papers assigned to AC")
        papers_checked = 0
        papers_matched = 0
        
        for paper in submissions:
            papers_checked += 1
            
            # Check assignment using the appropriate method
            is_assigned = False
            
            if use_specific_assignment:
                # Method 1: Check if paper number is in pre-filtered list (ICLR style)
                is_assigned = paper.number in assigned_paper_numbers
            else:
                # Method 2: Legacy method - check paper.readers (NeurIPS/ICCV style)
                ac_group_id_for_paper = f'{self.conference_id}/Submission{paper.number}/Area_Chairs'
                if ac_group_id_for_paper in paper.readers:
                    # Also check if you're actually in one of the AC groups for this paper
                    if any(ac_group in paper.readers for ac_group in pool_ac_groups):
                        is_assigned = True
            
            if not is_assigned:
                logging.debug("Paper %d is not assigned to you as AC.", paper.number)
                continue
            
            papers_matched += 1
            logging.info("Processing assigned paper %d", paper.number)

            logging.debug("Processing paper %d", paper.number)
            all_notes = self.openreview_client.get_notes(forum=paper.forum)
            invitation_str = f'{self.conference_id}/Submission{paper.number}/-/Official_Review'
            reviews = [note for note in all_notes if invitation_str in note.invitations]
            scores = (
                [CONFERENCE_INFO['RATING_EXTRACTOR'](review) for review in reviews]
                if 'RATING_EXTRACTOR' in CONFERENCE_INFO
                else []
            )

            # Extract final scores if FINAL_RATING_EXTRACTOR is available
            final_scores = []
            if 'FINAL_RATING_EXTRACTOR' in CONFERENCE_INFO:
                final_scores = [
                    CONFERENCE_INFO['FINAL_RATING_EXTRACTOR'](review) for review in reviews
                ]
                # Filter out None values for average calculation
                final_scores_filtered = [score for score in final_scores if score is not None]
            else:
                final_scores_filtered = []

            forum_notes = self.openreview_client.get_notes(forum=paper.forum)
            participating_reviewers = [
                note.signatures[0] for note in forum_notes if 'comment' in note.content
            ]

            note_counts = {
                note_key + '_count': 0 for note_key in CONFERENCE_INFO['NOTE_EXTRACTORS']
            }
            for note in forum_notes:
                for key, note_extractor in CONFERENCE_INFO['NOTE_EXTRACTORS'].items():
                    if note_extractor(note):
                        note_counts[key + '_count'] += 1

            note_counts['others_count'] = len(forum_notes) - sum(note_counts.values())

            paper_url = f"https://openreview.net/forum?id={paper.forum}"

            paper_data.append({
                'paper_title': paper.content['title']['value'],
                'withdrawn': 'Withdrawn' in paper.content.get('venue', {}).get('value', ''),
                'paper_number': CONFERENCE_INFO['PAPER_NUMBER_EXTRACTOR'](paper),
                'paper_url': paper_url,
                'num_reviewers': len(reviews),
                'avg_score': round(sum(scores) / len(scores), 2) if scores else 'N/A',
                'reviewer1_score': scores[0] if len(scores) >= 1 else '',
                'reviewer2_score': scores[1] if len(scores) >= 2 else '',
                'reviewer3_score': scores[2] if len(scores) >= 3 else '',
                'reviewer4_score': scores[3] if len(scores) >= 4 else '',
                'reviewer5_score': scores[4] if len(scores) >= 5 else '',
                'avg_final_score': (
                    round(sum(final_scores_filtered) / len(final_scores_filtered), 2)
                    if final_scores_filtered
                    else 'N/A'
                ),
                'reviewer1_final_score': final_scores[0] if len(final_scores) >= 1 else '',
                'reviewer2_final_score': final_scores[1] if len(final_scores) >= 2 else '',
                'reviewer3_final_score': final_scores[2] if len(final_scores) >= 3 else '',
                'reviewer4_final_score': final_scores[3] if len(final_scores) >= 4 else '',
                'reviewer5_final_score': final_scores[4] if len(final_scores) >= 5 else '',
                **note_counts,
                'reviewer_participation': len(participating_reviewers),
            })
            logging.debug("Added paper %d to results", paper.number)

        logging.info("Retrieved data for %d papers assigned to AC", len(paper_data))
        logging.info("Papers checked: %d, Papers matched: %d", papers_checked, papers_matched)
        return paper_data


def main():
    """
    Main function to orchestrate the Area Chair workflow automation.
    This includes:
    - Retrieving the list of papers assigned to the Area Chair
    - Writing the results to a Google Sheet
    """
    openreview_papers = OpenReviewACPapers(
        conference_id=CONFERENCE_INFO['CONFERENCE_ID'],
    )
    ac_papers_list = openreview_papers.get_ac_papers_list()

    gsheet_write = GSheetWithHeader(key_file=GSHEET_JSON,
                                    doc_name=GSHEET_TITLE,
                                    sheet_name=GSHEET_SHEET)
    gsheet_write.write_rows(rows=ac_papers_list,
                            empty_sheet=INITIALIZE_SHEET,
                            headers=ac_papers_list[0].keys() if ac_papers_list else [],
                            index_col=None if INITIALIZE_SHEET else 'paper_number',
                            write_headers=True,
                            overwrite_headers=INITIALIZE_SHEET,
                            start_row_idx=0,
                            batch_size=1000)


if __name__ == "__main__":
    main()
