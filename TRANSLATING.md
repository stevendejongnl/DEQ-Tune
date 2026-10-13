# Translating DEQ Tune

The app speaks English, Japanese, German, French, Spanish, and Dutch. You can
improve any of them, or finish one that is behind, without a clone and without
writing code.

## Where to translate

Translate at **<https://hosted.weblate.org/projects/deq-tune/>**.

Make an account there, pick your language, and type. Weblate collects the
changes and opens a pull request on this repository by itself. A maintainer
reads it and merges it.

You do not have to finish a language. A string nobody translated shows the
English text, so a part-done language still works. Translate what you know and
leave the rest.

## What you can translate

One file per language, under `frontend/src/i18n/locales/`. Those files hold the whole
app: buttons, labels, hints, and messages. English (`en.json`) is the source
text. Weblate shows it beside every string.

## What you must not translate

Three groups of names come from Pioneer's own Android app, not from us:

- the EQ-style names (Super Bass, Powerful, Natural, ...)
- the Live-Simulation names (Concert hall, Open air, Club, ...)
- the car model and speaker-type names (Mazda3, CX-5, For Normal Speaker, ...)

They live in `frontend/src/i18n/dsp-presets.ts` and
`frontend/src/i18n/preset-names.ts`, and Weblate cannot reach them. This is on
purpose. The user reads these same names on the DEQ unit's own screen, so the
app must print what the unit prints. That holds even where Pioneer's text is odd, cut
short, or still English. If one looks wrong, open an issue. Do not work around
it in a string you can edit.

## Rules for a good translation

**Keep a placeholder as it is.** The app puts a number in place of `{count}`
while it runs. Translate the words around it, never the placeholder.

- English: `Edited · {count} bands`
- Dutch: `Bewerkt · {count} banden`
- Wrong: `Bewerkt · {aantal} banden`. The user then reads `{aantal}`.

A test refuses a pull request that loses a placeholder, so Weblate will not let
this one through.

**Keep the short strings short.** These sit in a header, a tab, or a badge. The
app cuts long text off: `connectShort`, `revertShort`, `saveShort`,
`speakerPioneerShort`, `speakerStockShort`, `tabEq`, `tabStyle`.

**Keep these words as they are:** DEQ, EQ, Pioneer, Carrozzeria, Mazda.

**Write what a driver reads.** The app runs in a car. Short sentences, plain
words, no jargon that a hi-fi shop would use.

## Asking for a new language

Open an issue and name the language. Weblate can start the file. But the app
needs three small code edits before it offers the language in its picker. A
maintainer has to do that part.

## For maintainers

**Adding a string.** Add the key to the `UiStrings` type and to `en.json` in
the same commit. Weblate reads the new key on its next pull and asks the
translators for it. The five other files need nothing: a missing key reads
English.

**Removing a string.** Remove it from the type and from `en.json`. Weblate's
cleanup addon prunes it from the translations.

**Reviewing a Weblate pull request.** Check that it touches only
`frontend/src/i18n/locales/*.json`, that the checks pass, and read the diff.
Never merge one without reading it.

**From the command line.** The `.weblate` file at the repo root points `wlc` at
the project. So `wlc pull`, `wlc commit`, and `wlc push` work from here. Put
your API key in `~/.config/weblate` or the `WLC_KEY` environment variable, never
in the repo.
