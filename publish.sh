#!/bin/zsh
# Push the encrypted out/data.json to the single-commit `data` branch that the page polls.
# Always pushes as pawslyOps (gh account), whatever account is active and whatever the keychain holds.
set -e
cd "${0:A:h}"
REMOTE=$(git remote get-url origin)
if [ ! -d .publish/.git ]; then
  rm -rf .publish && mkdir .publish && cd .publish && git init -q -b data && git remote add origin "$REMOTE"
  git config credential.https://github.com.helper "" && git config --add credential.https://github.com.helper "!gh auth git-credential"
  git config user.name pawslyOps && git config user.email pawslyOps@users.noreply.github.com
  cd ..
fi
cp out/data.json .publish/data.json
cd .publish
git config core.logAllRefUpdates false
rm -f .git/index.lock
git add data.json
git commit -q --amend -m "data" 2>/dev/null || git commit -q -m "data"
tok=$(gh auth token -h github.com -u pawslyOps)
# Also write the update to one of ten rotating branches (d0..d9, by the update's running number). GitHub's file
# server caches each address for 5 minutes; a rotating address is only asked for once every 10 minutes, so the page
# always gets the fresh copy from it without using the rate-limited API.
slot=$(python3 -c "print(int(open('../raw/seq.txt').read())%10)" 2>/dev/null || echo "")
if [ -n "$slot" ]; then GH_TOKEN=$tok GIT_TERMINAL_PROMPT=0 git push -q -f origin data "data:refs/heads/d$slot"
else GH_TOKEN=$tok GIT_TERMINAL_PROMPT=0 git push -q -f origin data; fi
# superseded snapshots are only kept alive by reflogs: drop them so .publish stays small
git reflog expire --expire=now --all 2>/dev/null || true
git gc -q --prune=now 2>/dev/null || true
