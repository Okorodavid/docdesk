# Demo video script (2 minutes 45 seconds)

Record the screen at 1920 by 1080 with the simulator on the left and the console in a second tab. Speak the narration yourself; leave "Read replies aloud" on so Alexa's voice is heard. No music.

Before recording, run `python -m docdesk reset`, then `python -m docdesk serve`, and open `http://127.0.0.1:8765/` and `/console`.

| Time | Screen | Say |
|---|---|---|
| 0:00-0:20 | Simulator, empty | "When you're stuck with your internet, you dig through a help site, wait hours for an agent, or get a confident wrong answer from a bot. DocDesk puts a brand's real help centre inside Alexa+, and it never guesses." |
| 0:20-0:45 | As Ada, click "how do I restart my router?" Point at the source card, click it to open the help section. | "Ada asks how to restart her router. The answer comes only from Brightline's help centre, and the card shows the exact section it used." |
| 0:45-1:00 | Point at the inspector: initialize, protocolVersion 2025-11-25, tools/list, tools/call. | "This is a real MCP session over Streamable HTTP, spec 2025-11-25. The host picks the ask_support tool, and the card is an MCP App the host renders in a sandbox." |
| 1:00-1:20 | Click "Can I pay my bill with mobile money?" | "Now something the help centre doesn't cover. Instead of guessing, DocDesk opens ticket 1 for Brightline's support team and remembers it for Ada." |
| 1:20-1:30 | Switch to Tunde, ask "Any news on my tickets?" | "Tickets are private. Tunde sees none of Ada's." |
| 1:30-1:55 | Console tab. Ticket 1 is listed. Click Fill example, then Publish. Show "It answered 1 open ticket: #1". | "Brightline's team sees the gap and publishes one short article. DocDesk indexes it and re-checks every open ticket by itself. Ticket 1 is now answered." |
| 1:55-2:15 | Back to Ada. Ask "Is there a late fee?" Let Alexa speak the good news. | "Next time Ada talks to Alexa, she hears the good news first, then her answer. Nobody had to call her back." |
| 2:15-2:30 | Switch to Brightline team, ask for the doc gaps report. | "The team gets a report of what customers asked that the docs couldn't answer, grouped by topic. Customers asking for it are refused." |
| 2:30-2:45 | Terminal running the Strands host command, then the README's real-vs-simulated table. | "The same server works with a Strands Agents host on Amazon Bedrock, and the browser MCP client is open source as mcp-lite. Alexa+ itself is simulated, because add-on tools are partner-only. Everything else you saw is real and tested." |
