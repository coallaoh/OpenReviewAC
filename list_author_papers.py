"""
List all papers for a given user as author for a conference.

This script queries OpenReview to find all submissions where a specified user
is listed as an author for the configured conference.

Usage:
    python list_author_papers.py <author_email_or_id> [conference_name]

Arguments:
    author_email_or_id: Email address or OpenReview profile ID of the author
    conference_name: Optional conference name (defaults to CONFERENCE_NAME in config.py)
                     Options: "ICLR2026", "NeurIPS2025", "ICCV2025", "ICML2025"

Examples:
    python list_author_papers.py author@example.com
    python list_author_papers.py ~Author_Name1 ICLR2026
    python list_author_papers.py author@example.com NeurIPS2025

Environment Variables:
    OPENREVIEW_USERNAME: Your OpenReview account email
    OPENREVIEW_PASSWORD: Your OpenReview account password
"""
import logging
import sys
import argparse
from utils.openreview import OpenReviewPapers
from utils.gsheet import GSheetWithHeader
from config import (
    CONFERENCE_NAME,
    GSHEET_CREDENTIALS_PATH,
    GSHEET_AUTHOR_TITLE_TEMPLATE,
    GSHEET_AUTHOR_SHEET,
    INITIALIZE_SHEET,
    GSHEET_BATCH_SIZE
)

