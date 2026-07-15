"""Lead source backends."""
from .overpass import discover as overpass_discover
from .reddit import discover as reddit_discover
from .nws import discover as nws_discover
from .google_places import discover as google_discover
from .carrier_rosters import discover as carrier_discover
from .state_licenses import discover as state_license_discover

SOURCE_DESCRIPTIONS = {
    "overpass": "OpenStreetMap/Overpass — free, unlimited business listings",
    "reddit": "Reddit no-API — buying-intent signals from niche subreddits",
    "nws": "NWS storm alerts — severe weather as lead triggers",
    "google_places": "Google Places API — enrichment (requires GOOGLE_MAPS_API_KEY)",
    "carrier_rosters": "Insurance carrier DRP rosters — approved contractor directories",
    "state_licenses": "State contractor license databases — verified records (TX/GA/OH scrapable)",
}
