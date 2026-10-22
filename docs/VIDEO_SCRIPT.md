# Demo video script (about 2 minutes 50 seconds)

The submitted video follows this script. It was recorded with `demo-video/record_demo.py`, which drives the simulator in Microsoft Edge with Playwright and narrates with the Windows voices (David for the narrator, Zira for Alexa). To re-record with your own voice, follow the same order. Leave "Read replies aloud" on so Alexa is heard, and use no music.

Before recording, run `python -m docdesk reset`, then `python -m docdesk serve`, and open `http://127.0.0.1:8765/` and `/console`.

| Scene | Screen | Narration |
|---|---|---|
| Title | Title card | "This is DocDesk. It puts a brand's help centre inside Alexa+. Answers come only from the brand's own articles, and instead of just reading out directions, Alexa shows you where to tap, step by step." |
| 1. Where to tap | As Ada, type "Alexa, ask Brightline how do I change my Wi-Fi password?". The card shows the Brightline app, and the glow moves from the app icon to Wi-Fi to Change password while Alexa reads each step. | "Ada asks how to change her Wi-Fi password." Then: "The card shows Brightline's app, with a glow on exactly where to tap, while Alexa says each step. On the right is the real MCP traffic, on the November 2025 spec, over Streamable HTTP." Expand the initialize result in the inspector. |
| 2. A ticket, not a guess | Type "Can I pay my bill with mobile money?" | "Now a question the help centre doesn't cover." Then: "Instead of guessing, DocDesk opens ticket one for the support team, and remembers it for Ada." |
| 3. Support publishes | Console: Fill example, then Publish. The note says it answered ticket 1. | "Brightline's support team publishes one short help article, and DocDesk re-checks every open ticket against it, by itself." Then: "The new article answers ticket one." |
| 4. Good news, then the glow | Back on the simulator as Ada: "Alexa, ask Brightline for any updates on my tickets". Alexa gives the good news, then the glow walks through Billing, Pay now, Mobile money. | "So when Ada asks for an update," Then, after the walkthrough: "she hears the good news, and gets walked through paying, step by step. Nobody had to call her back." |
| 5. Doc gaps | Switch to Brightline team: "Alexa, ask Brightline what customers are asking that our docs don't cover". | "Staff can also ask what customers wanted that the docs couldn't answer." |
| Close | Closing card | "The same MCP server also works with a Strands Agents host built for Amazon Bedrock, and the browser client is open source as mcp-lite. Alexa+ itself is simulated. Everything else is real, and tested." |
