# Product: LifeClock

**User.** People who think in terms of time well spent: productivity and stoicism fans, people at a milestone birthday, people who want a memento mori on their desk. Secondary: anyone searching for life expectancy by age or country.

**Painful job.** Time feels abstract until it's gone. "Decades" doesn't move anyone; a number ticking down does.

**Promise.** In ten seconds, see the seconds ahead of you on average, from the same tables actuaries use, privately, with nothing stored.

**Wedge.** A share card with one big number ("1,453,133,934 seconds ahead of me") that makes people ask "how many do I have?", plus search pages people already look for: "death clock", "life expectancy calculator", "life expectancy in Japan by age", "when will I be a billion seconds old".

**Why now.** Memento-mori and "4,000 weeks" thinking is mainstream; second screens and tablets make a desk clock free; WHO's life tables now cover 2023 for 185 countries through an open API.

**Activation metric.** A visitor starts a clock (`clock_start`). Then: share cards made per start, and desk-mode opens.

**First revenue event.** Someone buys a printed poster or shirt of their number ("I had X seconds left when I bought this shirt"). The slot exists (`POSTER_URL`); the product and payment link need Jack (OPERATIONS.md key 2).

**What v1 deliberately won't do.**
- Store or send birthdays anywhere, or ask for an email.
- Adjust the estimate for health, habits or lifestyle (that would be medical advice).
- Call itself a "death clock" or use fear copy. It shows an average, says so, offers a count-up mode and links to crisis lines.
- Hardware or a Tidbyt app (until people show they want the clock on their desk).