# Import the full conference dictionary before selection
ALL_CONFERENCE_INFO = {
    "ICML2025": dict(
        CONFERENCE_ID='ICML.cc/2025/Conference',
        PAPER_NUMBER_EXTRACTOR=lambda paper: paper.number,
        RATING_EXTRACTOR=lambda review: review.content["overall_recommendation"]['value'],
        NOTE_EXTRACTORS={},  # ICML uses NOTE_KEYS instead, which is a different structure
    ),
    "ICCV2025": dict(
        CONFERENCE_ID='thecvf.com/ICCV/2025/Conference',
        PAPER_NUMBER_EXTRACTOR=lambda paper: paper.number,
        FINAL_RATING_EXTRACTOR=lambda review: (
            int(review.content["final_recommendation"]['value'].split(":")[0])
            if "final_recommendation" in review.content
            and "value" in review.content["final_recommendation"]
            else None
        ),
        NOTE_EXTRACTORS={
            'review': lambda note: 'preliminary_recommendation' in note.content,
            'comment': lambda note: 'comment' in note.content,
            'rebuttal': lambda note: ('pdf' in note.content and 'abstract' not in note.content),
            'ac_letter': lambda note: (
                'pdf' in note.content
                and 'abstract' not in note.content
                and 'value' in note.content.get('confidential_comments_to_AC', {})
            ),
        },
    ),
    "NeurIPS2025": dict(
        CONFERENCE_ID='NeurIPS.cc/2025/Conference',
        PAPER_NUMBER_EXTRACTOR=lambda paper: paper.number,
        RATING_EXTRACTOR=lambda review: (
            int(review.content["rating"]['value'])
            if "rating" in review.content and "value" in review.content["rating"]
            else None
        ),
        NOTE_EXTRACTORS={
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
                any(invitation.endswith('Official_Comment') for invitation in note.invitations)
                and any(writer for writer in note.writers if writer.split('/')[-1].startswith('Reviewer'))
                and any(reader for reader in note.readers if reader.split('/')[-1].startswith('Author'))
            ),
            'rebuttal': lambda note: any(invitation.endswith('Rebuttal') for invitation in note.invitations),
            'rebuttal_acknowledgement': lambda note: (
                any(invitation.endswith('Mandatory_Acknowledgement') for invitation in note.invitations)
            ),
            'ac_letter_author': lambda note: (
                any(invitation.endswith('Author_AC_Confidential_Comment') for invitation in note.invitations)
                and any(writer for writer in note.writers if writer.split('/')[-1].startswith('Author'))
            ),
            'ac_letter_ac': lambda note: (
                any(invitation.endswith('Author_AC_Confidential_Comment') for invitation in note.invitations)
                and any(writer for writer in note.writers if writer.split('/')[-1].startswith('Area_Chair'))
            ),
        },
    ),
    "ICLR2026": dict(
        CONFERENCE_ID='ICLR.cc/2026/Conference',
        PAPER_NUMBER_EXTRACTOR=lambda paper: paper.number,
        RATING_EXTRACTOR=lambda review: (
            int(review.content["rating"]['value'])
            if "rating" in review.content and "value" in review.content["rating"]
            else None
        ),
        NOTE_EXTRACTORS={
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
                    any(writer for writer in note.writers if writer.split('/')[-1].startswith('Reviewer'))
                    and any(reader for reader in note.readers if reader.split('/')[-1].startswith('Author'))
                )
            ),
            'discussion_comment': lambda note: (
                any(invitation.endswith('Official_Comment') for invitation in note.invitations)
                and any(writer for writer in note.writers if writer.split('/')[-1].startswith('Reviewer'))
                and any(reader for reader in note.readers if reader.split('/')[-1].startswith('Author'))
            ),
            'rebuttal': lambda note: any(invitation.endswith('Rebuttal') for invitation in note.invitations),
            'rebuttal_acknowledgement': lambda note: (
                any(invitation.endswith('Mandatory_Acknowledgement') for invitation in note.invitations)
            ),
            'ac_letter_author': lambda note: (
                any(invitation.endswith('Author_AC_Confidential_Comment') for invitation in note.invitations)
                and any(writer for writer in note.writers if writer.split('/')[-1].startswith('Author'))
            ),
            'ac_letter_ac': lambda note: (
                any(invitation.endswith('Author_AC_Confidential_Comment') for invitation in note.invitations)
                and any(writer for writer in note.writers if writer.split('/')[-1].startswith('Area_Chair'))
            ),
        },
    ),
}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class OpenReviewAuthorPapers(OpenReviewPapers):
    """
    OpenReviewAuthorPapers handles operations for finding papers by author.
    """
    
    def __init__(self, conference_id, paper_number_extractor, rating_extractor=None, final_rating_extractor=None, note_extractors=None):
        """
        Initialize with conference ID and paper number extractor.
        
        Args:
            conference_id: The OpenReview conference identifier string
            paper_number_extractor: Function to extract paper number from paper object
            rating_extractor: Optional function to extract initial review ratings
            final_rating_extractor: Optional function to extract final review ratings
            note_extractors: Optional dictionary of note type extractors
        """
        super().__init__(conference_id)
        self.paper_number_extractor = paper_number_extractor
        self.rating_extractor = rating_extractor
        self.final_rating_extractor = final_rating_extractor
        self.note_extractors = note_extractors or {}
    
    def get_author_papers_list(self, author_identifier):
        """
        Retrieve all papers where the specified user is an author.

        Args:
            author_identifier: Email address or OpenReview profile ID (e.g., ~Author_Name1)

        Returns:
            List[dict]: List of dictionaries, one per paper, containing:
                - paper_title: Title of the submission
                - paper_number: OpenReview paper number
                - paper_url: Direct link to paper on OpenReview
                - withdrawn: Boolean indicating if paper is withdrawn
                - authors: List of author names
                - authorids: List of author OpenReview IDs
                - venue: Current venue status
                - num_reviewers: Number of assigned reviewers
                - avg_score: Average initial review score
                - reviewer1_score through reviewer5_score: Individual reviewer initial scores
                - avg_final_score: Average final review score (if available)
                - reviewer1_final_score through reviewer5_final_score: Individual reviewer final scores
                - *_count: Counts of various note types (reviews, rebuttals, comments, etc.)
                - reviewer_participation: Number of participating reviewers
        """
        logging.info("Starting to retrieve papers for author: %s", author_identifier)
        
        # First, try to resolve the author identifier to a profile
        # This handles both email addresses and profile IDs
        try:
            profile = self.openreview_client.get_profile(author_identifier)
            if profile:
                author_id = profile.id
                logging.info("Resolved author identifier to profile ID: %s", author_id)
            else:
                # If profile lookup fails, use the identifier as-is
                author_id = author_identifier
                logging.info("Using provided identifier as author ID: %s", author_id)
        except Exception as e:
            logging.warning("Could not resolve profile for %s: %s. Using as-is.", author_identifier, e)
            author_id = author_identifier
        
        # Retrieve all submissions for the conference
        logging.info("Retrieving all submissions for %s", self.conference_id)
        all_submissions = []
        offset = 0
        batch_size = 1000

        while True:
            try:
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
            except Exception as e:
                logging.error("Error retrieving submissions batch at offset %d: %s", offset, e)
                break

        logging.info("Found %d total submissions", len(all_submissions))

        # Filter papers where the user is an author
        paper_data = []
        logging.info("Filtering papers for author: %s", author_id)
        papers_checked = 0
        papers_matched = 0

        for paper in all_submissions:
            papers_checked += 1
            
            # Check if the author is in the author list
            # OpenReview stores authors in different formats:
            # - authorids: List of OpenReview profile IDs (e.g., ~Author_Name1)
            # - authors: List of author names/emails
            
            is_author = False
            authorids = paper.content.get('authorids', {}).get('value', [])
            authors = paper.content.get('authors', {}).get('value', [])
            
            # Check if author_id matches any authorid
            if authorids:
                # Normalize author_id for comparison (remove ~ if present, compare both ways)
                normalized_author_id = author_id.lstrip('~')
                for aid in authorids:
                    normalized_aid = aid.lstrip('~')
                    if author_id == aid or normalized_author_id == normalized_aid:
                        is_author = True
                        break
            
            # Also check authors list (in case it contains emails or IDs)
            if not is_author and authors:
                for author in authors:
                    if author_id.lower() == author.lower() or author_id in author:
                        is_author = True
                        break
            
            if not is_author:
                logging.debug("Paper %d: Author not found", paper.number)
                continue

            papers_matched += 1
            logging.info("Found paper %d: %s", paper.number, paper.content.get('title', {}).get('value', 'N/A'))

            # Retrieve all notes for the forum (reviews and other notes)
            forum_notes = self.openreview_client.get_notes(forum=paper.forum)
            invitation_str = f'{self.conference_id}/Submission{paper.number}/-/Official_Review'
            reviews = [note for note in forum_notes if invitation_str in note.invitations]
            
            # Extract initial scores
            scores = []
            if self.rating_extractor:
                scores = [self.rating_extractor(review) for review in reviews]
                # Filter out None values
                scores = [score for score in scores if score is not None]
            
            # Extract final scores if available
            final_scores = []
            final_scores_filtered = []
            if self.final_rating_extractor:
                final_scores = [self.final_rating_extractor(review) for review in reviews]
                # Filter out None values for average calculation
                final_scores_filtered = [score for score in final_scores if score is not None]

            # Count note types and reviewer participation
            participating_reviewers = [
                note.signatures[0] for note in forum_notes if 'comment' in note.content
            ]

            note_counts = {
                note_key + '_count': 0 for note_key in self.note_extractors
            }
            for note in forum_notes:
                for key, note_extractor in self.note_extractors.items():
                    if note_extractor(note):
                        note_counts[key + '_count'] += 1

            note_counts['others_count'] = len(forum_notes) - sum(note_counts.values())

            paper_url = f"https://openreview.net/forum?id={paper.forum}"
            venue = paper.content.get('venue', {}).get('value', '')
            
            paper_data.append({
                'paper_title': paper.content.get('title', {}).get('value', 'N/A'),
                'paper_number': self.paper_number_extractor(paper),
                'paper_url': paper_url,
                'withdrawn': 'Withdrawn' in venue,
                'venue': venue,
                'authors': ', '.join(authors) if authors else 'N/A',
                'authorids': ', '.join(authorids) if authorids else 'N/A',
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
                'reviewer1_final_score': final_scores[0] if len(final_scores) >= 1 and final_scores[0] is not None else '',
                'reviewer2_final_score': final_scores[1] if len(final_scores) >= 2 and final_scores[1] is not None else '',
                'reviewer3_final_score': final_scores[2] if len(final_scores) >= 3 and final_scores[2] is not None else '',
                'reviewer4_final_score': final_scores[3] if len(final_scores) >= 4 and final_scores[3] is not None else '',
                'reviewer5_final_score': final_scores[4] if len(final_scores) >= 5 and final_scores[4] is not None else '',
                **note_counts,
                'reviewer_participation': len(participating_reviewers),
            })
            logging.debug("Added paper %d to results", paper.number)

        logging.info("Retrieved data for %d papers authored by %s", len(paper_data), author_id)
        logging.info("Papers checked: %d, Papers matched: %d", papers_checked, papers_matched)
        return paper_data


