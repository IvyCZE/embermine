"""UI targets of the app. Resource ids and content descriptions come first because visible English
strings get renamed ("Firefox" -> "Embermine"); text is the fallback for Compose screens without either."""
from __future__ import annotations

from scripts.emulator.uidump import Selector

# Compose toolbar test tags (BrowserToolbarTestTags), stable across string renames.
HOMEPAGE_VIEW = Selector(id="homepage.view")
ADDRESS_BAR = Selector(id="ADDRESSBAR_URL_BOX")
HOMEPAGE_BAR = Selector(id="ADDRESSBAR_URL_BOX", desc=r"Search")
ADDRESS_BAR_URL = Selector(id="ADDRESSBAR_URL")
MENU_BUTTON = Selector(desc=r"More options")
TAB_COUNTER = Selector(id="ADDRESSBAR_TABS_COUNTER")
TAB_COUNTER_DESC = Selector(id="TabCounterTestTags.tabCounter")
PRIVATE_BUTTON = Selector(id="private.browsing.homepage.button")
SITE_INFO = Selector(desc=r"Site information")
SEARCH_ENGINE_SELECTOR = Selector(desc=r".*search engine selector.*")
SEARCH_ENGINE_MENU_TITLE = Selector(label=r"This time,? search in:?")
SEARCH_EXTRAS = Selector(label=r".*(Voice search|Search with image|Google Lens|Scan|QR).*")

# Onboarding screens, in the order buttons are preferred. Skipping and declining beat accepting so that
# the walk never changes a setting; "Continue" and "Confirm" are the only way forward on some pages.
ONBOARDING_BUTTONS = (
    Selector(text=r"Not now|Skip|Maybe later|No thanks|Don.t allow"),
    Selector(text=r"Continue browsing|Start browsing|Agree and start browsing|Agree and continue"),
    Selector(text=r"Continue|Confirm|Done|Get started"),
)

MENU_SETTINGS = Selector(label=r"Settings")
MENU_HISTORY = Selector(label=r"History")
SETTINGS_TITLE = Selector(label=r"Settings")

CLOSE_BUTTON = Selector(desc=r"Close|Navigate up|Back")
