# Rooms4You Landlord Acquisition: Execution Kit

> **Starts:** Monday 2 November 2026
>
> **Supply deadline:** Sunday 13 December 2026, with ~150 live, verified listings
>
> **Tenant launch:** Monday 4 January 2027, the start of the January rush

This turns the Landlord Acquisition Playbook into daily action:

- **Founder**: works from home, keeps the app running, and runs **online acquisition** and the **command centre**.
- **CBO Jacob Hopa**: leads the **street team** of champions.

No funding needed. Everything here can be done with phones, data, a printer and shoe leather.

---

## 0. Why these dates

- **December is move-out season.** Students finish, contract workers go home,
  people relocate. Landlords end up with **empty rooms in December and
  January** and are most open to a new way of finding tenants.
- **January is peak tenant demand**: new jobs, TVET and university intake,
  people returning to the city after the holidays. If our app is full of rooms
  in the first week of January, tenants find what they need on day one.
- **Mid-December to early January the streets go quiet** because many people
  travel home. So the hard push happens **now through 13 December**.
- From 14 December to 3 January we keep listings fresh by phone and WhatsApp
  (confirm availability, add photos) and prepare tenant marketing.

---

## 1. Before 12:00 today: founder's app checklist

These came out of checking the current code. Fix them **before** the first
champion signs up a landlord.

| # | Issue in the app today | What to do now (no code) | Proper fix later (I can build it) |
|---|---|---|---|
| 1 | **The free trial ends after 30 days** and then the landlord is switched off. Landlords signed this week would be locked out on ~2 December, before launch. | Every evening, in **Django admin → Memberships**, set each new landlord to **tier = Gold** and **trial end = 30 April 2027**. Takes ~20 seconds per landlord. | A "Founding Landlord" flag that sets this automatically plus a badge |
| 2 | **Sign-up needs an email address** and sends the verification code (OTP) **by email**. Many township landlords have no email they remember. | Teach champions: **use "Continue with Google"**. Almost every Android phone already has a Google (Gmail) account signed in, even if the owner never uses it. That's one tap and no OTP. If there's no Google account, help them create a Gmail on the spot. | Phone-number sign-up with SMS/WhatsApp OTP (the `sms-otp` branches look like a start) |
| 3 | **Sign-ups are capped at 8 attempts per hour per network** (anti-fraud). If a champion signs up several landlords on **the champion's own hotspot**, the 9th gets blocked. | Sign landlords up **on the landlord's own phone and data** (best anyway, since they keep the account). If you must use the champion's phone, switch networks between landlords, or don't do more than ~6 per hour on one hotspot. | Raise the limit, or allow-list a "field agent" account |
| 4 | **Listing cap**: Starter = 2 listings. | The Gold upgrade in #1 removes it. Champions also group identical rooms into **one listing using total/available units**. | Covered by #1 |
| 5 | **Success fee** (R100–R350 when a tenant moves in) | Decide today: is the **first placement free** for founding landlords? Champions must give one consistent answer. | Waiver flag on the first invoice |
| 6 | **WhatsApp notifications** are built but switched off | Optional this week. Follow `docs/whatsapp_setup.md` when there's time. Landlords live on WhatsApp, so enquiry alerts there will matter in January. | — |

**Also today:**
- [ ] Get a **dedicated Rooms4You WhatsApp Business number** (a cheap second SIM, R0–R30). Name it "Rooms4You – List your room FREE", with logo, short description, catalogue and auto-reply. This number goes on every flyer.
- [ ] Create two WhatsApp groups: **"R4Y Street Team"** (Founder, Jacob, champions) and **"R4Y Command"** (Founder + Jacob).
- [ ] Share the **tracker spreadsheet** (`Rooms4You_Acquisition_Tracker.xlsx`) as a Google Sheet with Jacob and every champion, so everyone writes into the same file.
- [ ] Test the full landlord sign-up yourself on a cheap Android phone: Google sign-in → add room → photos → publish. Time it. If it takes more than 10 minutes, note what slowed you down.

---

## 2. Who does what

| Person | Role | Owns | Daily output |
|---|---|---|---|
| **Founder** | Command centre and online acquisition | App uptime, admin upgrades, verification calls, online channels, tracker, daily scoreboard | 10+ online conversations, every new landlord upgraded and verified within 24 h |
| **Jacob Hopa (CBO)** | Head of street team | Zone plans, champion pairs, quality of listings, community anchors (councillors, churches, stokvels) | Morning brief, 1 anchor meeting a day, evening report |
| **Champion pairs** | Door-to-door | Signing up landlords, taking photos, collecting leads | **Per pair per day: 30 doors, 4 listed on the spot, 6 leads** |

