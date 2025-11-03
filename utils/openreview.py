import openreview
import os


class OpenReviewPapers(object):
    def __init__(self, conference_id):
        self.openreview_client = openreview.api.OpenReviewClient(
            baseurl='https://api2.openreview.net',
            username=os.environ.get('OPENREVIEW_USERNAME'),
            password=os.environ.get('OPENREVIEW_PASSWORD'),
        )
        self.conference_id = conference_id
