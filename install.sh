#!/usr/bin/env bash
# Install (or remove) the ERPForAll agent-kit skills for Claude Code, Codex CLI, Antigravity and Gemini CLI.
# Works with bash 3.2+ (macOS default). Idempotent. Never overwrites files or folders it did not create.
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARK=".erpforall-agent-kit"          # file written inside copied skill folders to recognise them later
BEGIN="<!-- erpforall-agent-kit:begin -->"
END="<!-- erpforall-agent-kit:end -->"

usage() {
  cat <<USAGE
Usage: install.sh --agent AGENT [options]      install skills
       install.sh --uninstall --agent AGENT    remove what this script installed

  --agent AGENT      claude | codex | antigravity | gemini | all   (repeatable)
  --scope SCOPE      user (default) or project
  --project-dir DIR  project folder for --scope project and --agents-md (default: current directory)
  --copy             copy the skill folders instead of symlinking them to this checkout
  --force            replace an existing symlink of the same name that points somewhere else
  --bin-dir DIR      where to put erpforall-new-addon and erpforall-addon-lint
                     (default with --scope user: ~/.local/bin; none with --scope project)
  --no-tools         do not install the three command-line tools
  --agents-md        also add (or refresh) a marked block in DIR/AGENTS.md that points at the skill files
  --dry-run          print what would happen, change nothing
  -h, --help

Skill folders go to:
  claude       ~/.claude/skills            | <project>/.claude/skills
  codex        ~/.agents/skills            | <project>/.agents/skills
  antigravity  ~/.gemini/config/skills     | <project>/.agents/skills
  gemini       ~/.gemini/skills            | <project>/.gemini/skills
Claude Code can alternatively load this repository as a plugin (see docs/agent-support.md).
USAGE
}

agents=""; scope=user; project=""; mode=link; force=0; bindir=""; tools=1; agentsmd=0; dry=0; uninstall=0
while [ $# -gt 0 ]; do
  case "$1" in
    --agent) [ $# -ge 2 ] || { usage >&2; exit 2; }; agents="$agents $2"; shift 2 ;;
    --scope) scope="${2:-}"; shift 2 ;;
    --project-dir) project="${2:-}"; shift 2 ;;
    --copy) mode=copy; shift ;;
    --force) force=1; shift ;;
    --bin-dir) bindir="${2:-}"; shift 2 ;;
    --no-tools) tools=0; shift ;;
    --agents-md) agentsmd=1; shift ;;
    --dry-run) dry=1; shift ;;
    --uninstall) uninstall=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
case "$scope" in user|project) ;; *) echo "--scope must be user or project" >&2; exit 2 ;; esac
[ -n "$agents" ] || { echo "choose at least one --agent" >&2; usage >&2; exit 2; }
case " $agents " in *" all "*) agents="claude codex antigravity gemini" ;; esac
[ -n "$project" ] || project="$(pwd)"
[ "$scope" = user ] && [ -z "$bindir" ] && bindir="$HOME/.local/bin"

say() { printf '%s\n' "$*"; }
do_() { if [ "$dry" = 1 ]; then say "would: $*"; else "$@"; fi; }

target_dir() {
  case "$1:$scope" in
    claude:user) echo "$HOME/.claude/skills" ;;
    claude:project) echo "$project/.claude/skills" ;;
    codex:user) echo "$HOME/.agents/skills" ;;
    codex:project|antigravity:project) echo "$project/.agents/skills" ;;
    antigravity:user) echo "$HOME/.gemini/config/skills" ;;
    gemini:user) echo "$HOME/.gemini/skills" ;;
    gemini:project) echo "$project/.gemini/skills" ;;
    *) echo "unknown agent: $1" >&2; exit 2 ;;
  esac
}

