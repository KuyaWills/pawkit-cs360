#!/bin/zsh
# Auto-switch the site to its custom domain once DNS points at GitHub Pages.
# Called at the end of every 5-minute run (run_refresh.sh). Safe to run any number of times.
#   waiting  -> the DNS record is not there (or points elsewhere): do nothing
#   switched -> custom domain set on GitHub Pages; waiting for GitHub's HTTPS certificate
#   done     -> HTTPS enforced; nothing left to do
# Test hooks (no changes are made when DOMAIN_WATCH_DRY is set):
#   DOMAIN_WATCH_DRY=1  DOMAIN_WATCH_STATE=<file>  DOMAIN_WATCH_FAKE_DNS=<answer>  DOMAIN_WATCH_FAKE_PAGES="<cname> <cert> <enforced>"
set -u
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd "${0:A:h}"

DOMAIN="cs360.pawkit.sg"
TARGET="pawslyops.github.io"
REPO="pawslyOps/pawkit-cs360"
ZONE="pawkit.sg"
STATE_FILE="${DOMAIN_WATCH_STATE:-.domain-state}"
NOTE_FILE="${STATE_FILE}.note"
DRY="${DOMAIN_WATCH_DRY:-}"

say() { echo "$(date '+%Y-%m-%d %H:%M') $*"; }
# log a line only when it differs from the last one, so the log stays short
note() { [ "$(cat "$NOTE_FILE" 2>/dev/null)" = "$*" ] && return 0; say "$*"; [ -z "$DRY" ] && echo "$*" > "$NOTE_FILE"; return 0; }
set_state() { if [ -n "$DRY" ]; then echo "  DRY-RUN would set state: $1"; else echo "$1" > "$STATE_FILE"; fi }

lookup() {  # $1 = resolver; prints the CNAME target in lower case without the trailing dot
  if [ -n "${DOMAIN_WATCH_FAKE_DNS+x}" ]; then echo "$DOMAIN_WATCH_FAKE_DNS" | tr 'A-Z' 'a-z' | sed 's/\.$//'; return; fi
  dig +short +time=3 +tries=1 CNAME "$DOMAIN" "@$1" 2>/dev/null | head -1 | tr 'A-Z' 'a-z' | sed 's/\.$//'
}
pages_info() {  # prints "<cname> <certificate state> <https enforced>"
  if [ -n "${DOMAIN_WATCH_FAKE_PAGES+x}" ]; then echo "$DOMAIN_WATCH_FAKE_PAGES"; return; fi
  GH_TOKEN=$tok gh api "repos/$REPO/pages" --jq '[(.cname // "none"), (.https_certificate.state // "none"), (.https_enforced | tostring)] | join(" ")' 2>/dev/null
}

state=$(head -1 "$STATE_FILE" 2>/dev/null); state=${state:-waiting}
[ "$state" = done ] && exit 0