def print_papers(paper_data):
    """
    Print papers in a formatted table.
    
    Args:
        paper_data: List of paper dictionaries
    """
    if not paper_data:
        print("\nNo papers found for this author.")
        return
    
    print(f"\n{'='*80}")
    print(f"Found {len(paper_data)} paper(s)")
    print(f"{'='*80}\n")
    
    for idx, paper in enumerate(paper_data, 1):
        print(f"Paper #{idx}")
        print(f"  Title: {paper['paper_title']}")
        print(f"  Number: {paper['paper_number']}")
        print(f"  URL: {paper['paper_url']}")
        print(f"  Status: {'Withdrawn' if paper['withdrawn'] else paper['venue']}")
        print(f"  Authors: {paper['authors']}")
        print(f"  Author IDs: {paper['authorids']}")
        print()


def main():
    """
    Main function to list papers for a given author.
    """
    parser = argparse.ArgumentParser(
        description='List all papers for a given user as author for a conference',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python list_author_papers.py author@example.com
  python list_author_papers.py ~Author_Name1 ICLR2026
  python list_author_papers.py author@example.com NeurIPS2025
        """
    )
    parser.add_argument(
        'author',
        help='Email address or OpenReview profile ID of the author (e.g., author@example.com or ~Author_Name1)'
    )
    parser.add_argument(
        'conference',
        nargs='?',
        default=CONFERENCE_NAME,
        choices=['ICLR2026', 'NeurIPS2025', 'ICCV2025', 'ICML2025'],
        help=f'Conference name (default: {CONFERENCE_NAME})'
    )
    
    args = parser.parse_args()
    
    # Get conference info
    if args.conference not in ALL_CONFERENCE_INFO:
        logging.error("Unsupported conference: %s", args.conference)
        sys.exit(1)
    
    conference_info = ALL_CONFERENCE_INFO[args.conference]
    
    # Create OpenReview client and get papers
    try:
        author_papers = OpenReviewAuthorPapers(
            conference_id=conference_info['CONFERENCE_ID'],
            paper_number_extractor=conference_info['PAPER_NUMBER_EXTRACTOR'],
            rating_extractor=conference_info.get('RATING_EXTRACTOR'),
            final_rating_extractor=conference_info.get('FINAL_RATING_EXTRACTOR'),
            note_extractors=conference_info.get('NOTE_EXTRACTORS', {}),
        )
        papers_list = author_papers.get_author_papers_list(args.author)
        
        # Print results
        print_papers(papers_list)
        
        # Write to Google Sheet
        if papers_list:
            gsheet_title = GSHEET_AUTHOR_TITLE_TEMPLATE.format(conference=args.conference)
            gsheet_sheet = GSHEET_AUTHOR_SHEET
            
            logging.info("Writing %d papers to Google Sheet: %s", len(papers_list), gsheet_title)
            gsheet_write = GSheetWithHeader(
                key_file=GSHEET_CREDENTIALS_PATH,
                doc_name=gsheet_title,
                sheet_name=gsheet_sheet
            )
            gsheet_write.write_rows(
                rows=papers_list,
                empty_sheet=INITIALIZE_SHEET,
                headers=list(papers_list[0].keys()) if papers_list else [],
                write_headers=True,
                overwrite_headers=INITIALIZE_SHEET,
                start_row_idx=0,
                batch_size=GSHEET_BATCH_SIZE
            )
            logging.info("Successfully wrote papers to Google Sheet")
        else:
            logging.info("No papers found, skipping Google Sheet write")
        
    except Exception as e:
        logging.error("Error retrieving papers: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

