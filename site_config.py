"""Change the site's identity here. GitHub Pages workflow sets SITE_URL automatically."""
import os

SITE_TITLE = "Curiosity Dispatch"   # working title; change whenever you like
TAGLINE = "Astronomy, code, and curious detours."
SITE_URL = os.environ.get("SITE_URL", "https://YOUR-SITE.example/").rstrip("/") + "/"
FEED_URL = SITE_URL + "feed.xml"
DESCRIPTION = "Stories about space, code, and the wonderfully unexpected, selected with AI."
