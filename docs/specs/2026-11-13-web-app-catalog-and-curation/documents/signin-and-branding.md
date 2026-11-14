# Sign-in and branding: themed managed login, our own page, or both

Research for Plan 8 PLAN3. Read 2026-11-14. Repo: `plan8/ux-review` at `6853570` (origin/main). No files in the repo changed.

The user asked for "a complete look of our own that another adopter can rebrand easily" and to "use our own page whenever possible, like the cognito signin should be ourselves or at least themed".

## Recommendation

**Themed managed login, generated at synth from a small `brand:` block in `archive.yaml`. The same block also themes the app at build time.** Don't build our own sign-in page now.

Why:

- **It keeps what is already settled.** The CLI and MCP must use managed login whatever we do (handoff, 2026-11-13 row for Plans 6 and 9). Our own page would give an archive two sign-in screens, and a reader signed in on one would still be asked to sign in again on the other.
- **It covers nearly all of the look.** Managed login takes our logo, favicon, colours, light, dark or adaptive mode, background and header, all from CloudFormation, per app client. What it can't change is the font, the wording on the page, and the AWS domain in the address bar.
- **It keeps passwords off our origin.** The app renders text that contributors submit (dataset titles, descriptions). A password form on our origin puts every typed password one XSS bug away from being stolen. Managed login is a different origin.
- **It is the only path that fits ORCID and university SSO later.** Federation only works by redirecting through `/oauth2/authorize`. With managed login that comes for free: the IdP buttons appear on the themed page. With our own page we would build that redirect and callback ourselves, alongside the password flow.
- **It is small.** About 60 lines of CDK, one pydantic model, one Vite plugin change. No new auth code in the browser.

Our own page is worth reopening if Cognito ever ships a way to customise the managed login text or fonts, or if the custom-domain follow-up still leaves sign-in feeling foreign. Even then, the CLI keeps using managed login.

## Comparison

| | Themed managed login | Our own page | Both (own page for web, managed login for CLI/MCP) |
|---|---|---|---|
| **What the reader sees** | Cognito's layout with our logo, favicon, colours, header and background, in light, dark or adaptive mode. AWS's own wording (12 languages via `lang`) and AWS's font. Address bar: `archive-<stage>-<acct>.auth.<region>.amazoncognito.com` until a custom domain exists. | Our page, our font and words, on the archive's own domain. | Our page in the browser. A themed Cognito page whenever the CLI or MCP opens the browser. Two different sign-in screens for one archive. |
| **Effort** | Small. Write a settings document plus assets from config at synth. Same branding on the `web` and `cli` clients. No change to `packages/web/src/auth.ts`. | Large. An SRP library (or plain-password flow), screens for sign-in, `NEW_PASSWORD_REQUIRED`, forgot password (`ForgotPassword` / `ConfirmForgotPassword`), and MFA or passkeys if ever enabled. A token store to replace oidc-client-ts's code flow. Tests for every challenge. | Large (our own page) plus small (themed managed login), and both kept looking alike. |
| **What it breaks** | Nothing. PKCE code flow, `/auth/callback`, CLI and MCP unchanged. | The web app leaves the code-plus-PKCE flow the handoff settled. The web client needs `ALLOW_USER_SRP_AUTH` (or `USER_PASSWORD_AUTH`/`USER_AUTH`). There's no shared session with managed login, so the CLI asks a signed-in reader to sign in again. Managed login's one-hour session cookie never gets set from our page. | Same as our own page. |
| **Security** | The password is typed only on Cognito's origin. Cognito handles brute-force throttling. A WAF web ACL can attach to managed login. Tokens still go to the app via code plus PKCE. | Passwords pass through our JS on an origin that renders contributor-submitted content. Any XSS can read them. `InitiateAuth` is called directly with a public client id, so we answer for lockout UX and error-message leaks (`PreventUserExistenceErrors`). The attack surface is our code, not Cognito's. | Worst of both: two flows to secure and keep in step. |
| **Fit with later ORCID / university SSO** | Native. Add the IdP to the pool and the app clients; its button appears on the themed page (styled by `idpButton` and `authMethodOrder`). | Federation still needs a redirect through `/oauth2/authorize?identity_provider=…` and the code-flow callback, so the page ends up running two flows: password through the API, and SSO through OAuth. | Same as our own page. |

## 1. Themed managed login (newer version)

### What can be branded (1 console-guide page, 2 CloudFormation pages, 1 developer-guide page)