is_ours_link() { [ -L "$1" ] && case "$(readlink "$1")" in "$KIT"/skills/*) return 0 ;; esac; return 1; }

install_skill() { # src dst
  local src="$1" dst="$2"
  if [ -L "$dst" ]; then
    if [ "$mode" = link ] && [ "$(readlink "$dst")" = "$src" ]; then say "ok      $dst (already linked)"; return; fi
    if [ "$force" = 1 ]; then
      do_ rm "$dst"
    else
      say "skip    $dst (a symlink to somewhere else; use --force to replace it)"; return
    fi
  elif [ -e "$dst" ]; then
    if [ -f "$dst/$MARK" ]; then do_ rm -rf "$dst"
    else say "skip    $dst (exists and was not installed by this kit; left untouched)"; return; fi
  fi
  if [ "$mode" = link ]; then
    do_ ln -s "$src" "$dst"; say "link    $dst -> $src"
  else
    do_ cp -R "$src" "$dst"
    if [ "$dry" = 1 ]; then say "would: write $dst/$MARK"; else printf 'installed by erpforall-agent-kit %s\n' "$(cat "$KIT/VERSION")" > "$dst/$MARK"; fi
    say "copy    $dst"
  fi
}

uninstall_skill() { # src dst
  local dst="$2"
  if is_ours_link "$dst"; then do_ rm "$dst"; say "removed $dst"
  elif [ -d "$dst" ] && [ ! -L "$dst" ] && [ -f "$dst/$MARK" ]; then do_ rm -rf "$dst"; say "removed $dst"
  elif [ -e "$dst" ] || [ -L "$dst" ]; then say "skip    $dst (not installed by this kit)"
  fi
}

for agent in $agents; do
  dir="$(target_dir "$agent")"
  say "== $agent ($scope): $dir"
  [ "$uninstall" = 1 ] || do_ mkdir -p "$dir"
  for s in "$KIT"/skills/*/; do
    name="$(basename "$s")"
    if [ "$uninstall" = 1 ]; then uninstall_skill "${s%/}" "$dir/$name"; else install_skill "${s%/}" "$dir/$name"; fi
  done
done

install_tool() { # source-script command-name
  local src="$KIT/tools/$1" dst="$bindir/$2"
  if [ "$uninstall" = 1 ]; then
    if is_ours_tool "$src" "$dst"; then do_ rm "$dst"; say "removed $dst"; elif [ -e "$dst" ] || [ -L "$dst" ]; then say "skip    $dst (not installed by this kit)"; fi
    return
  fi
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ] && [ "$mode" = link ]; then say "ok      $dst (already linked)"; return; fi
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    if is_ours_tool "$src" "$dst"; then do_ rm "$dst"; else say "skip    $dst (exists and is not this kit's tool)"; return; fi
  fi
  do_ mkdir -p "$bindir"
  if [ "$mode" = link ]; then do_ ln -s "$src" "$dst"; say "link    $dst -> $src"
  else do_ cp "$src" "$dst"; do_ chmod 755 "$dst"; say "copy    $dst"; fi
}
is_ours_tool() { { [ -L "$2" ] && [ "$(readlink "$2")" = "$1" ]; } || { [ -f "$2" ] && [ ! -L "$2" ] && cmp -s "$1" "$2"; }; }

if [ "$tools" = 1 ] && [ -n "$bindir" ]; then
  say "== tools: $bindir"
  install_tool new-addon.py erpforall-new-addon
  install_tool addon-lint.py erpforall-addon-lint
  install_tool addon-graph.py erpforall-addon-graph
  case ":$PATH:" in *":$bindir:"*) ;; *) [ "$uninstall" = 1 ] || say "note    $bindir is not on PATH" ;; esac
fi

agents_md() {
  local f="$project/AGENTS.md" snippet tmp
  snippet="$(sed "s#{{KIT}}#$KIT#g" "$KIT/templates/AGENTS.md.snippet")"
  if [ "$uninstall" = 1 ]; then
    [ -f "$f" ] && grep -qF "$BEGIN" "$f" || return 0
    if [ "$dry" = 1 ]; then say "would: remove the kit block from $f"; return; fi
    tmp="$(mktemp)"; awk -v b="$BEGIN" -v e="$END" '$0==b{skip=1} !skip{print} $0==e{skip=0}' "$f" > "$tmp" && cat "$tmp" > "$f"; rm -f "$tmp"
    say "removed the kit block from $f"; return
  fi
  if [ "$dry" = 1 ]; then say "would: write the kit block into $f"; return; fi
  if [ -f "$f" ] && grep -qF "$BEGIN" "$f"; then   # refresh the existing block in place
    tmp="$(mktemp)"; printf '%s\n' "$snippet" > "$tmp.snip"
    awk -v b="$BEGIN" -v e="$END" -v sf="$tmp.snip" '
      $0==b { print; while ((getline l < sf) > 0) print l; skip=1; next }
      skip && $0==e { print; skip=0; next }
      !skip { print }' "$f" > "$tmp" && cat "$tmp" > "$f"
    rm -f "$tmp" "$tmp.snip"
  else
    { [ -s "$f" ] && printf '\n'; printf '%s\n%s\n%s\n' "$BEGIN" "$snippet" "$END"; } >> "$f"
  fi
  say "kit block written to $f"
}
[ "$agentsmd" = 1 ] && agents_md
[ "$dry" = 1 ] && say "dry run: nothing was changed"
exit 0
