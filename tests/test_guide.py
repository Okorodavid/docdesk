import pytest

from docdesk.config import ROOT
from docdesk.guide import build_guide, load_app_map

from .conftest import publish_mobile_money

APP = load_app_map(str(ROOT / "demo" / "app-map.json"))


def targets(guide):
    return [s["target"] for s in guide["steps"]]


def test_mobile_money_walkthrough_points_at_each_place_to_tap():
    g = build_guide("You can pay your Brightline bill with mobile money. Open the Brightline app, go to Billing, "
                    "tap Pay now, and choose Mobile money.", APP)
    assert targets(g) == ["app-brightline", "nav-billing", "bill-pay", "pay-mobile"]
    assert [s["say"] for s in g["steps"]] == ["Open the Brightline app.", "Go to Billing.", "Tap Pay now.", "Choose Mobile money."]
    assert [s["screen"] for s in g["steps"]] == ["launcher", "home", "billing", "pay"]
    assert g["intro"].startswith("You can pay your Brightline bill with mobile money.")
    assert set(g["screens"]) == {"launcher", "home", "billing", "pay"}


def test_steps_after_a_lead_in_and_app_opener_added():
    g = build_guide("To restart your Brightline router, unplug the power cable, wait 30 seconds, and plug it back in. "
                    "You can also restart it from the Brightline app: open Devices, choose your router, and tap Restart.", APP)
    assert targets(g) == ["app-brightline", "nav-devices", "device-router", "router-restart"]
    assert "unplug the power cable" in g["intro"] and "restart it in the app" in g["intro"]


def test_note_after_the_steps_is_kept_for_the_end():
    g = build_guide("Open the Brightline app, go to Wi-Fi, and tap Change password. "
                    "Every connected device has to rejoin with the new password.", APP)
    assert targets(g) == ["app-brightline", "nav-wifi", "wifi-password"]
    assert g["after"] == "Every connected device has to rejoin with the new password."
    assert "rejoin" not in g["intro"]


def test_navigation_phrases_without_verbs():
    g = build_guide("Tell us at least 14 days before you move, in the app under Account then Move service.", APP)
    assert targets(g) == ["app-brightline", "nav-account", "account-move"]
    assert g["steps"][1]["say"] == "Go to Account."
    assert g["steps"][2]["say"] == "Tap Move service."


@pytest.mark.parametrize("answer", [
    "If a payment is more than 10 days late, a late fee of 5 dollars is added.",
    "You can pay your Brightline bill with mobile money.",  # names a button but gives no directions
    "",
])
def test_no_guide_without_in_app_directions(answer):
    assert build_guide(answer, APP) is None


def test_every_step_points_at_a_real_element():
    g = build_guide("Open the Brightline app, go to Billing, then Payment methods, and switch on Autopay.", APP)
    for step in g["steps"]:
        ids = [e["id"] for e in g["screens"][step["screen"]]["elements"]]
        assert step["target"] in ids
    assert targets(g)[-1] == "methods-autopay"


async def test_screen_hosts_get_intro_voice_hosts_get_full_directions(desk):
    voice = await desk.ask("ada", "How do I change my Wi-Fi password?")
    screen = await desk.ask("tunde", "How do I change my Wi-Fi password?", screen=True)
    assert "tap Change password" in voice.speech
    assert screen.speech.endswith("I'll show you where to tap, step by step.")
    assert screen.guide["steps"][-1]["target"] == "wifi-password"
    assert voice.guide == screen.guide  # the card can still offer it


async def test_resolved_ticket_update_comes_with_a_guide(desk, settings):
    await desk.ask("ada", "Can I pay with mobile money?")
    publish_mobile_money(desk, settings)
    await desk.recheck_open_tickets()
    data = desk.my_tickets("ada", screen=True)
    update = data["updates"][0]
    assert targets(update["guide"])[-1] == "pay-mobile"
    assert "I'll show you where to tap" in data["speech"]
    assert "tap Pay now" not in data["speech"]