Pairs: champions work **two by two**. It's safer, and landlords trust a pair
more. If there's an odd number, Jacob makes up a pair or the extra person
works sign sweeps.

---

## 3. Street team: how a champion's day works

### 3.1 Daily rhythm

| Time | What |
|---|---|
| **08:00** | Jacob's voice note in **R4Y Street Team**: today's zone and streets per pair, yesterday's score, one tip |
| **08:30–09:00** | Pairs meet at the zone start point. Check phone charge, data, flyers, ID cards |
| **09:00–12:30** | **Door-to-door block 1**. Best time to find gogos and landlords at home |
| **12:30–13:30** | Lunch; **upload today's leads to the tracker** |
| **13:30–16:30** | **Block 2**: doors, plus revisit the morning's "come back later" houses |
| **16:30–17:00** | Photos of "Room to rent" signs on the way out (see 3.4) |
| **17:30** | Each pair sends the **daily report** (template in §7.6) |
| **19:00** | Founder posts the scoreboard |

**Saturdays** are the best day (landlords are home). **Sundays**: churches
and stokvel meetings only, by arrangement. **One full rest day per week.**

### 3.2 At the door: two outcomes, both count

**Outcome A: "List now"** (the landlord is willing and has a few minutes)
→ Do the 10-minute onboarding (§3.3) and the listing is live before you leave.

**Outcome B: "Lead"** (interested but busy, phone at work, no data, or wants
their child to help)
→ Collect a **lead card**: name, cell/WhatsApp number, street and section,
number of rooms, rent range, when rooms become free, best time to call, and
**consent** ("May Rooms4You WhatsApp you to set it up?").
→ The founder calls them within 24 h and does the listing remotely over
WhatsApp, with the landlord sending photos.

**Not interested** → thank them, leave a flyer, log "declined" with the reason.
No arguing. Many will call back after a neighbour signs up.

### 3.3 The 10-minute onboarding

1. **Consent**: "Are you happy for us to put your room on Rooms4You?"
2. **Sign in with Google** on the landlord's phone (§1 #2). Role = **Landlord**.
3. **Photos** (the champion takes them): ≥3 per room type, in daylight, with
   the curtains open and the bed made. One of the toilet/bathroom and one of
   the yard entrance **without the house number**. Phone held **sideways**.
4. **Title**: `[room type] + [best feature] + [section/landmark]`, e.g.
   *"Backroom with own toilet, Tembisa Ext 5, near Mall"*.
5. **Price, deposit, what's included** (water, prepaid electricity, Wi-Fi), and the rules.
6. **Identical rooms → one listing**, with total units and available units.
7. **Location**: suburb, town, postal code, map pin. (The street address stays private.)
8. **Phone + WhatsApp number**, then **Publish**.
9. Show the landlord three buttons: **mark taken/available**, **confirm
   availability** (asked every 14 days), and **messages**.
10. Hand over a flyer, and say: *"Our office will call you tomorrow to welcome you."*
11. Log it in the tracker with **status = Listed**.

### 3.4 Sign sweeps ("Room to rent" signs)

Photograph every handwritten sign: wall, gate, pole, spaza. Log the number,
street, section and date in the tracker with **source = Sign**. The founder
or a champion calls it the same afternoon using the script in §7.2. These
landlords already **want** tenants, so expect the highest conversion.

### 3.5 Champion rules

- Wear the T-shirt or bib and the ID card. Introduce yourself by name and company.
- **Never promise tenants, income or dates.** Promise visibility and support.
- Say the **fee truth** (§6) every time. Never "it's all free forever".
- Never list a room without the owner's consent. Never take money from anyone.
- No visits after dark. Stay in pairs. Leave any situation that feels wrong.
- Greet properly (Ma, Baba, Gogo). Speak the household's language.

---

## 4. Founder: online acquisition from home

You'll spend roughly **3–4 hours a day** on acquisition and the rest on the app.

### 4.1 Daily routine