if [ "$state" = waiting ]; then
  # the domain's own nameservers are the source of truth (public resolvers can cache "no such record" for an hour);
  # also require one public resolver to see it, so the record is really visible from outside
  ns=""; auth=""
  if [ -z "${DOMAIN_WATCH_FAKE_DNS+x}" ]; then ns=$(dig +short +time=3 +tries=1 NS "$ZONE" @1.1.1.1 2>/dev/null | head -1 | sed 's/\.$//'); fi
  if [ -n "$ns" ] || [ -n "${DOMAIN_WATCH_FAKE_DNS+x}" ]; then auth=$(lookup "${ns:-fake}"); fi
  a=$(lookup 1.1.1.1); b=$(lookup 8.8.8.8)
  if [ "$auth" != "$TARGET" ] || { [ "$a" != "$TARGET" ] && [ "$b" != "$TARGET" ]; }; then
    if [ -z "$auth$a$b" ]; then note "waiting: no DNS record for $DOMAIN yet"
    else note "waiting: $DOMAIN -> nameserver '${auth:-nothing}', public resolvers '${a:-nothing}' / '${b:-nothing}'; expected $TARGET"; fi
    exit 0
  fi
  say "DNS is in place: $DOMAIN -> $TARGET. Switching the site."
  if [ -n "$DRY" ]; then
    echo "  DRY-RUN would: write docs/CNAME ($DOMAIN), commit it, push main as pawslyOps, set the Pages custom domain"
    set_state switched; exit 0
  fi
  tok=$(gh auth token -h github.com -u pawslyOps 2>/dev/null) || { say "could not get the pawslyOps login; will retry next run"; exit 0; }
  # 1) the CNAME file inside the published folder, so a later page deploy keeps the domain
  if [ "$(cat docs/CNAME 2>/dev/null)" != "$DOMAIN" ]; then
    printf '%s\n' "$DOMAIN" > docs/CNAME
    git add docs/CNAME
    if git ls-files --error-unmatch CNAME.pending >/dev/null 2>&1; then
      git rm -q -f CNAME.pending
      git commit -q -m "Switch the site to $DOMAIN (DNS is in place)" -- docs/CNAME CNAME.pending
    else
      git commit -q -m "Switch the site to $DOMAIN (DNS is in place)" -- docs/CNAME
    fi
  fi
  if [ -n "$(git log origin/main..main --oneline 2>/dev/null)" ]; then
    GH_TOKEN=$tok GIT_TERMINAL_PROMPT=0 git push -q origin main 2>/dev/null \
      || say "warning: could not push the CNAME file; the Pages setting below still applies"
  fi
  # 2) the Pages setting itself
  if out=$(GH_TOKEN=$tok gh api -X PUT "repos/$REPO/pages" -f cname="$DOMAIN" 2>&1); then
    set_state switched
    say "custom domain set on GitHub Pages; waiting for the HTTPS certificate (usually minutes, up to an hour)"
  else
    say "GitHub refused the custom domain (${out[1,160]}); will retry next run"
  fi
  exit 0
fi

if [ "$state" = switched ]; then
  tok=""
  if [ -z "${DOMAIN_WATCH_FAKE_PAGES+x}" ]; then
    tok=$(gh auth token -h github.com -u pawslyOps 2>/dev/null) || exit 0
  fi
  info=$(pages_info) || exit 0
  [ -z "$info" ] && exit 0
  cname=${info%% *}; rest=${info#* }; cert=${rest%% *}; enforced=${rest##* }
  if [ "$cname" != "$DOMAIN" ]; then
    say "the custom domain is missing on GitHub Pages (found '$cname'); setting it again"
    [ -n "$DRY" ] && { echo "  DRY-RUN would: set the Pages custom domain again"; exit 0; }
    GH_TOKEN=$tok gh api -X PUT "repos/$REPO/pages" -f cname="$DOMAIN" >/dev/null 2>&1
    exit 0
  fi
  if [ "$enforced" = true ]; then
    set_state done; say "HTTPS is enforced. https://$DOMAIN is live."; exit 0
  fi
  tls_ok=no
  if [ "$cert" != approved ] && [ -z "$DRY" ]; then
    curl -s -m 10 -o /dev/null "https://$DOMAIN/" 2>/dev/null && tls_ok=yes   # a valid certificate is already being served
  fi
  if [ "$cert" = approved ] || [ "$tls_ok" = yes ]; then
    [ -n "$DRY" ] && { echo "  DRY-RUN would: enforce HTTPS"; set_state done; exit 0; }
    if GH_TOKEN=$tok gh api -X PUT "repos/$REPO/pages" -F https_enforced=true >/dev/null 2>&1; then
      set_state done; say "certificate ready, HTTPS enforced. https://$DOMAIN is live."
    else
      note "certificate looks ready but GitHub would not enforce HTTPS yet; will retry"
    fi
  else
    note "waiting for the HTTPS certificate (GitHub says: $cert)"
  fi
fi
exit 0
