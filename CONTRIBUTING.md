# Contributing

Thank you for helping agents build better ERPForAll addons.

## Sign your commits (DCO)

Contributions are accepted under the Developer Certificate of Origin (https://developercertificate.org/). Add a
`Signed-off-by: Your Name <you@example.com>` line to every commit with `git commit -s`. By signing off you state that
you wrote the change or have the right to submit it under this repository's licence, `MIT OR Apache-2.0`.

## The rule for skills: zero fabrication

A skill is only useful if an agent can trust it. So:

1. **Read before you write.** Every API name, macro, attribute, file layout, CLI command and flag, XML element and
   attribute in a skill must be something you read in a page of the framework's addon guide or in a real addon of the
   framework repository.
2. **Say what you did not find.** If the guide does not cover something, write "not covered here" and point at the page
   to read. Do not fill the gap from memory of another framework.
3. **Cite.** End the skill with `## Sources`, a bullet list of repo-relative paths (`docs/addon-guide/views.md`,
   `addons/contacts/views/contacts_views.xml`). Every path must exist in the framework checkout you wrote from.
4. **Note work in progress.** The guide marks features as not built yet. Do not describe them as available.
5. **Prefer the real addon over a guide snippet** when they differ (for example, the access CSV `operation` letters), and say
   which you followed.
6. Keep it short and procedural; one topic per skill.

## Add or change a skill

1. Create or edit `skills/erpforall-<topic>/SKILL.md`: frontmatter `name` (same as the directory) and `description`
   (when to use it, at most 1024 characters), a `# Title`, the procedure, "Not covered here", `## Sources` last.
2. Run `python3 -I scripts/build-packaging.py` to refresh the generated packaging files.
3. Run the checks from `AGENTS.md`. `scripts/check.py --source <framework checkout>` verifies the frontmatter, the
   `Sources` list (each path must exist), the guide pages named in the text, and that no internal host names or e-mail
   addresses slipped in.
4. If your skill relies on a tool behaviour, add a test under `tests/`.
5. Open a pull request that names the guide revision you read (update `SOURCE_REVISION`).

## Tools

`tools/*.py` use Python 3.11+ and the standard library only. Add a unit test for every check you add to
`addon-lint.py`, including a case that must pass and a case that must fail, and make sure the real example addons
(for example `sample_library`) still lint clean.
