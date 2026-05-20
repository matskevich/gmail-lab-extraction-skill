# Live Gmail Boundaries

Current native-attachment extraction should use Gmail API first when OAuth is available. Browser/CDP is the fallback for UI-specific rescue and inline Gmail assets.

Before a live run:

```bash
./scripts/doctor.sh
```

If CDP is down, live Gmail scripts will need a Chrome clone. The runner can start one, but stale login state can still block extraction.

Prefer a persistent CDP profile when browser fallback is needed:

```bash
skills/gmail-browser-attachments/scripts/start_chrome_cdp_profile.sh
```

If smoke reports `gmail_not_authenticated`, the browser lane has not reached mailbox evidence. Diagnose with:

```bash
gmail-lab diagnose-gmail-acquisition
```

Known caveats:

- Gmail attachment controls can hydrate late; historical partial-ready messages need regression coverage.
- A narrow query can produce false negatives; a broader order-id query can recover the same old thread.
- A broad query can match the wrong conversation; always use a row needle.
- Provider portals with username/password/2FA/captcha are out of scope unless a provider adapter explicitly supports the flow.

For completeness claims, require:

1. discovery run
2. acquisition run
3. manifest review
4. regression summary for historical cases