From the branding editor guide (https://docs.aws.amazon.com/cognito/latest/developerguide/managed-login-brandingeditor.html) and the `AWS::Cognito::ManagedLoginBranding` reference (https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cognito-managedloginbranding.html):

- **Display mode:** light, dark or adaptive. `categories.global.colorSchemeMode`: `LIGHT`, `DARK` or `DYNAMIC`. "When you choose a browser-adaptive mode, you can choose different colors and logo images for light and dark mode."
- **Colours,** for each of light and dark mode, in `RRGGBBAA` hex (e.g. `"0972d3ff"`). They cover: primary button (default, hover, active), links, focus ring, inputs, labels, option controls, dropdowns, dividers, alerts and status indicators, form container, page background, page text (heading, body, description), header and footer, and IdP buttons.
- **Shape and layout:** border radius per component, spacing density, form position (horizontal and vertical), form logo position (`IN`/`OUT`, `TOP`, `CENTER`/`START`/…), header and footer on or off, header logo position.
- **Images (`Assets`, at most 40):**
  - favicon: `FAVICON_ICO` (ico) or `FAVICON_SVG` (svg)
  - logos: `FORM_LOGO`, `PAGE_HEADER_LOGO`, `PAGE_FOOTER_LOGO` (png, svg, jpeg)
  - backgrounds: `PAGE_BACKGROUND`, `FORM_BACKGROUND`, `PAGE_HEADER_BACKGROUND`, `PAGE_FOOTER_BACKGROUND`
  - per-method graphics: `PASSWORD_GRAPHIC`, `PASSKEY_GRAPHIC`, `EMAIL_GRAPHIC`, …
  - `IDP_BUTTON_ICON` (ico, svg)

  Each asset has a `ColorMode` (`LIGHT`, `DARK` or `DYNAMIC`) and an `Extension` (`ICO`, `JPEG`, `PNG`, `SVG` or `WEBP`). SVGs are limited to an allow-list of elements and attributes.
- **Not brandable:**
  - **Page text.** "You can't modify or localize text in the branding editor." The only lever is the `lang` query parameter (12 languages). The reserved `instructions` component "is not currently implemented".
  - **Fonts.** No font or typography setting appears in the editor's component list or in the full CloudFormation example settings (2 sources). I found no statement either way, so treat custom fonts as unavailable.
  - **The domain** (see below).

### Generating the settings at synth (rests on: the CloudFormation reference plus the API guidance)

Yes. `Settings` is a plain JSON property and `Assets` takes base64 `Bytes`, so the CDK app can build both from config.

- Cognito "preserves existing style settings that you don't specify" and "ignores any values in your `Settings` object that aren't in the schema". A short settings document is valid, and the rest stay at Cognito's defaults. That is by documentation; I didn't test it.
- `useCognitoProvidedValues: true` (what `auth.ts` sets today) must be dropped: "When you specify `true` for this option, you must also omit values for `Settings` and `Assets`."
- AWS's suggested workflow is to call `DescribeManagedLoginBrandingByClient` with `ReturnMergedResources: true` and edit the result. For us, a small hand-written template is cleaner. Take the primary colour and derive the hover and active shades, the text-on-primary colour (black or white by contrast), the link colour and the focus ring.
- One caveat: whether each setting key applies can only be confirmed by deploying and looking. That check belongs in the plan's walk.

Minimal shape (illustrative, not tested):

```json
{
  "categories": { "global": { "colorSchemeMode": "LIGHT", "pageHeader": { "enabled": false } } },
  "componentClasses": {
    "focusState": { "lightMode": { "borderColor": "0b5cadff" } },
    "link": { "lightMode": { "defaults": { "textColor": "0b5cadff" }, "hover": { "textColor": "08447fff" } } }
  },
  "components": {
    "primaryButton": { "lightMode": { "defaults": { "backgroundColor": "0b5cadff", "textColor": "ffffffff" },
                                       "hover":    { "backgroundColor": "08447fff", "textColor": "ffffffff" },
                                       "active":   { "backgroundColor": "063361ff", "textColor": "ffffffff" } } },
    "form": { "logo": { "enabled": true, "formInclusion": "IN", "location": "CENTER", "position": "TOP" } },
    "favicon": { "enabledTypes": ["SVG"] }
  }
}
```

Assets: `[{ Category: "FORM_LOGO", ColorMode: "LIGHT", Extension: "SVG", Bytes: <base64> }, { Category: "FAVICON_SVG", … }]`.

### Limits

- **Per asset:** `Bytes` holds at most 1,000,000 base64 characters (about 730 KB raw).
- **Per request:** 2 MB. "Your branding settings might exceed 2MB… separate it into multiple requests." That isn't possible in one CloudFormation resource, so keep assets small.
- **Template size:** the bytes are inlined in the CloudFormation template. CDK uploads templates through S3, where the limit is 1 MB. Two copies of a 50 KB SVG (one per client) are fine. Validate the logo size in config, say ≤ 200 KB.
- **The archive config's 4 KB SSM limit** (`research-archive.ts:27`) is not a problem if the config stores paths and colours, never image bytes.
- **Feature plan:** managed login branding needs Essentials or Plus. The repo sets no `featurePlan`, and the CDK default is "`FeaturePlan.ESSENTIALS` for a newly created user pool" (CDK `UserPool` docs). It already works today, since `NEWER_MANAGED_LOGIN` deploys. Essentials keeps the 10,000 MAU free tier (https://aws.amazon.com/cognito/pricing/).
- `ClientId` and `UserPoolId` changes require replacement. The other properties update in place.

### Per app client

Yes. "Each style is linked to an app client until you delete it." Without one, "Managed login isn't available for an app client created with an AWS SDK" (managed-login page; matches the comment in `auth.ts`). Apply the same generated settings and assets to both `WebClient` and `CliClient`. The `client()` helper in `addAppClients` already creates one `CfnManagedLoginBranding` per client, so the change goes in one place.

### What the CLI's sign-in looks like

It looks the same as the web's. The CLI opens `…/oauth2/authorize?client_id=<cli>&…` in the browser. The page carries the `cli` client's style, which would be identical, then redirects to `localhost:8765`.

Bonus: managed login sets a one-hour `cognito` session cookie. A reader who signed in on the web within the hour gets CLI tokens without typing a password again (managed-login page, "The one-hour managed login and hosted UI session cookie"). Our own page would lose this.

### Is a custom domain needed? (custom-domain page, managed-login page)

Not for the theme. Branding applies to the prefix domain the stack has now (`archive-<stage>-<account>`). The only thing that stays foreign is the address bar, `*.auth.<region>.amazoncognito.com`.

A custom domain (e.g. `auth.archive.example.org`) needs:

- a domain the adopter owns
- an ACM certificate in us-east-1 ("The certificate must be in us-east-1 because the certificate is associated with a distribution in CloudFront")
- a DNS alias
- up to five minutes for the domain to become available

This fits the already-deferred custom-domain follow-up (handoff, 2026-11-13 row for Plan 4). Themed managed login should not wait for it.

### Related brandable surface: the invitation email

The temporary-password email an invited user gets comes from the pool's `userInvitation` (`emailSubject`, `emailBody` with `{username}` and `{####}`). Today that is Cognito's default text. It is part of "a complete look" and can be generated from the same `brand.name` plus the site URL. I didn't fetch a doc for this; it rests on the CDK `UserPool` API as I know it, so verify it in the plan.

## 2. Our own sign-in page

### What it takes (developer-guide authentication flows page, `InitiateAuth` API reference)

- **App client flows.** Enable `ALLOW_USER_SRP_AUTH` (password proof, no plaintext to Cognito) or `ALLOW_USER_PASSWORD_AUTH` on the web client, or `ALLOW_USER_AUTH` for choice-based sign-in. With choice-based, the pool also needs `SignInPolicy.AllowedFirstAuthFactors` (`PASSWORD`, `EMAIL_OTP`, `WEB_AUTHN`).
- **SRP.** "The low-level AWS SDKs … don't compute the SRP values for you." That means Amplify or another SRP library in the bundle. With SRP, "your application is the only entity that processes the passwords that users enter". That is exactly the point: the password lives in our page's JS.
- **Invited users.** An invited user's first sign-in returns the `NEW_PASSWORD_REQUIRED` challenge: "Respond to this challenge with NEW_PASSWORD and any required attributes". That is a second screen, and the session times out.
- **Other screens.** Forgot password needs `ForgotPassword` and `ConfirmForgotPassword` screens, because `AccountRecovery.EMAIL_ONLY` is set. MFA isn't configured today. Adding it, or passkeys, means more challenge screens (`SOFTWARE_TOKEN_MFA`, `EMAIL_OTP`, `WEB_AUTHN`, `MFA_SETUP`, `SELECT_CHALLENGE`) and passkey registration (`StartWebAuthnRegistration`/`CompleteWebAuthnRegistration`).
- **Tokens.** `InitiateAuth` returns ID, access and refresh tokens directly. The app's rule (drop the refresh token, keep tokens in memory) still holds, but oidc-client-ts's redirect flow is gone. We'd write a token store and expiry handling.
- **Rate limits.** `UserAuthentication` has a regional quota (120 RPS default, adjustable), shared across the account's pools. Cognito throttles failed attempts, but lockout messaging and user-existence leaks (`PreventUserExistenceErrors`) become our job.

### What it breaks or changes

- **PKCE code flow.** The web leaves it, even though the handoff settled code plus PKCE for both clients. The hosted endpoints still exist because the CLI needs them. Two flows on one pool, each to secure and test.
- **CLI and MCP.** They still need managed login (settled). There's no shared session, so readers meet a second, different sign-in page and sign in twice.
- **ORCID and university SSO.** "Federated authentication doesn't make use of any of the authentication flows that you can build into your app client… Federated sign-in happens when users select their IdP in managed login or your application invokes a session with a redirect to their IdP sign-in page." Our own page can add an "ORCID" button that sends the reader to `/oauth2/authorize?identity_provider=ORCID` ("it silently redirects your user to the sign-in page for that identity provider"). But that requires keeping the OAuth callback and code exchange, so the web app ends up with both flows. University SAML with many institutions wants managed login's "Domain search input" (match email to an IdP), which we'd rebuild ourselves.
- **Security posture.** Passwords are typed into an origin that also renders contributor-submitted metadata, so XSS becomes credential theft rather than one-hour token theft. A CSP helps but doesn't remove the risk. WAF on managed login (supported since 2025-06) wouldn't cover our page. We'd put WAF on the pool's API endpoint or on CloudFront instead.

### Newer Cognito features (Cognito document history, read to 2026-11-05)

- **Choice-based sign-in (`USER_AUTH`), passkeys and email OTP** (Essentials). They make our own page bigger, not smaller: each is another challenge to render. Managed login renders them for free ("passkey sign-in isn't available in the classic hosted UI", so the newer managed login has it).
- **Embedded login components:** none from Cognito. The only embeddable UI is Amplify's open-source `Authenticator`, which brings Amplify's look and a large dependency. It doesn't give us our own look for less than writing the screens.
- **Recent and relevant, but don't change the trade-off:**
  - session management for user pools (2026-11-05): list and revoke sessions
  - dynamic client registration (2026-10-02): "Applications and AI agents can now register their own app clients… through the registration endpoint of your user pool domain". Worth a note for the MCP client: it still goes through managed login, which strengthens the case for theming it.
  - WAF on managed login (2025-06)
  - the `prompt` parameter (2025-05)
- **Still true:** "Managed login doesn't support custom authentication with custom authentication challenge Lambda triggers." Not relevant to us.

## 3. Rebranding the app itself

### What exists

- `packages/web/vite.config.ts` already reads `archive.yaml` (or `ARCHIVE_CONFIG`) at build time and injects `__PUBLISHER__`.
- `styles.css` already themes through CSS custom properties: `--text`, `--muted`, `--line`, `--surface`, `--accent`, `--danger`, `--radius`, and the font is `system-ui`.
- `index.html` has a fixed `<title>research-in-a-box</title>`.
- Dataset pages from `packages/backend/src/archive_backend/pages.py` load `/app.js`, which adds the hashed stylesheet, so anything in the CSS reaches them too.
- CI builds the web bundle on every deploy (handoff, 2026-11-14 row for Plan 10a).

### Recommendation: build time, one `brand:` block, two consumers

```yaml
brand:
  name: Invented Research Cooperative Archive   # default: publisher
  logo: brand/logo.svg                           # svg or png, ≤ 200 KB; path relative to archive.yaml
  favicon: brand/favicon.svg                     # optional; default: logo if svg
  primaryColor: "#0b5cad"                         # becomes --accent and Cognito's primary
  font: "Source Sans 3, system-ui, sans-serif"   # optional CSS font-family stack, app only
```

- **Contract.** A strict `Brand` model in `archive_contract/config.py`:
  - hex pattern for `primaryColor`
  - allowed extensions for `logo` and `favicon`
  - file exists, size within limit
  - all fields optional, with today's look as the default

  The config stays a few hundred bytes, well under the 4 KB SSM limit.
- **App (Vite plugin, build time).**
  - emit `:root { --accent: …; --accent-hover: …; --on-accent: …; font-family: … }` after `styles.css`
  - copy the logo and favicon into `dist/brand/`
  - write `<title>` and `<link rel="icon">` into `index.html`
  - inject `__BRAND__` (name, logo URL) for the header

  No extra request, no flash of unthemed content, and it works on the static dataset pages. A woff2 font file is possible later as an optional `fontFile`. Keep v1 to a system font stack, since managed login can't match a custom font anyway.
- **Managed login (CDK, synth time).** `infra/src/config.ts` reads the same `brand`. A small `brandingSettings(brand)` function builds the settings JSON (primary colour and derived shades, link, focus ring, form logo on) and the `Assets` (base64 `FORM_LOGO` and `FAVICON_SVG`/`ICO`). `Auth.addAppClients` passes both to each client's `CfnManagedLoginBranding` instead of `useCognitoProvidedValues`. Same input, same colours, same logo on both surfaces.
- **Shared derivation.** Write the hover, active and text-on-primary maths once in TypeScript (a tiny module both Vite and CDK import, or two ten-line copies with a test). Then the app's button and Cognito's button match exactly.

### Why not a runtime `/theme.json` beside `/auth-config.json`

It would allow rebranding without a rebuild, but every deploy already rebuilds in CI, so that buys an adopter nothing. And it costs:

- a fetch before first paint (a flash of the default theme)
- a second source of truth from what Cognito got at synth
- no help for the `<title>` and favicon in the static `index.html` and dataset pages

Put the brand into `/auth-config.json`-style runtime data only if a "change theme without redeploy" need ever appears.

## Sources and how many cases each rests on

| Claim | Source | Cases |
|---|---|---|
| Brandable components, display modes, no text editing, `lang` only | https://docs.aws.amazon.com/cognito/latest/developerguide/managed-login-brandingeditor.html | 1 page |
| Asset categories and file types, 2 MB request, partial updates keep settings | same page; https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cognito-managedloginbranding.html | 2 pages agree |
| Asset `Bytes` ≤ 1,000,000; `ColorMode` LIGHT/DARK/DYNAMIC; `Extension` ICO/JPEG/PNG/SVG/WEBP; ≤ 40 assets | https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-cognito-managedloginbranding-assettype.html and the resource page | 2 pages |
| `useCognitoProvidedValues` excludes `Settings`/`Assets`; reserved unimplemented components | CloudFormation resource page | 1 page |
| No font setting | absent from the editor's component list and the full CloudFormation example | 2 pages, by absence (unconfirmed) |
| Per-client style; SDK-created client has no managed login without a style; one-hour session cookie; localization needs Essentials/Plus; passkeys only in newer managed login | https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-managed-login.html | 1 page (per-client also in the CloudFormation page) |
| CDK default feature plan is Essentials for new pools | https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cognito.UserPool.html (search snippet) | 1 source |
| Essentials free tier 10,000 MAU | https://aws.amazon.com/cognito/pricing/ | 1 page |
| Custom domain needs an ACM cert in us-east-1 | https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-add-custom-domain.html | 1 page |
| SRP/password/`USER_AUTH` setup; SDKs don't compute SRP; federation bypasses app-client flows | https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-authentication-flow-methods.html | 1 page |
| `NEW_PASSWORD_REQUIRED` response shape | https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_InitiateAuth.html | 1 page |
| `identity_provider` on `/oauth2/authorize` silently redirects to the IdP | https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html | 1 page |
| `UserAuthentication` and `UserFederation` quota categories | https://docs.aws.amazon.com/cognito/latest/developerguide/quotas.html | 1 page |
| 2025–2026 features (session management, DCR, WAF, passkeys); no embedded component | https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-document-history.html | 1 page, by absence for the component |
| Repo facts (clients, branding, config, Vite, CSS variables, 4 KB check, dataset pages load `/app.js`) | `packages/infra/src/auth.ts`, `web.ts`, `research-archive.ts:27`, `packages/web/vite.config.ts`, `src/styles.css`, `index.html`, `packages/backend/src/archive_backend/pages.py:28`, `docs/planning-handoff.md` | read directly |

Not verified by deploy: which minimal settings keys take effect, and how the page looks with them. The walk should check both. The `userInvitation` email settings rest on CDK API knowledge, not a fetched page.
