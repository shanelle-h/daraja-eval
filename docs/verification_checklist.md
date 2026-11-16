# Expert verification checklist (do this BEFORE running the eval)

The eval is only as good as its expected answers. I (Claude) drafted them from web sources, not from
your hands-on Daraja experience. Go through each row, confirm or fix `expected` in `tasks/tasks.json`,
then tick the box. Re-run `python selftest.py` after any edit.

| Task | Claim to confirm | Confidence | How to verify | OK |
|---|---|---|---|---|
| T01 | stkCallback `ResultCode` is a JSON **number**; success callbacks have `CallbackMetadata`, failures don't | High | Log a real sandbox callback | [ ] |
| T02 | STK **query** response returns `ResultCode` as a **string**; `ResponseCode "0"` only means the query was accepted | Med-High | One sandbox query call | [ ] |
| T03 | `C2B00012` = invalid account number; validation must be enabled for the shortcode by Safaricom; `ResponseType: "Cancelled"` rejects when validation URL is unreachable | High / High / Med | Daraja C2B Register URL docs page | [ ] |
| T04 | Prod URLs: HTTPS only, no `mpesa`/`safaricom`/`exec`/`cmd`/`sql`/`query` keywords, no ngrok-type testers; prod registration is one-time, fix = delete in Self Services > URL Management then re-register | Med-High | Daraja docs; try the URLs in sandbox. If you doubt option **c** (`/api/exec/`) or **e**, edit the options | [ ] |
| T05 | Same `ResultCode 2001` + same `ResultDesc`: **STK = wrong PIN**, **B2C = invalid initiator** | Med-High | Your own production logs are best evidence | [ ] |
| T06 | B2C sync `ResponseCode 0` = accepted only; final result via ResultURL; 2001 = fix initiator name / SecurityCredential | High | Daraja B2C docs | [ ] |
| T07 | Password = Base64(shortcode + passkey + timestamp); timestamp `YYYYMMDDHHmmss`; phone formats | High (computed by script) | `python -c` recompute | [ ] |
| T08 | DPA 2019 **s.43**; processor to controller **48h where reasonably practicable**; controller to Commissioner **72h from the controller's awareness** | Med-High | Verified 2026-11-07 against the Act text: s.43(1)(a) controller to Commissioner within 72h of becoming aware (where real risk of harm); s.43(3) processor to controller without delay and where reasonably practicable within 48h. Clock starts when the controller is aware of a breach posing real risk of harm (11:30). | [x] |
| T09 | Reg. 26 of the General Regulations 2021: localisation only for "strategic interests of the state" (county revenue/public finance counts; private retail does not); transfers abroad still need safeguards/consent | Medium | Read Reg. 26(2) in the General Regulations PDF | [ ] |
| T10 | C2B **v2** masks MSISDN (e.g. `2547*****126`) | Med-High | Daraja docs / sandbox v2 callback | [ ] |

## Known weak spots (drop or soften a task if you can't confirm it)
- T04 depends on exact keyword rules; if you can't test it in sandbox, remove option c.
- T09 and T08's deadline are interpretive legal calls. If your reading differs, change `expected`; don't leave a disputed answer in.
- A secondary source I found cited the breach duty as "section 62"; the ODPC's own determinations cite **section 43**. T08 treats 43 as correct.

## Sources (all public)
- Daraja docs mirrors / SDK docs: see `sources` per task in `tasks/tasks.json`
- Data Protection Act 2019: https://www.odpc.go.ke/wp-content/uploads/2024/02/TheDataProtectionAct__No24of2019.pdf
- Data Protection (General) Regulations 2021: https://www.odpc.go.ke/wp-content/uploads/2024/03/THE-DATA-PROTECTION-GENERAL-REGULATIONS-2021-1.pdf