from pathlib import Path

import pytest

from docdesk.config import ROOT, DocDeskSettings
from docdesk.server import index_docs
from docdesk.service import DocDesk


@pytest.fixture
def settings(tmp_path):
    return DocDeskSettings(
        db_path=tmp_path / "docdesk.db",
        articles_dir=tmp_path / "articles",
        answer_mode="offline",
        staff_token="test-staff-token",
        demo_docs_dir=ROOT / "demo" / "docs",
    )


@pytest.fixture
def desk(settings):
    d = DocDesk(settings)
    index_docs(d, settings)
    yield d
    d.store.close()


MOBILE_MONEY_ARTICLE = (
    "# Payment methods\n\n## Pay with mobile money\n\nYou can pay your Brightline bill with mobile money. "
    "Open the Brightline app, go to Billing, tap Pay now, and choose Mobile money.\n"
)


def publish_mobile_money(desk: DocDesk, settings) -> None:
    folder: Path = settings.articles_dir
    folder.mkdir(parents=True, exist_ok=True)
    desk.add_article(folder, f"{settings.base_url}/help/new", "Payment methods", MOBILE_MONEY_ARTICLE)
