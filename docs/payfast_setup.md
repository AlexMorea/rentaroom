# Going live with PayFast

Payments are fully built and tested in code. They switch on as soon as the
PayFast keys are added. Until then the app shows "Online payments open soon"
and nobody can be charged.

## 1. Open the merchant account (do this first, it takes a few days)
1. Sign up at payfast.io as a **business** (4You (Pty) Ltd), not an individual.
2. Upload the company registration documents, director ID and the business
   bank account confirmation. PayFast verifies these, usually within a few
   working days.
3. In the PayFast dashboard → **Settings → Developer settings**:
   - set a **passphrase** (long and random, stored in a password manager);
   - note the **Merchant ID** and **Merchant Key**;
   - make sure **recurring billing / subscriptions** is enabled on the account
     (ask PayFast support if the option is missing).

## 2. Test in sandbox first
1. Log in at sandbox.payfast.co.za with the same email to get sandbox
   credentials and set a sandbox passphrase.
2. In Render → the web service → **Environment**, add:
   ```
   PAYFAST_MERCHANT_ID=<sandbox id>
   PAYFAST_MERCHANT_KEY=<sandbox key>
   PAYFAST_PASSPHRASE=<sandbox passphrase>
   PAYFAST_SANDBOX=1
   ```
3. Use a test landlord (not founding, or one whose trial has been ended in
   admin) and buy Pro monthly. Check in **Django admin → Billing → Payments**
   that the payment turns **Complete** within a minute and the membership shows
   Pro with a "paid until" date.
4. Cancel the subscription from the Plans page and confirm "auto renew" goes off.
5. With `BOOSTS_ENABLED=1`, buy a boost and check the room shows ⭐ Featured
   at the top of search. Then set `BOOSTS_ENABLED=0` again until launch.

> Worth checking in sandbox specifically: the **second (renewal) payment**
> of a subscription. The code expects PayFast to send it with the original
> payment reference, which is how their subscriptions work, but confirm it
> extends "paid until" by a month. If it doesn't, tell your developer
> before going live.

## 3. Go live
Replace the three values with the **live** ones and set `PAYFAST_SANDBOX=0`.
Do this before tenant launch. Founding landlords aren't billed until
1 May 2027 in any case.

## 4. Tenant launch day
Set `BOOSTS_ENABLED=1` in Render. That's the only switch.

## Where the money shows up
- **Django admin → Billing → Payments**: every payment, with PayFast's
  reference and fee; the page title shows the total collected.
- **Django admin → Billing → Boosts**: every boost and whether it's live.
- **Django admin → Memberships**: each landlord's plan, "paid until" date and
  founding discount. The **"Grant 1 month of Pro"** action is for goodwill or
  fixing a payment by hand.
