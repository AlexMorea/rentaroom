# Landlord Acquisition Playbook: Townships & Local Areas

> Goal: before Rooms4You markets to tenants, put enough **real, available
> rooms** on the app that a tenant searching in our launch areas finds
> something worth contacting. Written for the founder and a team of five
> field agents. Treat the figures as targets to adjust after week 2, not
> fixed rules.

---

## 1. Market research: what we are walking into

### 1.1 The size of the opportunity

Backyard and back-room renting is one of the biggest housing markets in
South Africa. Almost all of it is informal and offline.

| Indicator | Figure | Source / caveat |
|---|---|---|
| People renting a backyard room | ~10 million (≈20% of population) | RoomKing estimate, 2023 ([BusinessLIVE](https://www.businesslive.co.za/fm/fm-fox/entrepreneurs/2023-08-03-profile-backyard-rentals-go-online-with-roomking/)) |
| Annual value of backyard rentals | R12bn (2023) to ~R30bn (2025) | RoomKing / GG Alcock via [Financial Mail](https://www.financialmail.businessday.co.za/fm/features/2025-07-31-backyard-rentals-go-big-in-urban-housing/). These are estimates and they differ a lot. |
| Households in backyard rental units | ~919,000 (2016), ≈26% of the rental market | Government-cited figure ([BusinessTech](https://businesstech.co.za/news/?p=658501)) |
| Share of households renting in Gauteng | 36.6%, the highest in SA | Census 2022 ([Daily News](https://dailynews.co.za/news/politics/2023-10-11-gauteng-residents-are-more-likely-to-rent-than-own-their-homes--census-2022/)) |
| Typical township room rent | ~R1,200 average nationally; R1,900–R2,200 for better rooms in Soweto and Tembisa | RoomKing average; Gumtree listings sampled 2025. This is a small sample, so check it in the field. |

**What this means for us:** supply already exists. Thousands of rooms
sit behind every township's gates. The real problem is that landlords
**don't know us, don't trust us yet, and already fill rooms "well enough"**
through word of mouth. We are not creating rooms. We are moving existing
rooms online.

### 1.2 Who the landlords are (segments)

Plan the work around these segments. Each one needs a different pitch.

| Segment | Profile | What they care about | Priority |
|---|---|---|---|
| **A. Multi-room owners** | 4–20 rooms on one or two stands, often built as a business | Low vacancy, reliable payers, less admin | 🔴 Highest. One "yes" gives many listings |
| **B. "Gogo" / family landlords** | Older homeowners, often women, renting 1–3 back rooms to supplement a pension | Safety, respectful tenants, not being cheated | 🟠 High: many of them, very trusted by neighbours |
| **C. New builders / investors** | Currently building rooms, or just finished | Filling new rooms fast | 🟠 High: they need tenants *now* |
| **D. Student-area landlords** | Near TVET colleges, universities, nursing colleges | Filling rooms every January/July | 🟡 Seasonal: start in Nov for Jan intake |
| **E. Informal agents / caretakers** | People who "manage" rooms for several owners for a cut | Commission, contacts | 🟡 Useful channel but verify ownership carefully |

### 1.3 How landlords find tenants today (our real competition)

1. **Word of mouth.** Current tenants, neighbours, church, work. This is free
   and trusted, and it's what we compete with most.
2. **"Room to rent" signs** on walls, gates and poles with a phone number.
3. **WhatsApp groups** (community, street, church, stokvel groups).
4. **Facebook groups and Marketplace** ("Rooms to rent in Soweto", etc.).
5. **Gumtree.**
6. **Specialist apps** such as RoomKing and Roomsta, which already target this
   market. This proves the model works, but landlords may already have been
   asked to sign up for something like us.
7. **Spaza / supermarket notice boards.**

### 1.4 Landlord pains we solve (lead with these)

| Pain | How Rooms4You answers it |
|---|---|
| Rooms stand empty between tenants, and every empty month is lost income | Your room is visible 24/7 to people actively searching in your area |
| Endless calls from people who aren't serious, or who want a different price or area | Tenants see the price, photos and rules *before* they call |
| Fear of scammers and bad tenants | Verified-landlord badge, fraud reporting, in-app messaging, Guardian safety mode for viewings |
| Strangers knowing your address | **Your full address is not shown publicly.** Tenants see the area and suburb. You decide who visits |
| Don't have time or skill for "apps" | We set it up with you on your phone in about 10 minutes |
| Paying for adverts | Free to list during launch (see §2 for what "free" must mean in the app) |

### 1.5 Likely objections

| Objection | Response |
|---|---|
| "What's the catch? Who pays?" | "Listing is free. We only earn a small once-off fee **if** a tenant you found through us actually moves in, starting at R100. If nobody moves in, you pay nothing." *(Say this honestly. See §2.)* |
| "I don't need it, my rooms fill up." | "Great. Then list it for the next time someone moves out. It costs nothing, and you'll have people waiting instead of an empty month." |
| "Is this SARS / the municipality?" | "No. We're a private company that helps rooms get tenants. We don't share your details with government." *(Only say this if it's true under our privacy policy.)* |
| "I don't trust apps / I've been scammed." | Show the verified badge, show a real listing, give them your name and team ID card, and leave a printed flyer with the support number. |
| "I don't have data / a smartphone." | List it on their behalf, using their phone number and their consent. Their son or daughter can manage it later. |
| "I don't want everyone to see my house." | Photos of the **room only** are fine. The street address stays private. |

---

## 2. Fix this in the app before the team goes out ⚠️

I checked how the app works today. Several rules will **break the "free
listing" promise** if nobody changes them:

1. **The trial ends after 30 days** (`Membership.trial_end`). When it
   ends, `MembershipMiddleware` deactivates the landlord, and they can't add
   listings until they pay. A landlord signed up in week 1 would be
   locked out in week 5, before tenant marketing has even started. That
   would damage trust in their neighbourhood.
2. **The free Starter tier allows only 2 listings.** Segment A landlords with
   8 rooms will hit the limit immediately.
   *Workaround that already exists:* one listing can cover several identical
   rooms via **total units / available units**. Teach agents to group
   identical rooms into one listing.
3. **There is a success fee** (R100–R350 once a tenant moves in). That's fine
   and fair, but agents must **say so upfront**. A landlord who is told
   "it's all free" and then gets an invoice will tell the whole street.
4. **Required fields** include full address and postal code. Agents should
   know the postal codes for their zones before they go out.

**Recommended: a "Founding Landlord" programme.**
- Every landlord signed up by the team gets **Gold (unlimited listings) free
  for 6 months**, or until a fixed date, e.g. 30 April 2027.
- You can do this today without code: in Django admin → Memberships, set
  `tier = gold` and push `trial_end` out to the chosen date (or set
  `is_trial = False` with `status = active`).
- Optional: **waive the success fee for each founding landlord's first
  placement.** It's a strong closing line: "Your first tenant through us is
  completely free."
- Give them a "Founding Landlord" status in your tracking sheet. Later this
  could become a badge in the app.

If you want, I can build this as a proper feature: a `founding` flag, a
bulk admin action, and a badge on their listings.

---

## 3. Strategy: go deep, not wide

**The single most important rule: concentrate.** A tenant in Tembisa doesn't care
that we have 300 listings across Gauteng. They care whether we have 30 in
Tembisa. Spreading five people across ten townships produces an app that
feels empty everywhere.

### 3.1 Pick 2–3 launch zones

Choose by:
- **Tenant demand.** Where are your tenant enquiries and waitlist coming from?
  (Check the placements waitlist and search data.)
- **Room density.** Townships with lots of backyard rooms. Known hotspots
  include Soweto (Protea, Orlando, Dobsonville), Tembisa, Cosmo City,
  Diepsloot, Mamelodi and Sebokeng.
- **Team connections.** Areas where a team member lives or grew up get a
  faster "yes".
- **Demand anchors.** Areas near a TVET college, hospital, mine, factory or
  big taxi rank always have tenants looking.

### 3.2 Targets ("enough supply" to launch)

| Metric | Target per launch zone | Why |
|---|---|---|
| Live, available listings | **40–60** | A search needs to show a full page or two |
| Landlords | 25–40 | Spreads risk, gives price variety |
| Price spread | Rooms under R1,500, R1,500–2,500, and above R2,500 | Every tenant budget finds something |
| Photos | ≥3 per listing, 100% of listings | Listings without photos don't get enquiries |
| Confirmed available in last 14 days | ≥80% | The app demotes stale listings automatically |

**Across 3 zones, that's ~150 listings in 6 weeks.** Five agents need
about **5 live listings per agent per week**, which is very achievable once
the pitch is practised.

---

## 4. The team of five

### 4.1 Roles

| Person | Role | Main job |
|---|---|---|
| Founder | Lead / quality | Approve and verify listings, run the daily huddle, own the tracker, handle hard objections, do admin membership changes |
| Agent 1 | Zone captain: Zone A | Door-to-door plus community anchors in Zone A |
| Agent 2 | Zone captain: Zone B | Same, Zone B |
| Agent 3 | Zone captain: Zone C | Same, Zone C |
| Agent 4 | Digital and phone hunter | Calls numbers from signs, Facebook, Gumtree and WhatsApp groups (with consent); books visits for zone captains |
| Agent 5 | Partnerships and student housing | Churches, ward councillors, stokvels, colleges, hardware stores, builders, property managers |

Agents work **in pairs** for door-to-door when possible. It's safer, and
landlords trust a pair more than a single stranger.

### 4.2 Pay and incentives (suggestion)

Pay for **outcomes that matter**, not sign-ups:
- Small daily stipend or transport and data allowance, plus
- Bonus per **verified live listing** (has photos, correct price, landlord
  confirmed availability), e.g. R20–R50 each, plus
- Extra bonus when a listing they brought in gets its **first tenant enquiry**
  or **placement**.
- Weekly prize for the top agent, by quality as well as count.

Don't pay per account created. That rewards fake or empty listings, which
destroys tenant trust at launch.

---

## 5. Acquisition channels (ranked by expected yield)

### 5.1 Door-to-door and "To Let" sign sweeps 🔴 (biggest channel)
- Walk the zone street by street. Photograph every "Room to rent" sign and
  log the number, street and date.
- Knock on houses with visible back rooms. Ask: *"Good morning Ma/Baba,
  do you rent out rooms here?"*
- Best times: **Saturday morning, Sunday after church, weekday afternoons
  after 15:00.** Avoid month-end Friday afternoons, when people are busy
  with pay day.
- Every landlord who says yes: **list on the spot** (see §7).
- Every "not now": leave a flyer and log a follow-up date.

### 5.2 Phone and WhatsApp follow-up on existing adverts 🟠
- Agent 4 calls numbers from signs, Facebook groups, Marketplace and Gumtree.
- **Never copy someone's advert onto our app without their permission.** That
  breaks POPIA, platform terms and trust. Call, explain, get a "yes", then
  list with them.
- Script: *"Hi, I saw your room in [area] is available. I'm [name] from
  Rooms4You, a new local app for rooms to rent. We'd love to list your room
  for free so more people in [area] can see it. Can I help you set it up
  now? It takes about 10 minutes."*

### 5.3 Community anchors 🟠
One trusted endorsement unlocks a whole street:
- **Ward councillors and ward committees.** Ask to speak for 5 minutes at a
  community meeting.
- **Churches.** Ask the pastor or priest for an announcement, or a table after
  the service.
- **Stokvels and burial societies.** Many members are homeowners and landlords.
- **Street committees and CPFs (community policing forums).** Safety is
  their language, so lead with the safety features.
- **Spaza shops and taxi rank marshals.** Ask to put up a poster ("List your
  room FREE. Call/WhatsApp ...").

### 5.4 Builders and hardware stores 🟡
People building back rooms buy bricks, cement and roofing. Ask local
hardware stores and brickyards to hand out flyers, or to let you stand
outside on Saturdays. These landlords need tenants **soon**.

### 5.5 Student accommodation 🟡
- Visit landlords around TVET colleges and nursing colleges in Oct–Nov
  ahead of the January intake.
- Talk to student representative councils. They often keep lists of
  rooms.

### 5.6 Referrals (start from week 2) 🔴 once running
- Every signed landlord gets asked: *"Do you know anyone else who rents
  out rooms?"* Get the name and number with permission.
- Optional: offer something small for each referred landlord who goes live,
  e.g. airtime or data (R20–R50).

---

## 6. The pitch (60 seconds)

Do this in the landlord's home language. Practise it in isiZulu, Sesotho,
Setswana, Xitsonga, etc. according to the zone, and keep it conversational:

> "Good morning Ma, my name is [name], I'm from Rooms4You. We're a new
> local app that helps people in [area] find rooms to rent, safely.
>
> We're signing up landlords in [area] before we launch, so when tenants
> start searching, your rooms are the first they see.
>
> It's **free to list**. You don't pay anything to advertise. We only charge
> a small once-off fee, from R100, **if** a tenant who found you on our app
> moves in. *(Founding landlords: your first tenant is free.)*
>
> Your address stays private: tenants only see your area and photos of the
> room, and you decide who comes to view.
>
> I can set it up with you right now on your phone. It takes about 10
> minutes. Shall we take a few photos of the room?"

**Close with a question that assumes yes:** "Shall we start with the
photos?" works better than "Are you interested?"

---

## 7. On-the-spot onboarding (10 minutes)

Use the landlord's own phone where possible, so the account is
theirs and they can manage it later. If they can't, create it with their
phone number and email and **written or recorded consent**.

**Checklist (agent ticks each one):**
1. ☐ Consent: landlord agrees to listing and to being contacted (POPIA)
2. ☐ Account created; phone verified (OTP)
3. ☐ Founding Landlord upgrade requested (founder applies it in admin the same day)
4. ☐ **Photos:** at least 3 per room type. Clean room, daylight, curtains open,
   one of the bathroom or toilet, one of the yard entrance (no house number
   visible). Shoot horizontally.
5. ☐ Title that sells: *"Spacious backroom with own toilet, Orlando West,
   near taxi rank"*
6. ☐ Price, deposit, what's included (water, electricity / prepaid, Wi-Fi)
7. ☐ Rules: couples, kids, visitors, pets, working-only, students
8. ☐ Identical rooms grouped into **one listing with total/available units**
9. ☐ Correct suburb and town, postal code, map pin
10. ☐ Contact phone **and WhatsApp number**
11. ☐ Show the landlord how to:
    - mark a room as taken or available
    - **confirm availability**, since the app asks every 14 days and hides
      unconfirmed listings
    - reply to messages
12. ☐ Leave a flyer with the support WhatsApp number and the agent's name
13. ☐ Log in the tracker (§9)

**Verification:** the founder (or a trust person) phones each new landlord
within 48 hours to confirm they are the owner or are authorised, that
details are correct, and to say thank you. Then mark them verified in admin.
Fake listings at launch would be worse than no listings.

---

## 8. Keeping landlords: avoid the "empty app" trap

The biggest risk: landlords list, hear nothing for 6 weeks while we wait for
supply, and decide the app doesn't work. Counter it:

1. **Set expectations honestly:** "We launch to tenants on [date]. Until
   then we're building up rooms in [area]."
2. **WhatsApp broadcast** to all founding landlords every 1–2 weeks with
   progress: "We now have 45 rooms in Tembisa on Rooms4You! Launch is on
   [date]." It's social proof, and it keeps us in mind.
3. **Soft-launch tenant demand per zone as soon as a zone hits ~40
   listings.** Don't wait for all three zones. Run small, local tenant
   promotion in that zone only (Facebook groups, flyers at taxi ranks,
   colleges, factory gates) so landlords get enquiries.
4. **Give each landlord a share link and a printed "Find my room on
   Rooms4You" sign with a QR code** for their gate. It replaces their
   handwritten sign and markets the app to tenants for free.
5. **Availability reminders:** the app nudges every 14 days. Agents follow up
   by phone with landlords whose listings went stale.
6. Celebrate the first placements publicly (with permission). One real
   story, like "Ma Dlamini filled her room in 4 days", sells to the next
   50 landlords.

---

## 9. Tracking: one shared sheet

Columns:

| Date | Agent | Zone | Landlord name | Phone / WhatsApp | Segment (A–E) | Source (door / sign / FB / referral / church …) | # rooms | Status | Listing link | Photos ✔ | Verified ✔ | Founding upgrade ✔ | Follow-up date | Notes / objections |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

**Status values:** Contacted → Interested → Listed → Verified → Live & confirmed → First enquiry → Placement
(also: Not now – follow up, Declined, Not a landlord).

**Daily huddle (15 min, WhatsApp voice note or call):**
yesterday's numbers, best objection heard and how it was answered, today's streets.

**Weekly review:** listings live per zone vs target, conversion rate by channel
(double down on what works and drop what doesn't), top objections, agent leaderboard.

**Funnel to aim for (adjust after week 2):** of 10 landlords spoken to,
about 4 interested, 2–3 listed on the spot, plus 1 more on follow-up.

---

## 10. Six-week plan

| Week | Focus | Output |
|---|---|---|
| **0 (prep)** | Fix the trial and limits issue (§2); print flyers, posters, gate signs with QR code, team ID cards and lanyards; translate and practise the pitch; choose zones; set up the tracker and support WhatsApp number | Team ready, app ready |
| **1** | Pilot: whole team in **Zone A** together. Learn what works, refine the pitch | 15–25 listings; top 5 objections captured |
| **2** | Split into zones; Agent 4 starts phone and sign follow-ups; Agent 5 books churches and councillors | +25 listings (≈45 total) |
| **3** | Full speed; start referrals; follow up the "not now" list | +30 (≈75) |
| **4** | Community meetings and church tables; student-area push; **soft-launch tenant demand in Zone A** if it has 40+ listings | +30 (≈105) |
| **5** | Fill gaps in price range and room type per zone; re-confirm stale listings | +25 (≈130) |
| **6** | Quality sweep: every listing has photos, is verified and confirmed. Prepare for the full tenant launch | ~150 live, verified listings → **start tenant marketing** |

---

## 11. Ground rules (non-negotiable)

- **Consent first.** Never list a room without the owner's agreement. Never
  scrape adverts.
- **Be honest about fees.** Free to list, success fee only on move-in (unless
  waived). No overpromising tenants or "guaranteed" income.
- **Safety for the team.** Work in pairs, carry ID cards, keep a WhatsApp
  location share on, no visits after dark, and leave any situation that
  feels wrong.
- **Quality over count.** One fake or wrong listing that wastes a tenant's
  taxi fare costs more than ten good listings earn.
- **Respect.** Greet properly, use titles (Ma, Baba, Gogo), and be on time.
  Reputation in a township travels street by street.

---

## 12. Field kit checklist

- Branded T-shirt or bib and a printed ID card per agent
- A5 flyers (landlord version: "List your room FREE")
- A3 posters for spaza shops and churches
- QR "Find my room on Rooms4You" gate signs for signed-up landlords
- Phone with data and power bank; a spare phone for landlords without smartphones
- Printed one-page pitch and objection sheet
- Consent form (simple, one page) or recorded verbal consent
- List of postal codes and suburb names for the zone
