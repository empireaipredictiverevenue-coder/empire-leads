"""Lead source backends."""
from .overpass import discover as overpass_discover
from .reddit import discover as reddit_discover
from .nws import discover as nws_discover
from .google_places import discover as google_discover

SOURCE_DESCRIPTIONS = {
    "overpass": "OpenStreetMap/Overpass — free, unlimited business listings",
    "reddit": "Reddit no-API — buying-intent signals from niche subreddits",
    "nws": "NWS storm alerts — severe weather as lead triggers",
    "google_places": "Google Places API — enrichment (requires GOOGLE_MAPS_API_KEY)",
}
