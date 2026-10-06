"""OpsPilot demo UI: ``uv run python -m streamlit run src/web/app.py`` from the repo root.

Two pages (Phase 9):
- **Chat** (customers, decision D6): conversational replies only.
- **Operation Admin** (operations, decision D8): full case reports and refund approvals.

Both are thin adapters over ``src.agents.service``.
"""

import streamlit as st

from src.config.settings import get_settings
from src.utils.logging import configure_logging
from src.web.components import graph


def main() -> None:
    configure_logging(get_settings().log_level)
    st.set_page_config(page_title="OpsPilot", page_icon="🛠️", layout="wide")
    graph()
    navigation = st.navigation(
        [
            st.Page("views/chat.py", title="Chat", icon="💬", default=True),
            st.Page("views/admin.py", title="Operation Admin", icon="🛡️"),
        ]
    )
    navigation.run()


main()
