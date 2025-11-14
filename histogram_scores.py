"""
OpenReview Review Score Histogram Generator
===========================================

Crawls average review scores from OpenReview and generates a histogram visualization.

Usage:
    python histogram_scores.py [options]

Options:
    --scope {all,ac}          Scope of papers to analyze (default: all)
    --score-type {initial,final}  Type of scores to use (default: initial)
    --exclude-withdrawn       Exclude withdrawn papers from analysis
    --save PATH               Save histogram to file (PNG/PDF) instead of displaying
    --bins N                  Number of bins for histogram (default: auto)
    --no-cache                Disable caching and fetch fresh data
    --refresh-cache           Force refresh of cached data

Examples:
    # Show histogram of all papers' initial scores
    python histogram_scores.py

    # Show histogram of AC-assigned papers' final scores
    python histogram_scores.py --scope ac --score-type final

    # Save histogram excluding withdrawn papers
    python histogram_scores.py --exclude-withdrawn --save histogram.png

    # Force refresh of cached data
    python histogram_scores.py --refresh-cache
"""
import argparse
import hashlib
import logging
import pickle
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from tqdm import tqdm
from utils.openreview import OpenReviewPapers
from config import CONFERENCE_INFO, CONFERENCE_NAME, CACHE_ROOT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class ScoreHistogramGenerator(OpenReviewPapers):
    """
    Generates histograms of review scores from OpenReview papers.
    
    Can analyze all papers in a conference or only papers assigned to
    the authenticated user as an Area Chair.
    """
    
    def __init__(self, conference_id, use_cache=True, refresh_cache=False):
        """
        Initialize the histogram generator.
        
        Args:
            conference_id: OpenReview conference identifier
            use_cache: If True, use cached data when available
            refresh_cache: If True, force refresh of cached data
        """
        super().__init__(conference_id)
        self.use_cache = use_cache
        self.refresh_cache = refresh_cache
        self.cache_dir = Path(CACHE_ROOT) / "histogram_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_path(self, cache_key):
        """
        Get the cache file path for a given cache key.
        
        Args:
            cache_key: String identifier for the cache
            
        Returns:
            Path: Path to the cache file
        """
        # Create a hash of the cache key for filename
        cache_hash = hashlib.md5(cache_key.encode()).hexdigest()
        return self.cache_dir / f"{cache_hash}.pkl"
    
    def _load_cache(self, cache_key):
        """
        Load data from cache if available and caching is enabled.
        
        Args:
            cache_key: String identifier for the cache
            
        Returns:
            Cached data if available, None otherwise
        """
        if not self.use_cache or self.refresh_cache:
            return None
        
        cache_path = self._get_cache_path(cache_key)
        if cache_path.exists():
            try:
                logging.info("Loading data from cache: %s", cache_path)
                with open(cache_path, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                logging.warning("Failed to load cache: %s", e)
                return None
        return None
    
    def _save_cache(self, cache_key, data):
        """
        Save data to cache.
        
        Args:
            cache_key: String identifier for the cache
            data: Data to cache
        """
        if not self.use_cache:
            return
        
        cache_path = self._get_cache_path(cache_key)
        try:
            logging.info("Saving data to cache: %s", cache_path)
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            logging.warning("Failed to save cache: %s", e)
    
    def get_all_submissions(self):
        """
        Retrieve all submissions for the conference.
        Uses cache if available.
        
        Returns:
            List: All submission notes from OpenReview
        """
        cache_key = f"all_submissions_{self.conference_id}"
        
        # Try to load from cache
        cached_data = self._load_cache(cache_key)
        if cached_data is not None:
            logging.info("Loaded %d submissions from cache", len(cached_data))
            return cached_data
        
        # Fetch from OpenReview
        logging.info("Retrieving all submissions for %s", self.conference_id)
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
            logging.info("Retrieved %d submissions (total: %d)", 
                        len(submissions_batch), len(all_submissions))
            offset += batch_size

            # Stop if we got less than a full batch (means we're at the end)
            if len(submissions_batch) < batch_size:
                break

        logging.info("Found %d total submissions", len(all_submissions))
        
        # Save to cache
        self._save_cache(cache_key, all_submissions)
        
        return all_submissions
    
    def get_ac_assigned_submissions(self):
        """
        Retrieve submissions assigned to the authenticated user as Area Chair.
        Uses cache if available.
        
        Returns:
            List: Submission notes assigned to the user as AC
        """
        profile = self.openreview_client.get_profile()
        cache_key = f"ac_submissions_{self.conference_id}_{profile.id}"
        
        # Try to load from cache
        cached_data = self._load_cache(cache_key)
        if cached_data is not None:
            logging.info("Loaded %d AC-assigned submissions from cache", len(cached_data))
            return cached_data
        
        logging.info("Retrieving AC-assigned submissions")
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
        ac_groups = [g.id for g in user_groups if 'Area_Chair' in g.id]
        logging.info("Found %d AC groups for user", len(ac_groups))

        # Extract paper numbers from AC groups
        assigned_paper_numbers = set()
        specific_ac_groups = []
        pool_ac_groups = []

        for ac_group in ac_groups:
            # Method 1: Specific assignments (Area_Chair_{code}) - used by ICLR
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
            # Method 2: Pool groups (Area_Chairs) - used by others
            elif (self.conference_id in ac_group and
                  '/Submission' in ac_group and
                  ac_group.endswith('/Area_Chairs')):
                pool_ac_groups.append(ac_group)

        use_specific_assignment = len(specific_ac_groups) > 0

        if use_specific_assignment:
            logging.info("Found %d specific AC assignment groups", 
                        len(specific_ac_groups))
            # Fetch only assigned papers
            submissions = []
            sorted_paper_nums = sorted(assigned_paper_numbers)
            for paper_num in tqdm(sorted_paper_nums, desc="Fetching AC-assigned papers"):
                try:
                    paper_notes = self.openreview_client.get_notes(
                        invitation=f'{self.conference_id}/-/Submission',
                        details='replicated',
                        number=paper_num
                    )
                    if paper_notes:
                        submissions.extend(paper_notes)
                except (ValueError, KeyError, AttributeError) as e:
                    logging.warning("Failed to retrieve paper %d: %s", paper_num, e)
            logging.info("Retrieved %d assigned submissions", len(submissions))
        else:
            # Fallback: retrieve all and filter by paper.readers
            logging.info("Using paper.readers method (legacy)")
            all_submissions = self.get_all_submissions()
            submissions = []
            for paper in tqdm(all_submissions, desc="Filtering AC-assigned papers"):
                ac_group_id_for_paper = f'{self.conference_id}/Submission{paper.number}/Area_Chairs'
                if ac_group_id_for_paper in paper.readers:
                    if any(ac_group in paper.readers for ac_group in pool_ac_groups):
                        submissions.append(paper)
            logging.info("Found %d AC-assigned submissions", len(submissions))

        # Save to cache
        self._save_cache(cache_key, submissions)
        
        return submissions
    
    def extract_average_scores(self, submissions, score_type='initial', 
                               exclude_withdrawn=False):
        """
        Extract average review scores from submissions.
        Uses cache if available.
        
        Args:
            submissions: List of submission notes
            score_type: 'initial' or 'final' to specify which scores to use
            exclude_withdrawn: If True, exclude withdrawn papers
            
        Returns:
            List[float]: List of average scores (one per paper)
        """
        # Create cache key based on parameters
        # Include paper numbers to detect if submissions changed
        paper_numbers = tuple(sorted([s.number for s in submissions]))
        cache_key = f"scores_{self.conference_id}_{score_type}_{exclude_withdrawn}_{hash(paper_numbers)}"
        
        # Try to load from cache
        cached_data = self._load_cache(cache_key)
        if cached_data is not None:
            logging.info("Loaded %d scores from cache", len(cached_data))
            return cached_data
        
        logging.info("Extracting %s scores from %d submissions", 
                    score_type, len(submissions))
        
        avg_scores = []
        papers_processed = 0
        papers_with_scores = 0
        
        for paper in tqdm(submissions, desc=f"Extracting {score_type} scores"):
            papers_processed += 1
            
            # Check if withdrawn
            if exclude_withdrawn:
                if 'Withdrawn' in paper.content.get('venue', {}).get('value', ''):
                    logging.debug("Skipping withdrawn paper %d", paper.number)
                    continue
            
            # Get reviews for this paper
            all_notes = self.openreview_client.get_notes(forum=paper.forum)
            invitation_str = f'{self.conference_id}/Submission{paper.number}/-/Official_Review'
            reviews = [note for note in all_notes if invitation_str in note.invitations]
            
            if not reviews:
                logging.debug("Paper %d has no reviews", paper.number)
                continue
            
            # Extract scores based on type
            if score_type == 'initial':
                if 'RATING_EXTRACTOR' not in CONFERENCE_INFO:
                    logging.warning("RATING_EXTRACTOR not defined for %s", 
                                  CONFERENCE_NAME)
                    continue
                scores = [
                    CONFERENCE_INFO['RATING_EXTRACTOR'](review) 
                    for review in reviews
                ]
                # Filter out None values
                scores = [s for s in scores if s is not None]
            elif score_type == 'final':
                if 'FINAL_RATING_EXTRACTOR' not in CONFERENCE_INFO:
                    logging.warning("FINAL_RATING_EXTRACTOR not defined for %s", 
                                  CONFERENCE_NAME)
                    continue
                scores = [
                    CONFERENCE_INFO['FINAL_RATING_EXTRACTOR'](review) 
                    for review in reviews
                ]
                # Filter out None values
                scores = [s for s in scores if s is not None]
            else:
                raise ValueError(f"Invalid score_type: {score_type}")
            
            if not scores:
                logging.debug("Paper %d has no valid scores", paper.number)
                continue
            
            # Compute average score
            avg_score = sum(scores) / len(scores)
            avg_scores.append(avg_score)
            papers_with_scores += 1
        
        logging.info("Extracted scores from %d papers (out of %d processed)", 
                    papers_with_scores, papers_processed)
        
        # Save to cache
        self._save_cache(cache_key, avg_scores)
        
        return avg_scores
    
    def generate_histogram(self, scores, score_type='initial', bins=None, 
                          save_path=None):
        """
        Generate and display/save histogram of scores.
        
        Args:
            scores: List of average scores
            score_type: 'initial' or 'final' (for labeling)
            bins: Number of bins (None for auto)
            save_path: Path to save file (None to display)
        """
        if not scores:
            logging.error("No scores to plot")
            return
        
        scores_array = np.array(scores)
        
        # Calculate statistics
        mean_score = np.mean(scores_array)
        median_score = np.median(scores_array)
        std_score = np.std(scores_array)
        min_score = np.min(scores_array)
        max_score = np.max(scores_array)
        
        # Print statistics
        print("\n" + "="*60)
        print(f"Review Score Statistics ({score_type.upper()} scores)")
        print("="*60)
        print(f"Total papers: {len(scores)}")
        print(f"Mean score: {mean_score:.2f}")
        print(f"Median score: {median_score:.2f}")
        print(f"Std deviation: {std_score:.2f}")
        print(f"Min score: {min_score:.2f}")
        print(f"Max score: {max_score:.2f}")
        print("="*60 + "\n")
        
        # Create histogram
        _, ax = plt.subplots(figsize=(10, 6))
        
        # Determine bins if not specified
        if bins is None:
            # Use 0.5-width bins for typical 1-5 scale, or auto if range is different
            if max_score - min_score <= 5:
                bins = np.arange(min_score - 0.25, max_score + 0.5, 0.5)
            else:
                bins = 'auto'
        
        ax.hist(scores_array, bins=bins, edgecolor='black', 
                alpha=0.7, color='steelblue')
        
        # Add vertical lines for mean and median
        ax.axvline(mean_score, color='red', linestyle='--', linewidth=2, 
                  label=f'Mean: {mean_score:.2f}')
        ax.axvline(median_score, color='green', linestyle='--', linewidth=2, 
                  label=f'Median: {median_score:.2f}')
        
        # Labels and title
        ax.set_xlabel('Average Review Score', fontsize=12)
        ax.set_ylabel('Number of Papers', fontsize=12)
        ax.set_title(f'Distribution of {score_type.capitalize()} Review Scores - {CONFERENCE_NAME}', 
                    fontsize=14, fontweight='bold')
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)
        
        # Add statistics text box
        stats_text = f'N = {len(scores)}\nμ = {mean_score:.2f}\nσ = {std_score:.2f}'
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, 
               fontsize=10, verticalalignment='top',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        plt.tight_layout()
        
        # Save or display
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            logging.info("Histogram saved to %s", save_path)
        else:
            plt.show()
        
        plt.close()


