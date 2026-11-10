"""Change the site's identity here. GitHub Pages workflow sets SITE_URL automatically."""
import os

SITE_TITLE = "Kuriosity Kronicles"  # working title; change whenever you like
TAGLINE = "Across Space, Time, and the Internet."
SITE_URL = os.environ.get("SITE_URL", "https://YOUR-SITE.example/").rstrip("/") + "/"
FEED_URL = SITE_URL + "feed.xml"
DESCRIPTION = "Stories about space, code, and the wonderfully unexpected, selected with AI."
