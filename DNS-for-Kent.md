Hi Kent, could you add this DNS record for pawkit.sg? It points cs360.pawkit.sg at the new internal CS360 page.

| Type  | Name / Host | Value / Points to     | TTL     |
|-------|-------------|-----------------------|---------|
| CNAME | cs360       | pawslyops.github.io   | default |

- If the DNS is on Cloudflare, set it to "DNS only" (grey cloud), not proxied, so GitHub can issue the HTTPS certificate.
- Nothing else on pawkit.sg changes.
- Once it's in, the page opens at https://cs360.pawkit.sg (HTTPS can take up to an hour after the record goes live).

Thanks!