def main():
    """Main function to generate histogram."""
    parser = argparse.ArgumentParser(
        description='Generate histogram of OpenReview review scores',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--scope', 
        choices=['all', 'ac'], 
        default='all',
        help='Scope of papers to analyze: all papers or AC-assigned only (default: all)'
    )
    parser.add_argument(
        '--score-type',
        choices=['initial', 'final'],
        default='initial',
        help='Type of scores to use: initial or final (default: initial)'
    )
    parser.add_argument(
        '--exclude-withdrawn',
        action='store_true',
        help='Exclude withdrawn papers from analysis'
    )
    parser.add_argument(
        '--save',
        type=str,
        default=None,
        metavar='PATH',
        help='Save histogram to file (PNG/PDF) instead of displaying'
    )
    parser.add_argument(
        '--bins',
        type=int,
        default=None,
        metavar='N',
        help='Number of bins for histogram (default: auto)'
    )
    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Disable caching and fetch fresh data'
    )
    parser.add_argument(
        '--refresh-cache',
        action='store_true',
        help='Force refresh of cached data'
    )
    
    args = parser.parse_args()
    
    # Initialize generator
    use_cache = not args.no_cache
    generator = ScoreHistogramGenerator(
        conference_id=CONFERENCE_INFO['CONFERENCE_ID'],
        use_cache=use_cache,
        refresh_cache=args.refresh_cache
    )
    
    # Get submissions based on scope
    if args.scope == 'all':
        submissions = generator.get_all_submissions()
    else:  # args.scope == 'ac'
        submissions = generator.get_ac_assigned_submissions()
        if not submissions:
            logging.error("No AC-assigned papers found. Make sure you are logged in as an Area Chair.")
            return
    
    # Extract scores
    scores = generator.extract_average_scores(
        submissions=submissions,
        score_type=args.score_type,
        exclude_withdrawn=args.exclude_withdrawn
    )
    
    if not scores:
        logging.error("No scores found. Check your configuration and data.")
        return
    
    # Generate histogram
    generator.generate_histogram(
        scores=scores,
        score_type=args.score_type,
        bins=args.bins,
        save_path=args.save
    )


if __name__ == "__main__":
    main()

