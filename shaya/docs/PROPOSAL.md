# Shaya: a South African short-video platform that pays South African creators

**Proposal to the Minister of Communications and Digital Technologies,
Hon. Solly Malatsi**
Draft for discussion · October 2026

---

## 1. The problem

South African creators supply much of the trends, music and comedy that keep
short-video platforms busy, but they are shut out of the main way those
platforms pay creators directly.

* **TikTok's Creator Rewards Programme is not available anywhere in Africa.**
  Eligibility depends on where the creator lives, not on how many views they
  get. Eligible markets include the US, UK, Germany, France, Japan, Brazil,
  Indonesia and others. [IOL, Feb 2026](https://iol.co.za/business-report/companies/2026-02-20-earning-on-tiktok-alternatives-for-south-african-creators-without-the-creator-fund/), [Creators Agency](https://creatorsagency.co/blog/tiktok-creator-rewards-program-2026)
* TikTok's position is that Africa "has not been deliberately excluded" and
  that creators can earn from LIVE gifts, subscriptions and brand deals.
  [ITWeb](https://www.itweb.co.za/article/tiktok-insists-african-creators-are-coining-it-on-the-platform/KzQenvjyknRqZd2r)
* The Minister has repeatedly asked TikTok for "the same equal treatment of
  content creators in South Africa as they do in the US, as they do in the UK".
  So far there has been no breakthrough. [EWN, July 2026](https://www.ewn.co.za/2026/07/24/minister-renews-push-for-tiktok-to-pay-local-creators-for-content), [MyBroadband](https://mybroadband.co.za/news/internet/669499-minister-demands-equal-treatment-from-tiktok-in-south-africa.html), [IOL, Sept 2026](https://iol.co.za/business/2026-09-29-pay-our-creators-south-africa-turns-up-pressure-on-tiktok/)
* Creators organised a **boycott of TikTok on 1 September 2026**. TikTok
  responded with a brand-deal marketplace (TikTok One Creator Marketplace)
  rather than direct pay for views.
  [Explain.co.za](https://explain.co.za/2026/08/18/explained-why-sa-tiktok-creators-want-to-boycott-the-app-on-1-september/), [Techpoint](https://techpoint.africa/insight/techpoint-digest-1442/)
* The audience is large. South Africa has an estimated 17 million TikTok
  users [Business Report](https://businessreport.co.za/technology/mobile-apps/2025-03-28-tiktoks-monetisation-gap--minister-malatsi-calls-for-economic-equity-for-south-african-creators),
  51.7 million internet users and 29.1 million social media identities
  [DataReportal, Digital 2026](https://datareportal.com/reports/digital-2026-south-africa).
  TikTok usage rose from 34% to 47.9% of users between 2023 and 2025, and to
  56% among young adults.

Lobbying TikTok remains worthwhile. But a country should not depend on one
foreign company's product roadmap for its young people's digital income.
**Shaya is the local option: built here, hosted here, paying here.**

## 2. What Shaya is

A short-video app with the core of what people use TikTok for, built around
South African realities:

| South African reality | What Shaya does about it |
| --- | --- |
| Creators can't get paid per view | Pays from **1,000 views** per clip, monthly, to any SA bank account via **PayShap** (instant, using a cellphone number), from **R50** |
| Data is expensive: South Africa pays more for data than 27 other African countries ([AllAfrica, Feb 2026](https://allafrica.com/stories/202602170116.html)), and has the highest data prices among Africa's biggest economies ([BusinessTech](https://businesstech.co.za/news/mobile/185941)) | **Data saver on by default**: about 480p at about 600 kbps, and no preloading. Built to be **zero-rated** by the networks, the way MoyaApp is ([TechCentral](https://techcentral.co.za/?p=200622)) |
| 12 official languages | Every clip is tagged with its language, and viewers can filter the feed by language. isiZulu comedy and Sepedi cooking can find their audience |
| WhatsApp is how things spread | One-tap share to WhatsApp, with link previews |
| Young users and POPIA | 13+ to join. Under-18s can post but can't enter the paid programme. Views are de-duplicated with hashed IDs, not raw phone or IP data |
| Films and Publications Act | Report button on every clip, a human moderation queue, and registration with the FPB as a commercial online distributor ([BusinessTech](https://businesstech.co.za/news/internet/564592/south-africa-has-introduced-new-internet-censorship-laws-what-you-should-know/)) |

**A working MVP has been built** (this repository). It covers the swipe feed,
upload, likes, comments, follows, profiles, sharing, data saver, sponsored
clips, view tracking, the monthly pay calculation, the creator studio and
withdrawals. Demo creators and clips can be loaded with one command.

### Why "Shaya"?

*Shaya* is used across Mzansi's languages and slang for "hit, strike, play"
(*shaya i-beat*, *shaya the moves*). It is short, easy to say in every
language, and sounds like what you do in the app. **Alternatives:** *Jika*
("turn", for the swipe), *Lekker*, *Vibe Mzansi*. The name still needs a CIPC
trademark search before launch.

## 3. How creators get paid, and the honest economics

### The model

1. Local businesses buy **sponsored clips** in the feed (one slot every six
   clips), priced per 1,000 impressions (CPM).
2. Each month, **55% of ad revenue** goes into a creator pool. That is the
   same share YouTube gives its partners.
3. Sponsors, telcos and public programmes can **top up** the pool.
4. The pool is split by **paid views**: real views (watched for at least 3
   seconds, not the creator's own, one per person per day) on clips that have
   passed 1,000 views.

The exact rules are in code (`clips/monetisation.py`), have automated tests,
and can be published. Creators can check the maths for themselves.

### What ads alone can pay

South African ad rates are low by global standards. YouTube CPMs in SA run
about **R8.50 to R54 per 1,000** ad views
([Briefly](https://briefly.co.za/facts-lifehacks/services/122563-how-youtube-pay-south-africa-examples/)),
and Meta's averaged about **$2.53**
([Superads](https://www.superads.ai/facebook-ads-costs/cpm-cost-per-mille/south-africa)).

| Per 1,000 clip views | Assumption | Rand |
| --- | --- | --- |
| Ad impressions | 1 ad every 6 clips | 167 |
| Ad revenue | R30 CPM | R5.00 |
| Creator pool from ads | 55% | **≈ R2.75** |

The MVP's demo data reproduces this: **R3.16 per 1,000 paid views** from ads
alone.

That is real money, but it isn't yet enough. A creator with 100,000 paid views
a month would earn about **R300**. Promising more without saying where the
money comes from would repeat the frustration creators already feel.
**Closing this gap is the core of the ask in section 5.**

### Closing the gap

| Lever | Effect |
| --- | --- |
| **Mzansi Creator Fund top-up** (see the ask) | Brings the rate to a published target, for example **R20 per 1,000 paid views** |
| Premium ad formats: branded challenges, sponsored sounds, local brand takeovers | Much higher CPMs than standard feed ads |
| B-BBEE Enterprise & Supplier Development spend directed to creator payouts | Corporates already have to spend this; youth creators are a natural recipient |
| Fan gifts and tips through PayShap (roadmap) | Creator keeps 80%. Fees are low because PayShap is a local rail ([Stitch](https://stitch.money/blog/real-time-payments-in-south-africa-the-state-of-payshap-in-2026)) |
| Brand-deal marketplace (roadmap) | Matches local SMEs with local creators |
| Low delivery costs: free peering at NAPAfrica in Johannesburg, Cape Town and Durban ([Teraco](https://www.teraco.co.za/news/napafrica-internet-exchange-achieves-5tbps-traffic-milestone-driving-africas-digital-transformation/)) | Keeps more revenue for creators instead of bandwidth bills |

### Size of the top-up needed to reach R20 per 1,000 paid views

Assuming ads cover about R3 per 1,000 paid views, the fund covers about R17:

| Stage | Paid views per month | From ads | Fund top-up per month | Fund top-up per year |
| --- | --- | --- | --- | --- |
| Pilot (≈ 500 creators) | 20 million | R60,000 | R340,000 | **≈ R4.1 million** |
| Growth | 200 million | R600,000 | R3.4 million | ≈ R41 million |
| National scale | 1 billion | R3 million | R17 million | ≈ R204 million |

As the audience grows, ad targeting and premium formats should raise
ad revenue per view and shrink the top-up. The aim is for ads to carry the
programme on their own. The fund is a bridge, not a permanent subsidy. For
scale: the Competition Commission's digital platforms inquiry secured a
**R688 million** media support package from Google and YouTube, and
monetisation commitments from Meta, YouTube, TikTok and X
([ACTS](https://acts.co.za/news/blog/2025/11/competition-commission-mdpmi-final-report)).
Remedies like this show that money for local digital content can be
mobilised.

## 4. Being realistic about "replacing TikTok"

Shaya should not try to replace TikTok overnight, and government should not
ban or restrict foreign platforms to help it. Social apps live on network
effects, and audiences go where their friends and favourite creators are.
The realistic path:

1. **Win creators first.** If creators are paid on Shaya and not elsewhere,
   they will post here first and cross-post to TikTok. Audiences follow
   creators.
2. **Win on local value TikTok can't match quickly**: getting paid in Rands,
   zero-rated data, local languages, local brands, and local moderation that
   understands context.
3. **Stay credible**: publish the payout rules, the monthly pool and the rate
   per 1,000 views.

If TikTok does open Creator Rewards in South Africa, that is a win for
creators. Shaya would then compete on everything else in that list.

### Key risks

| Risk | Mitigation |
| --- | --- |
| Not enough viewers | Creator-first launch, pilot cohort, WhatsApp sharing, zero-rating |
| Fake views and view farms | Watch-time rule, per-viewer de-duplication and a verified-creator requirement (built). Device attestation and anomaly detection come next |
| Moderation cost and harmful content | Human review queue (built), FPB registration, clear community rules, trusted-flagger partnerships |
| Child safety | Age gate (built), no pay for minors (built), parental consent flow for 13–17, Information Regulator guidance |
| Music rights | Licences with SAMRO, CAPASSO and SAMPRA before launching a sounds library |
| Funding running out | Fund commitments tied to milestones, published rate, ads designed to take over from the fund |

## 5. The ask

We are asking the Ministry to help with the things a startup can't do alone:

1. **Convene the mobile networks** (Vodacom, MTN, Telkom, Cell C) on
   zero-rated or discounted data for Shaya's data-saver streams. This has
   been done before for education and public-service sites.
2. **Co-found a Mzansi Creator Fund** with private partners: about
   **R4 million for a 12-month, 500-creator pilot**. It can be matched by
   corporate ESD spend, the MICT SETA, the NYDA and platform remedy funds.
   Payouts are published monthly.
3. **Direct a share of government's digital advertising** (GCIS and public
   campaigns) to local platforms, starting with public-service messages on
   Shaya.
4. **Smooth the regulatory path**: introductions to the FPB and the
   Information Regulator so that compliance is built in from day one.
5. **Endorse the pilot** as part of the Department's digital economy and
   youth employment work.

## 6. Roadmap

| Phase | Timing | Deliverables |
| --- | --- | --- |
| 0. MVP | Done | Web app: feed, upload, social features, data saver, ads, monthly pay engine, creator studio, moderation queue, tests |
| 1. Production build | Months 1–3 | Android app first (most SA phones are Android), then iOS. Transcoding pipeline and CDN in SA data centres, live PayShap payouts through a bank or payments provider, KYC ID verification, FPB registration, POPIA impact assessment |
| 2. Pilot | Months 4–9 | 500 creators across all 9 provinces and all 12 languages, zero-rating with at least one network, first local advertisers, monthly public payout report |
| 3. Launch | Months 10–12 | Public launch, fan gifts via PayShap, brand marketplace, duets and remixes, licensed sounds library, recommendation model trained on local data |

## 7. Success measures for the pilot

* Share of pilot creators paid each month, and the median monthly payout
* Rate per 1,000 paid views, published monthly, against the R20 target
* Monthly active viewers, and their split across provinces and languages
* Share of watch time on zero-rated data
* Time to resolve a moderation report, and the share of reports actioned
* Ad revenue as a share of the creator pool (should rise each month)

---

*Prepared by the Shaya team. Figures marked as assumptions are estimates to be
replaced with pilot data. Sources are linked inline.*