| Time | Task |
|---|---|
| 07:30 | App health check: site up, sign-up works, last night's errors |
| 08:00 | **Admin sweep**: upgrade yesterday's landlords to Founding Gold (§1 #1) |
| 08:30–10:00 | **Online hunt** (§4.2): 10+ new conversations |
| 10:00–12:00 | Software work |
| 12:00–13:00 | **Call the street team's leads** and sign-photo numbers from the morning; list them remotely |
| 13:00–16:00 | Software work |
| 16:00–17:00 | **Verification and welcome calls** to every landlord listed yesterday (§4.4) |
| 17:30–19:00 | Read daily reports, update the tracker, **post the scoreboard** |
| 19:00–20:00 | Second online hunt (Facebook is busiest in the evening) |

### 4.2 Online channels, in order

1. **Facebook groups**: search "rooms to rent [township]" and "backrooms
   [township]", and join 10–15 groups across your launch zones.
   - Each landlord post = a lead. **Comment or inbox (not spam):** script §7.3.
   - Twice a week, post the **landlord call-out** (§7.4) where the group rules allow it.
2. **Facebook Marketplace → Property rentals.** Filter by area and message
   individual landlords (not agencies) with the script in §7.3.
3. **Gumtree** room adverts in your zones. Same script, by WhatsApp or phone where a number is shown.
4. **Your own Facebook page, TikTok and WhatsApp Status.** Three times a week, post:
   a landlord success story, a "rooms now live in Tembisa: 37" counter, or a
   15-second "how to list your room in 5 minutes" screen recording.
5. **WhatsApp community groups** (your own and family networks). Ask people
   to forward the landlord call-out. Never add strangers to groups.
