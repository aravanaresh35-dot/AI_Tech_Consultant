#!/usr/bin/env python3
"""Generates the OFFLINE demo help-center used by Task 1 (data/demo_site).

The articles describe a FICTIONAL product ("Directory Platform"). They are original fixtures written
for this project; they are NOT real Brilliant Directories documentation. Use CRAWL_SOURCE=live for the real site.
"""
import base64
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "task1-knowledge-brain" / "data" / "demo_site"
HOST = "https://demo.example"

# 1x1 PNG used as a stand-in screenshot
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

ARTICLES = [
 ("member-login", "How to enable the member login page", "2026-03-02",
  ["Members can sign in from a dedicated login page. Open Settings, then Members, then Login Page, and switch on Enable Login Page.",
   "After saving, a Login link appears in the website header. Use the Header Menu editor to move or hide it.",
   "If members forget their password, the Forgot Password link sends a reset email using the Password Reset email template."],
  ("Members settings screen", "The Login Page toggle inside Settings > Members.")),
 ("membership-plans", "Creating and pricing membership plans", "2026-03-05",
  ["Go to Billing, then Membership Plans, and click Add Plan. Enter a plan name, a price, and a billing period (monthly, quarterly or yearly).",
   "Each plan controls how many listings a member can publish and whether the member can appear in Featured results.",
   "Changing the price of an existing plan only affects new subscribers. Current subscribers keep their old price until they change plans."], None),
 ("payment-gateway", "Connecting a payment gateway", "2026-03-09",
  ["Payments are handled through Stripe or PayPal. Open Billing, then Payment Gateways, choose a provider and paste your API credentials.",
   "Use the Test Mode switch to run a sandbox payment before going live.",
   "Refunds are issued from the payment provider dashboard. The platform does not process refunds itself."], None),
 ("custom-fields", "Adding custom profile fields", "2026-03-12",
  ["Custom fields let you collect extra information on member profiles, such as license number or service area.",
   "Open Settings, then Profile Fields, and click Add Field. Choose a type: text, dropdown, checkbox or file upload.",
   "Fields can be marked required and can be shown or hidden on the public profile page."], None),
 ("search-results", "Customizing the search results page", "2026-03-15",
  ["The search results page can show listings as a grid, a list, or on a map. Change the layout under Design, then Search Results.",
   "Sorting options include Newest, Alphabetical and Featured First. Featured members always appear above regular listings when Featured First is selected.",
   "You can limit the number of results per page between 10 and 50."], None),
 ("email-notifications", "Editing email notification templates", "2026-03-18",
  ["System emails such as Welcome, Password Reset and New Lead use editable templates. Open Settings, then Email Templates.",
   "Templates support placeholders like the member name and site name. Always send yourself a test email after editing a template.",
   "Emails are sent from the address set in Settings, then General. Using a domain you own improves deliverability."], None),
 ("seo-settings", "SEO settings for listings and pages", "2026-03-20",
  ["Each listing and page has a Meta Title and Meta Description under its SEO tab.",
   "The platform generates a sitemap automatically at /sitemap.xml and updates it when listings change.",
   "Use the Redirects tool under Settings, then SEO, to forward old URLs to new ones after a redesign."], None),
 ("import-members", "Importing members from a CSV file", "2026-03-22",
  ["Open Members, then Import. Download the sample CSV to see the required columns: email, first name, last name and plan.",
   "The import accepts up to 5,000 rows per file. Rows with an invalid email address are skipped and listed in the import report.",
   "Imported members receive a Welcome email only if you tick the Send Welcome Email option."], None),
 ("custom-domain", "Using a custom domain", "2026-03-25",
  ["To use your own domain, open Settings, then Domain, and enter the domain name. Then create a CNAME record at your DNS provider pointing to the address shown.",
   "DNS changes can take up to 48 hours. An SSL certificate is issued automatically once the domain resolves."], None),
 ("lead-forms", "Lead forms and lead routing", "2026-03-28",
  ["Visitors can send a lead request to members through a lead form. Enable it under Leads, then Lead Forms.",
   "Leads can be routed to members by category or by location. Members receive a New Lead email for each match.",
   "Lead volume per member can be capped with the Monthly Lead Limit setting on the membership plan."], None),
 ("reviews", "Member reviews and ratings", "2026-04-01",
  ["Visitors can leave a star rating and a written review on a member profile when Reviews are enabled under Settings, then Reviews.",
   "New reviews can require admin approval before they are published. Pending reviews appear under Reviews, then Moderation."], None),
 ("map-view", "Showing listings on a map", "2026-04-03",
  ["The Map View displays listings as pins using the address entered on each profile. Enable it under Design, then Search Results, then Layout.",
   "A map provider API key is required. Paste the key under Settings, then Integrations, then Maps."], None),
 ("user-roles", "Admin users and permission levels", "2026-04-06",
  ["Staff accounts are created under Settings, then Admin Users. Each staff user has one role: Administrator, Editor or Support.",
   "Editors can change content but cannot change billing. Support users can view members and leads but cannot edit settings.",
   "Custom roles with individually selectable permissions are not available."], None),
 ("backups", "Backups and data export", "2026-04-09",
  ["The platform keeps automatic daily backups for 14 days. Contact support to request a restore.",
   "Members and leads can be exported as CSV files from their list pages at any time."], None),
 ("api-access", "API access and webhooks", "2026-04-12",
  ["A read-only REST API is available on the Business plan. Generate a key under Settings, then Integrations, then API.",
   "Webhooks can notify an external URL when a member joins or a lead is created. Webhook delivery is retried up to three times."], None),
 ("announcement-banner", "Adding an announcement banner", "2026-04-14",
  ["A site-wide banner can be switched on under Design, then Banner. Enter a message, a link and a background color.",
   "The banner can be dismissed by visitors and will stay hidden for them until you change the message."], None),
]

REMOVED_NOTE = "removed-demo-article"


def page(slug, title, paras, image):
    body = "".join(f"<p>{html.escape(p)}</p>\n" for p in paras)
    img = ""
    if image:
        alt, cap = image
        img = (f'<figure><img src="/images/{slug}.png" alt="{html.escape(alt)}">'
               f"<figcaption>{html.escape(cap)}</figcaption></figure>\n")
    return (f"<!doctype html><html><head><title>{html.escape(title)} - Demo Help Center</title></head><body>"
            f"<nav>Menu Home Search</nav><main><article><h1>{html.escape(title)}</h1>\n"
            f"<h2>Overview</h2>\n{body}{img}</article></main><footer>Demo Help Center</footer></body></html>")


def main(out: Path = OUT) -> int:
    (out / "kb").mkdir(parents=True, exist_ok=True)
    (out / "images").mkdir(exist_ok=True)
    urls = []
    for slug, title, lastmod, paras, image in ARTICLES:
        (out / "kb" / f"{slug}.html").write_text(page(slug, title, paras, image), encoding="utf-8")
        urls.append((f"{HOST}/kb/{slug}.html", lastmod))
        if image:
            (out / "images" / f"{slug}.png").write_bytes(PNG)
    # one tag page that the crawler must skip, and one broken URL to exercise failure handling
    urls.append((f"{HOST}/tags/login", "2026-04-01"))
    urls.append((f"{HOST}/kb/page-that-does-not-exist.html", "2026-04-01"))
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    xml += [f"<url><loc>{u}</loc><lastmod>{m}</lastmod></url>" for u, m in urls]
    xml.append("</urlset>")
    (out / "sitemap.xml").write_text("\n".join(xml), encoding="utf-8")
    print(f"Wrote {len(ARTICLES)} demo articles to {out}")
    return len(ARTICLES)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT)
