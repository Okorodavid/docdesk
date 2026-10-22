from communityops.answer import Result

from docdesk.memory import ANSWERED_BY_DOCS, OPEN, RESOLVED_BY_AGENT
from docdesk.service import DocDesk, VOICE_SYSTEM_TEMPLATE

from .conftest import publish_mobile_money


async def test_answers_from_docs_with_section_source(desk):
    out = await desk.ask("ada", "How do I restart my router?")
    assert out.status == "answered"
    assert "unplug the power cable" in out.speech
    assert out.sources[0].url.endswith("/help/router-setup.md#restart-your-router")
    assert "Router setup" in out.sources[0].title


async def test_picks_the_sentence_that_answers(desk):
    out = await desk.ask("ada", "What does a solid orange light mean?")
    assert out.status == "answered"
    assert "no internet signal" in out.answer


async def test_unknown_question_opens_ticket(desk):
    out = await desk.ask("ada", "Can I pay with mobile money?")
    assert out.status == "ticket_opened"
    assert out.ticket.status == OPEN
    assert f"ticket {out.ticket.id}" in out.speech


async def test_account_specific_question_is_not_answered(desk):
    out = await desk.ask("tunde", "Why is my bill higher this month?")
    assert out.status == "ticket_opened"


async def test_similar_question_joins_existing_ticket(desk):
    first = await desk.ask("ada", "Can I pay with mobile money?")
    second = await desk.ask("ada", "Do you accept mobile money payments?")
    assert second.status == "added_to_ticket"
    assert second.ticket.id == first.ticket.id
    assert len(desk.memory.for_customer("ada")) == 1


async def test_tickets_are_private_to_each_customer(desk):
    await desk.ask("ada", "Can I pay with mobile money?")
    assert desk.my_tickets("tunde")["open"] == []
    assert len(desk.my_tickets("ada")["open"]) == 1
    t = desk.memory.for_customer("ada")[0]
    assert desk.add_details("tunde", t.id, "hijack")["ok"] is False
    assert desk.close_ticket("tunde", t.id)["ok"] is False


async def test_new_article_resolves_open_ticket_and_customer_hears_once(desk, settings):
    opened = await desk.ask("ada", "Can I pay with mobile money?")
    await desk.ask("tunde", "Why is my bill higher this month?")
    publish_mobile_money(desk, settings)
    resolved = await desk.recheck_open_tickets()
    assert [t.id for t in resolved] == [opened.ticket.id]
    assert desk.memory.get(opened.ticket.id).status == ANSWERED_BY_DOCS
    assert desk.memory.all_tickets(statuses=(OPEN,))[0].customer_id == "tunde"

    nxt = await desk.ask("ada", "Is there a late fee?")
    assert nxt.speech.startswith(f"Good news about ticket {opened.ticket.id}")
    assert "mobile money" in nxt.speech and "late fee" in nxt.speech
    assert nxt.updates[0].sources[0].url.endswith("/help/new/payment-methods.md#pay-with-mobile-money")

    again = await desk.ask("ada", "Is there a late fee?")
    assert again.updates == [] and not again.speech.startswith("Good news")


async def test_agent_reply_reaches_customer_via_my_tickets(desk):
    out = await desk.ask("tunde", "Why is my bill higher this month?")
    desk.agent_reply(out.ticket.id, "Your promo discount ended on 1 October.", "Brightline support")
    data = desk.my_tickets("tunde")
    assert data["open"] == []
    assert "support team replied" in data["speech"] and "promo discount" in data["speech"]
    assert desk.memory.get(out.ticket.id).status == RESOLVED_BY_AGENT


async def test_gaps_report_groups_unanswered_questions(desk):
    await desk.ask("ada", "Can I pay with mobile money?")
    await desk.ask("tunde", "Is mobile money accepted for bills?")
    await desk.ask("ada", "How do I restart my router?")
    report = desk.gaps_report(days=7)
    assert report["questions"] == 3 and report["answered"] == 1
    assert report["topics"][0]["count"] == 2
    assert "mobile" in report["topics"][0]["topic"]


async def test_claude_mode_uses_voice_prompt(settings):
    class FakeAnswerer:
        mode = "fake"

        async def answer(self, question):
            return Result(question, "answered", "Spoken answer.\n\nSources:\nhttp://x/help/a.md#b", ["http://x/help/a.md#b"])

    settings.answer_mode = "claude"
    desk = DocDesk(settings)
    assert desk.answerer.system_template == VOICE_SYSTEM_TEMPLATE
    assert "read aloud" in VOICE_SYSTEM_TEMPLATE
    desk.store.close()

    custom = DocDesk(settings, answerer=FakeAnswerer())
    out = await custom.ask("ada", "anything")
    assert out.speech == "Spoken answer."
    custom.store.close()
