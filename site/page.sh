#!/bin/sh
# A Hugo page from a document of one of the repositories: front matter, then the
# document without its own title (the page shows the title).
# page.sh <title> <library> <version> <pdf, or ""> <source url> <markdown file>
printf -- '---\ntitle: "%s"\nlibrary: "%s"\nversion: "%s"\n' "$1" "$2" "$3"
[ -n "$4" ] && printf 'pdf: "%s"\n' "$4"
printf 'source: "%s"\n---\n\n# %s\n\n' "$5" "$1"
awk 'NR == 1 && /^# / { next } { print }' "$6"