6. **Competitor-listed landlords** (on other room apps). These landlords are already online
   and need no convincing about digital. Contact them with the §7.3 script ("list on
   us too, it's free").

**Remote listing.** When someone says yes online, list them over WhatsApp:
they send 3–5 photos and the details (§7.5 checklist), and you either create
the account with them on a call or send the sign-up link and guide them step by step.

**POPIA rule.** Only contact numbers that were published for renting rooms,
or that the person gave us. Never copy someone's advert or photos into our app
without their "yes". Keep the WhatsApp reply of consent.

### 4.3 Remote onboarding over WhatsApp

1. Send §7.5 (what we need).
2. Short voice call: "Tap the link → Continue with Google → choose Landlord."
3. You guide them on the call while they add the room, or with their
   permission **you** fill it in on a shared screen. Their photos go in.
4. Publish → upgrade in admin → welcome message (§7.7).

### 4.4 Verification and welcome call (every new landlord, within 24 h)

- "Hi Ma, it's [your name] from Rooms4You. [Champion] visited you yesterday.
  Thank you for joining as a Founding Landlord!"
- Confirm: they own or are authorised to rent the rooms; the price; the
  number of rooms; the WhatsApp number.
- Ask: "How was our team? Do you know anyone else who rents out rooms?" → referral leads.
- Mark **Verified** in admin and in the tracker.
- **Red flags** (no owner, can't describe the room, asks for money, rent far
  below the area): don't verify, hide the listing, tell Jacob.

---

## 5. Targets and scoreboard

### 5.1 Targets

| Week | Dates | Zones active | New listings | Running total | Focus |
|---|---|---|---|---|---|
| 1 | 2–8 Nov | **Zone A only** (whole team) | 20 | 20 | Learn: script, objections, onboarding speed |
| 2 | 9–15 Nov | A + B | 25 | 45 | Split into pairs per zone; start anchors |
| 3 | 16–22 Nov | A + B + C | 30 | 75 | Full speed; referrals start |
| 4 | 23–29 Nov | A + B + C | 30 | 105 | Churches and stokvels; month-end move-outs |
| 5 | 30 Nov–6 Dec | A + B + C | 25 | 130 | Fill price and room-type gaps; student areas |
| 6 | 7–13 Dec | A + B + C | 20 | **150** | Quality sweep: every listing has photos, is verified, confirmed |
| — | 14 Dec–3 Jan | — | top-ups | 150+ | Phone and WhatsApp upkeep; tenant launch prep |
| **Launch** | **Mon 4 Jan 2027** | | | | Tenant marketing starts, zone by zone |

**Zone A** = the township where the team has the strongest connections and
the most "Room to rent" signs. Jacob picks it today. Zones B and C are
picked by Friday from week 1's learning.

**Launch rule per zone:** a zone "goes live" for tenant marketing once it
has **40+ available listings with photos, across at least 3 price bands.**

### 5.2 What to track daily (it's in the tracker)

Doors knocked → Landlords spoken to → Listed now / Leads → Leads converted
→ Verified → Upgraded to Founding Gold. Plus **declines with reasons.**

**Healthy numbers after week 1:** 1 in 3 landlords spoken to lists, and
half of leads convert within 48 h. If you're below that, change the pitch, not the effort.

### 5.3 Champion rewards (no-funding version)

- Pay **per verified live listing**, never per sign-up. Suggested: R20–R30
  per listing, plus R50 when a listing they brought gets its first placement.
  Adjust to what you can afford, and pay weekly on Fridays.
- If cash is too tight now: record the points and pay out once success fees
  start coming in. Agree this **in writing** with each champion upfront.
- Weekly "Champion of the Week" shout-out, judged on quality and count.

---

## 6. The one consistent message

Everyone, on the street or online, says the same thing:

> **"Listing your room on Rooms4You is free. As a Founding Landlord you get
> unlimited listings free until the end of April 2027. We only earn a small
> once-off fee, from R100, if a tenant who found you through Rooms4You
> actually moves in. *[If you decide to waive it: Your first tenant through us is free.]*
> Your street address stays private. We launch to tenants in January,
> which is the busiest month for people looking for rooms."**

---

## 7. Message templates (copy and paste)

Translate into isiZulu, Sesotho, Setswana etc. as needed. Keep it warm and short.

### 7.1 WhatsApp Business auto-reply (greeting message)
> Sawubona / Dumela! 👋 Welcome to **Rooms4You**: rooms to rent in your area, online and safe.
> 🏠 **Landlords:** list your rooms **FREE**. Reply **LIST** and we'll help you set it up in 10 minutes.
> 🔎 **Looking for a room?** Reply **ROOM** and we'll let you know when we launch in January.

### 7.2 Calling a number from a "Room to rent" sign
> "Hello, good afternoon Ma/Baba. My name is ___ from Rooms4You. I saw your
> sign in [street/section] about a room to rent. Is it still available?
> … We're a new local app where people in [area] search for rooms. We're
> signing up landlords for free before we launch to tenants in January, so
> your room is one of the first they'll see. Can I help you put it up? It
> takes about 10 minutes, or I can WhatsApp you what we need."

### 7.3 Inbox / WhatsApp to a landlord advertising online
> Hi [name], I saw your room in [area] advertised on [Facebook/Gumtree].
> I'm [name] from **Rooms4You**, a new app just for rooms to rent in [area].
> We'd love to list your room **for free** so more people searching in
> [area] can find it. 🏠 You stay in control of who views, and your street
> address stays private. Can I help you set it up? It takes about 10 minutes.

### 7.4 Facebook group / Status call-out for landlords
> 📢 **LANDLORDS IN [AREA]: list your rooms FREE on Rooms4You!**
> Empty room? Tired of time-wasters calling? Rooms4You is a new local app
> where tenants search for rooms in [area]. **We launch in January**, the
> busiest month for people looking for rooms.
> ✅ Free listing (Founding Landlord offer)
> ✅ Your address stays private
> ✅ We help you set it up in 10 minutes
> 👉 WhatsApp **LIST** to [number] or visit rooms4you.co.za

### 7.5 What we need from you (remote listing)
> Great! Please send us:
> 1️⃣ 3–5 photos of the room (daylight, curtains open) + 1 of the toilet/bathroom
> 2️⃣ Monthly rent and deposit
> 3️⃣ What's included (water, electricity, Wi-Fi?)
> 4️⃣ How many rooms are free, and from when
> 5️⃣ Your section/suburb and nearest landmark (not your house number)
> 6️⃣ Any rules (working people only, couples, kids, visitors?)
> We'll call you to finish setting up. 🙏

### 7.6 Champions' daily report (each pair, 17:30)
> 📊 **[Pair names] – [Zone] – [Date]**
> Doors: __ | Spoke to landlords: __
> ✅ Listed now: __ | 📝 Leads: __ | 📸 Signs photographed: __
> ❌ Declined: __ (top reason: ____)
> 💡 Best objection today and how we answered it: ____
> 📍 Streets covered: ____ | Tomorrow: ____

### 7.7 Welcome message after listing (founder)
> 🎉 Welcome to Rooms4You, [name]! You're now a **Founding Landlord**. Your
> room is live: [link]. Share the link with anyone looking for a room.
> Every 2 weeks the app asks you to **confirm your room is still available**,
> so please tap confirm. It keeps you at the top of search. Any questions?
> Just WhatsApp this number. 🙏

### 7.8 Fortnightly broadcast to founding landlords
> 🏠 Rooms4You update: we now have **[number] rooms** listed in [area]!
> Tenant launch is on **4 January**. 👉 Please check that your room's details
> and photos are still correct, and tap "Confirm available". Know another
> landlord? Send them to us: [number]. Thank you for building this with us! 🙏

### 7.9 Lead card (printed, A6; champions fill in by hand or in the sheet)
> Date ___ Champion ___ Zone/Section ___
> Landlord name ___ Cell ___ WhatsApp ___
> No. of rooms ___ Rent range R___–R___ Rooms free from ___
> Best time to call ___ ☐ Agrees to be contacted by Rooms4You (POPIA)
> Notes ___

---

## 8. Week 1, day by day

| Day | Founder | Jacob + champions |
|---|---|---|
| **Mon 2 Nov** | App checklist §1. Set up WhatsApp Business, groups and the shared tracker. Test sign-up on an Android phone. | Jacob picks **Zone A** and maps 4–6 streets per pair. **Training (2 h):** pitch §6, roles, onboarding §3.3 practised on each other's phones. **Afternoon:** sign sweep only (photograph signs, no doors). |
| **Tue 3 Nov** | Call yesterday's sign numbers. Join 10–15 Facebook groups. Brief Jacob on what the calls taught you. | **First full door day.** Whole team in Zone A, in pairs. Jacob shadows each pair for 30 min. |
| **Wed 4 Nov** | Verification calls. Admin upgrades. First online call-out (§7.4). | Doors. 12:30 check-in call: what objections are we hearing? Adjust the pitch. |
| **Thu 5 Nov** | Fix the worst sign-up friction found so far (or ask me to). Online hunt. | Doors. Jacob visits the **ward councillor's office** and **2 churches** in Zone A to ask for slots. |
| **Fri 6 Nov** | Scoreboard and first weekly review with Jacob (30 min). Pay champions if agreed. | Doors (morning only). Afternoon: **team debrief.** Choose Zones B and C. |
| **Sat 7 Nov** | Light: verification calls, admin. | **Big door day**, since landlords are home. All pairs. |
| **Sun 8 Nov** | Rest / planning. | Churches or stokvel if arranged; otherwise **rest.** |

**End of week 1 target:** 20 live listings in Zone A, top 5 objections
written down, onboarding under 10 minutes.

---

## 9. Weekly review (every Friday, 30–45 min: Founder + Jacob)

1. Scoreboard: listings vs target, per zone and per pair.
2. Conversion by source: door, sign, Facebook, referral, anchor. **Move effort to what works.**
3. Top 3 objections, and is our answer working?
4. Quality: listings without photos? Stale (not confirmed in 14 days)? Unverified?
5. App issues the team hit, and the fix list for next week.
6. Next week: zones, streets, anchor meetings, targets.

---

## 10. When things go wrong

| Problem | Do this |
|---|---|
| Landlords say "I'll do it later" a lot | Switch from "List now" to **lead capture**, and have the founder close by phone that evening. Ask "When should we call?" and book a time. |
| Sign-up keeps failing | Champion sends a screenshot to **R4Y Command** straight away. Founder fixes it or switches to remote onboarding. Never leave a landlord with a broken account. |
| "Too many signup attempts" | They've hit the per-network limit (§1 #3). Use the landlord's own phone/data, or wait an hour. |
| Few landlords at home on weekdays | Shift doors to 14:00–17:30 and Saturdays; use mornings for sign sweeps and anchor visits. |
| Suspicious "landlord" | Don't verify. Hide the listing in admin. Use the admin **suspend account** action if it's a scam. |
| A champion's numbers are high but quality is low | Pay only on **verified** listings, and Jacob spot-checks 3 listings per pair per week. |
| The team is losing energy | Share every win in the group: the first landlord, the 50th listing, a nice review. Jacob calls the quietest champion personally. |
| Landlords ask "Where are the tenants?" | Honest answer: "Launch is 4 January." Send the fortnightly broadcast. Once a zone has 40+ listings, start small tenant promos there early. |

---

## 11. Small costs to plan for (rough estimates, check local prices)

| Item | Estimate |
|---|---|
| WhatsApp Business SIM | R0–R30 |
| 500 A5 flyers (landlord) | ~R300–R600 at a local print shop |
| 200 A6 lead cards | ~R100–R200 |
| Champion ID cards (laminated, printed at home) | ~R50 |
| Data for champions (1 GB each per week) | ~R80–R100 per person per week |
| Taxi fare | per zone |
| **Week 1 total (excluding champion pay)** | **≈ R1,000–R2,000** |

T-shirts can wait. A printed ID card plus a clear introduction does the job in week 1.
