# DEQ Tune

A web app for the equalizer and sound-profile part of Pioneer's Sound & Tune app.

The [wiki](https://github.com/stevendejongnl/deq-tune/wiki) has the guides: hardware, installing on the Pi, first run and troubleshooting for car owners, and the architecture, the DEQ protocol and the DSP blocks for developers.

This app edits DEQ tuning profiles: the 13-band graphic EQ, per-speaker level and time alignment, the high-pass filter, and fader/balance. It ships with the factory Mazda presets from the official Android app. It also ships an EQ library with Pioneer's own styles (Super Bass, Powerful, Vocal, ...), and the device's Live-Simulation modes (Concert hall, Club, ...). An EQ plays on top of the car profile. The UI works in English, Japanese, German, French, Spanish, and Dutch. The app picks the language from the browser, and Settings → Language changes it. The profile list is a permanent sidebar on a desktop screen, a drawer on a tablet, and a bottom sheet on a phone. The app has two pages. Sound holds what plays: the audio, the EQ and its library. Car holds the car profile: speakers, timing and the car's own correction curve. The phone shows them as the Audio, EQ and Car tabs. The factory presets live in a library. Star a car model there, and it stays in the sidebar. You can edit a factory preset, then revert it or save it as your own profile. A new profile starts flat. With a unit connected, you can save the tune the unit holds as a profile of its own. It is a web app that the Pi serves, and the Android car app carries it on the phone and in Android Auto. The backend speaks the DEQ's USB protocol and drives the unit through a Raspberry Pi. The Pi answers the DEQ's accessory handshake and relays frames (see [Status](#status)).

## Project layout

```
backend/    FastAPI + SQLite. Serves and stores profiles, and drives the DEQ unit.
frontend/   Lit + TypeScript + Vite. The EQ editor, profile list, and device header.
            `e2e/` holds the Playwright tests, which drive a real browser.
            `src/i18n/locales/` holds the UI text, one JSON file per language.
pi-gadget/  The Raspberry Pi side: the USB gadget, its kernel drivers, the BLE bridge, the
            access point and the systemd units. See `pi-gadget/README.md`.
data/presets/  The bundled factory preset JSON files, extracted from the Pioneer APK.
openapi.json   The backend's exported API schema. The frontend generates its DTOs from this file.
conformance/   Shared test corpus: inputs plus the exact bytes the Pioneer app produces for them.
tools/         Builds the conformance corpus and the device's value sets from the Pioneer APK.
Makefile       Shortcuts for install/dev/test/generate-dto/clean. Run `make help`.
```


## Setup

You need Python 3.13+ with [`uv`](https://docs.astral.sh/uv/), Node.js 22+, and a Go toolchain (`go` on your `PATH`). The frontend's `typia` transform compiles a small native plugin on first install.

```bash
cd backend && uv sync
cd ../frontend && npm install
```

`npm install` also runs a one-time native build for the frontend's DTO-validation toolchain. On a fresh install this build takes one to three minutes. Let it finish.

`make install` then runs `make warm`, which fills the frontend's dependency cache. Without it the first page load stalls. The `ttsc` transform writes imports of `typia`'s deep internals, so Vite cannot see them when it first scans. Vite then discovers them mid-load, re-optimizes and reloads. Warming takes about a second and makes `make dev` start in well under a second. Run `make warm` again after a `typia` or `vite` version change.

## Makefile

A `Makefile` at the repo root wraps the commands below. Run `make` or `make help` to list targets.

```bash
make install        # install backend and frontend dependencies
make dev             # run backend (8420) and frontend (5173) dev servers together
make dev-backend     # run only the backend dev server (8420)
make dev-frontend    # run only the frontend dev server (5173)
make dev-sim         # run the whole stack against the simulated DEQ
make dev-simulator   # run only the backend against the simulated DEQ
make console         # change what the simulated DEQ reports
make warm            # fill the frontend's dependency cache
make test            # run backend and frontend tests
make e2e             # run the end-to-end tests in a real browser
make e2e-install     # install the browser those tests need, once
make typecheck       # type-check the frontend
make generate-dto    # regenerate frontend DTOs from the backend schema
make check-real-deq  # run the hardware check against a real unit
make clean           # remove .venv, node_modules, the local database and the simulator state
```

## Run it locally

Either `make dev`, or run each side by hand:

Start the backend (port 8420):

```bash
cd backend
PYTHONPATH=. uv run uvicorn app.main:app --reload --port 8420
```

Start the frontend (port 5173, proxies `/api` to the backend):

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. The backend seeds its 14 bundled Mazda factory profiles into `backend/deq.db` on first startup.

## Tests

Either `make test`, or run each side by hand:

```bash
cd backend && uv run pytest
cd backend && uv run pytest ../pi-gadget   # the Pi updater
cd frontend && npm test
```

Every test file lives next to the code it tests (`app/foo.py` → `app/test_foo.py`, `src/foo.ts` → `src/foo.test.ts`).

The end-to-end tests run in a real browser, which is the only place real
rendering and real CSS can be checked. They start the backend and the
frontend themselves, with `DEQ_TRANSPORT=fake`, so they need no hardware:

```bash
make e2e-install    # once, to fetch Chromium
make e2e
```

Those specs live in `frontend/e2e/` and end in `.spec.ts`, so `vitest` and
Playwright never pick up each other's files.

## Translating

The app's text lives in `frontend/src/i18n/locales/`, one JSON file per
language. `en.json` is the source text and changes with the code. The community
translates the other five at
<https://hosted.weblate.org/projects/deq-tune/>, which opens a pull request on this repository for every batch of
changes.

A string nobody translated yet reads English, so a part-done language still
works. [TRANSLATING.md](TRANSLATING.md) explains how to help, and which names
are deliberately **not** translatable. The EQ-style, Live-Simulation, car model,
and speaker-type names come from Pioneer's own app, so the web UI matches
what the DEQ unit shows.


## Regenerating the frontend DTOs

The backend's Pydantic models are the source of truth for the data shape. After changing `backend/app/eq_data.py` or `backend/app/schemas.py`, run `make generate-dto`, or by hand:

```bash
cd backend && PYTHONPATH=. uv run python scripts/export_openapi.py
cd ../frontend && npm run generate:dto
```

Commit the updated `openapi.json` and `frontend/src/dto/generated/openapi.d.ts` together with the schema change. The frontend's API client checks every request and response against these generated types at runtime (`typia.assert`), so a mismatch fails loudly instead of silently.

## Licence

[GNU AGPL-3.0](LICENSE).

**Scope.** The licence covers this project's own code. It does not cover the
material taken from Pioneer's Android app. That material is the bundled preset
files in `data/presets/`. It is also the car model, speaker type, EQ-style and
Live-Simulation names transcribed in `backend/app/preset_translations.py`,
`frontend/src/i18n/preset-names.ts`, and `frontend/src/i18n/dsp-presets.ts`.
Those stay Pioneer's, and they are here so this app can talk to the same device
and show the same names on screen. This project is not made by, or connected
to, Pioneer.

## Status

- **Profile editing**: works. Factory Mazda presets plus your own custom profiles, backed by the FastAPI backend. The editor changes the selected bank of `foundationEq.eqs.LR`, which is the curve a push sends. The preset files also carry an `expandEq` curve. The Pioneer app neither reads nor writes it, so this app leaves it alone. `PUT /api/profiles/{id}/favorite` stars a profile, and a factory preset takes a star too. `POST /api/device/profile` reads the unit's settings blob and stores it as a custom profile. `backend/app/unit_tuning.py` does that mapping. A 31-band bank goes through the app's own 31-to-13 conversion, so the profile stays 13-band and the unit gets the same coefficients. One profile is the active one: the one the unit plays. `PUT /api/active-profile` makes a profile active. The backend pushes it at once when the unit is connected. Otherwise it pushes it as the next link comes up, before the header reports the link. `GET /api/active-profile` gives the status. The unit plays the stored version (`applied`), waits for a link (`waiting`), plays an older version after an edit (`outdated`), or refused the push (`failed`). The app shows that status under the profile name, with Activate, Apply changes or Try again, and tags the active profile in the sidebar. The choice lives in the database, so it outlives a restart.
- **Localization**: works. English, Japanese, German, French, Spanish, and Dutch. The app picks the language from the browser on the first visit and remembers it after. Settings → Language links to the Weblate project and to `TRANSLATING.md`, and says that a string nobody translated shows in English. The UI text lives in `frontend/src/i18n/locales/`, one JSON file per language. The community translates it in Weblate (see [TRANSLATING.md](TRANSLATING.md)). The preset and DSP-preset names come from the APK's own string resources per locale (`backend/app/preset_translations.py`, `frontend/src/i18n/preset-names.ts`, `frontend/src/i18n/dsp-presets.ts`). The bundled preset JSON itself only carries Japanese text. Note: Pioneer never localized the car/speaker-type names for German/French/Spanish/Dutch, so those locales show the English text. Pioneer translated the EQ-style and Live-Simulation DSP preset names in all six locales.
- **EQ library**: works. A profile describes the car: speakers, distances, filters and a correction curve. An EQ describes a taste in music, and the unit plays the sum of both. The Pioneer app works the same way. It adds the profile's curve and its own "makeup EQ" band for band. Then it clamps each term and the sum to ±12 dB. `backend/app/equalizers.py` does that sum, and every push sends it. `/api/equalizers` lists, copies, edits and deletes EQs, and `PUT /api/active-profile/equalizer` picks the one that plays. The library comes with Pioneer's own 13 styles plus Flat. Their curves come from the app's player library (`MultiBandEqualizer::getBandEq` in `libPMGJni.so`), run under an emulator. The Pioneer app shows a different set per region. Outside Brazil, India, Japan and Mexico it shows seven, and those seven start with a star. The EQ panel and the car app's EQ folder show the starred EQs and the person's own. The Library lists every EQ with a star, as the profile library does. The main EQ chart edits the EQ that plays. A factory EQ stays read-only, so the first drag of one, or of No EQ, makes a copy of the person's own, and the copy plays. On a touch screen only a touch on a dot drags it, so a swipe over the chart scrolls the page. Undo, above the chart, takes back one edit step: a whole drag, or one tap on − or +. The car profile's own correction curve sits apart, as "Car correction" next to the speakers. It has its own Undo, with the same steps. Its steps clear when another car profile opens, or when a factory preset goes back to the factory data.

  The unit does not compute a style itself. A style picked in the settings blob only names what plays, so the sound stays the same. Each push therefore puts the unit's own style on Custom in bank A, and sends the whole curve as coefficients. `/api/device/eq-style` still writes the blob, but the app no longer offers it.
- **Volume and mute**: `POST /api/device/volume` and `POST /api/device/mute` write to the unit and answer with what it now holds. Mute is a boolean on the wire, read and write: 1 is muted, 0 plays. The Pioneer app's request builder (`b/e/aa`) and its `0x0b` reply parser (`b/f/x`) both treat it that way. The `MUTE_STATE` enum (1 on, 2 off) is the app's own model, not the wire. The Audio page's volume slider shows its value while it moves and sends it when it rests for 300 ms or the finger lets go. A send that waits while one is on its way replaces any older one waiting, so a drag makes a few USB writes and not one per step.
- **Source mode**: a new link sets `CAR_SOURCE`, the car's audio through the DSP, unless the person chose another mode. `THROUGH` most likely skips the DSP: the Pioneer app picks it only while a phone call rings, and its level block has no level for it. A drive on 2026-10-15 confirmed that `CAR_SOURCE` plays the EQ. `PUT /api/active-profile/source` and `POST /api/device/audio-source` both keep the choice for each next link.
- **Live Simulation**: works, against a connected unit. The mode lives in the settings blob as `sound_field`. A selection reads the blob, changes that byte and writes the blob back. The list comes from the Pioneer app's own enum. `tools/build_enums.py` reads the enums out of the APK into `backend/app/deq_enums.json`. A decoder returns `UNKNOWN` for a wire value it does not recognise, and three modes have no label in the APK's own resources. The app leaves those out, as the Pioneer app does, so it shows 5 modes.
- **Browsers**: all of them. The backend owns the USB link, so the frontend needs no WebUSB and the app has no browser requirement. It once blocked Safari, Firefox and iOS for a capability it no longer uses.
- **DSP coefficients**: works. `backend/app/deq_dsp.py` computes the numbers the DEQ expects: the 13-band equalizer, the crossover filters, and the time alignment. The DEQ designs no filters of its own. The Android app sends finished coefficients, so this app has to produce the same ones. The tests check the maths against coefficients captured from the Android app's own designer library (`backend/app/deq_dsp_reference.json`, 253 cases). The maths matches to within one Q27 step. The equalizer needs one step beyond filter design. The library spreads every band's gain over the other bands before it designs a biquad. So two raised bands are not two independent peakers. `fit_equalizer_gains` reproduces that step from the library's own constant tables. `conformance/flows.json` then checks whole payloads, byte for byte, against what the Android app produces (`backend/app/test_conformance.py`).
- **Settings**: a settings page in the style of Fluidd, behind the gear button in the header (the Settings tab on a phone). Its sections are Phone app (inside the car app only), Updates, Wi-Fi, Backup, Community, System and Language. `frontend/src/components/settings-page.ts` lays it out.
- **Loaders**: every control whose action waits on the Pi shows a spinner in place of its label while the request runs: the EQ and Live Simulation choices, Activate and Apply, New profile, Save unit's tune, Save as my profile, the Wi-Fi and access point buttons, Backup, Community's Add, and Check now. A component sets `aria-busy="true"` on the control, and `frontend/src/components/busy.styles.ts` draws the spinner. The page does not reload into a newer build from the Pi while a text field has the focus or a profile action runs.
- **Community library**: works. The index is live, with one entry so far. Other people share car profiles and EQs in the [deq-tune-library](https://github.com/stevendejongnl/deq-tune-library) repository, one JSON file per entry, and its CI publishes them as one `index.json` on GitHub Pages. The Community section of the settings page reads that file in the browser, so the Pi needs no internet. "Add to my library" sends one entry through `POST /api/library/import`, the same import as a backup file, so it adds and never replaces. `frontend/src/api/community-library.ts` reads and checks the index.
- **Updates**: works on the Pi. `pi-gadget/deq_updater.py` installs each new release by itself (see `pi-gadget/README.md`). `/api/updates` reads its state file, `PUT /api/updates/settings` switches automatic updates on or off, and `POST /api/updates/request` asks for one update now (`backend/app/updates.py`). A machine with no updater answers `supported: false`. `DEQ_UPDATE_DIRECTORY` points the backend at the updater's files (default `/home/deq`). A notification dock in the bottom-left corner says what is new after an update, and offers a waiting release while automatic updates are off.
- **Fresh, not cached**: while the bridge answers, the app never shows an old copy. The app has no service worker since 2026-10-24, when the PWA went. `frontend/public/sw.js` is a worker that only removes itself and its caches from a browser that installed the old one. The backend serves the page with `Cache-Control: no-cache`. `/api/updates` reports the bridge's `frontend_build`, and a page with another build reloads by itself, once per build and never over unsaved edits (`updates-controller.ts`). `GET /api/bridge/frontend` returns the whole web app as one base64 zip, for the car app's own copy (`backend/app/frontend_bundle.py`).
- **Bridge Wi-Fi**: works on the Pi. The Wi-Fi section of the settings page lists the networks the Pi joins, and adds or forgets one. `/api/wifi` serves it (`backend/app/wifi_networks.py`). The backend runs as an ordinary user, so it calls one root helper, `/usr/local/bin/deq-wifi-networks`, through `sudo -n`. The sudoers rule names that helper and nothing else. The password goes to the helper on stdin, never on a command line. A save joins nothing at once: the Pi joins a saved network on its own, and "Join now" asks it to try. The helper refuses a radio change while the DEQ holds the USB link (409). A machine with no helper, such as a laptop, answers 503, and the Wi-Fi section says so. The Pi's own access point starts with the public default key `deq-tune-bridge`. While the Pi uses that key, the app asks for a key of your own when it starts. "Later" closes that step for good on that browser, and a notice in the bottom-left corner stays until the key changes. It hides while Settings → Wi-Fi is open, so it does not cover the form. Its button opens Settings → Wi-Fi, which can change the key at any time. The access point uses a new key from its next start. So after a save the helper restarts the Pi, 5 seconds later, once the reply has left. During a DEQ session it does not restart, because a restart would also restart the gadget and wedge the USB link. The key then applies at the Pi's next start, and the reply's `restarts_now` tells the app which of the two happened. The API never returns the key.
- **Driving the unit**: works, against a real unit through the Pi (see **A real unit** below). `backend/app/deq_session.py` runs the unit's own startup sequence and matches every reply to its request. It sends a profile's DSP settings as four blocks of command `0x05`. The speaker levels, the fader and the balance go under CONFIG_ID 0, the equalizer under 13, the time alignment under 10, and the crossover under 11 or 12. The level block keeps the values that a profile does not name, such as the subwoofer level and the level per source mode: the backend reads them from the unit with `0x06` first. Each of those CONFIG_IDs comes from the APK's own dispatch table. Each payload size matches the field width that table declares. `backend/app/deq_protocol.py` reads and writes the wire format. `backend/app/deq_commands.json` lists every command's fields in both directions, generated from the Android app's field enums. `backend/app/deq_blob.py` reads and writes the settings blob: speaker mode, both equalizer banks, crossovers, per-speaker values.

  A profile carries only a front and a rear high-pass filter. Those two are the first of the unit's five crossover slots. The person sets the rest on the unit itself. So a push reads the unit's stored crossover and keeps those slots, and does not send Pass over them. Pass would write identity biquads into the audio path while the blob still named a frequency and a slope. The unit would then disagree with itself.

  The frontend asks for all of this over `/api/device`, so the browser never touches USB.

  `/api/bridge` reports the machine the backend runs on, which is not the DEQ. A Pi that browns out drops its USB link and its Wi-Fi at once. Without this report the app shows only the symptom, and a person debugs the wrong thing. The endpoint reads the Pi's undervoltage flags through `vcgencmd`. It answers `null` on any machine that has none, so a laptop and CI are not special cases. Settings → System also shows the DEQ unit's firmware version. The pill does not. `/api/bridge/system` adds the machine statistics: board, OS, kernel, uptime, load, CPU temperature, memory, disk, network interfaces, and the id of the frontend build that the bridge serves. A click on the header's status pill opens them in the System section of the settings page. The pill also says whether the page is `live` from the Pi or `offline`. The section compares the page's build id (`frontend/src/build-id.ts`, written into `dist/build-id.txt` at build time) with the served one, and offers a reload when they differ.

  The backend records a fault there as a **notice that stays until the bridge restarts** (`backend/app/bridge_notices.py`). A dip that lasts a second is gone from every live reading by the time anyone looks. It still explains the link that dropped. A clear when the condition passes would hide the only evidence. Restarting the bridge clears them, which matches the hardware's own sticky undervoltage bit.

  The backend connects by itself. `LinkKeeper` in `backend/app/deq_device.py` runs in its own thread, which starts with the app. It calls `connect()` until the link is up, and again whenever the link drops. So the frontend has no connect button: it reads `/api/device` and reports what it finds. The keeper is a thread and not an asyncio task. A transport read blocks for its whole timeout, and in an asyncio task it would stall every request in progress. One lock guards the link, because the keeper's thread and the request handlers both reach it. The protocol is one request and then its reply, over a single transport.

  Four transports sit behind `backend/app/deq_transport.py`. That file also holds the piece they share. `FrameJoiner` cuts whole frames out of the bytes a link hands back. Every link carries the same frames, and only the read differs. A bulk USB read returns one 512-byte packet. A socket read returns the bytes that arrived. `FrameJoiner` imports nothing optional, so `app/test_deq_transport.py` tests the framing with no USB stack installed, the 512-byte pad rule included. `DEQ_TRANSPORT=fake` is the default. It talks to `backend/app/testing/fake_deq.py`, which answers by the rules measured from 217 request-and-reply pairs of real DEQ-S1000A2 traffic. `app/testing/test_fake_deq.py` checks that the fake reproduces a captured reply byte for byte. So the fake stands in for the unit and not for our own guesses. `DEQ_TRANSPORT=usb` talks to a real unit over bulk transfers through `backend/app/usb_transport.py`, which needs the `usb` extra:

```bash
cd backend && uv sync --extra usb
PYTHONPATH=. DEQ_TRANSPORT=usb uv run uvicorn app.main:app --port 8420
```

  `DEQ_TRANSPORT=accessory` is the one that reaches a DEQ in a car, and it needs no extra at all. It talks to the unit through the Pi's accessory gadget, over `backend/app/accessory_transport.py`:

```bash
cd backend
PYTHONPATH=. DEQ_TRANSPORT=accessory uv run uvicorn app.main:app --port 8420
```

  `DEQ_TRANSPORT=simulator` is the fake unit with knobs on, for working on the frontend without hardware. It is `FakeDeq` plus a state file, so every protocol rule stays pinned to real captures and only the reported state varies. `backend/scripts/deq_console.py` is a small curses console that writes that file. The simulator reads the file again before each reply. So a key press shows up in the next frame, and nothing restarts. Run the two side by side:

```bash
make dev-sim    # the whole stack against the simulated unit
make console    # in a second terminal, to change what it reports
```

  The console moves the volume, mutes, and sets the driving state. It also turns on the faults a real unit can show. The unit can refuse the open with `STATUS -5` and then go quiet, fail one command, or report system error flags. Refuse the open and `/api/device` reports `connected: false` with the unit's own reason. Clear the fault and the link comes back. `DEQ_SIMULATOR_STATE` names the file if the default `deq-simulator-state.json` is in the way.

  The simulator knows nothing about the Pi and reaches no hardware. It also has no "audio flowing" switch, on purpose. Audio is a separate USB function, and the DEQ never reports on it. So the switch would invent a protocol field that does not exist.

  The accessory transport exists because a laptop's own USB-C port is usually host-only hardware. The DEQ is itself a USB host when connected over its own USB-A port. Two hosts plugged together answer each other with silence, and give no error. A Pi can present the device side. So it runs a gadget that answers the DEQ's Android Open Accessory handshake. The unit expects to talk to a tablet that runs Pioneer's own app, and the Pi takes that place.

  The gadget program owns the USB handle. The backend does not. The gadget answers the mode-switch request and re-enumerates the gadget. It puts the accessory interface where the unit expects it. It feeds the audio function that the unit demands before it will talk. The backend does none of that work. Two programs also cannot share the handle, because two writers on one link interleave frames. So the gadget keeps the handle and relays whole frames over a Unix socket. `accessory_transport.py` is the other end of that socket. While the backend holds the socket, the gadget sends nothing of its own: no cold start and no keepalive. The backend's session carries both. When the backend detaches, the gadget takes the link back, so the link does not drop. The SysEx framing and all command parsing stay in `deq_protocol.py`, unchanged. The gadget program itself is not in this repository.

- **A real unit**: answering. A DEQ-S1000A2 in a car answered all ten commands of the read-only cold start, each with `STATUS 0`. It sent its firmware version (2.02), its device id, and 2032 bytes of tuning state. This app's own blob decoder read that state on the first try. The same day, `check_real_deq.py --write` wrote the unit's own settings back, and the unit kept every byte. So the hardware itself backs the protocol work, and not only the captures.

  The road there had four bugs worth knowing about, because any reimplementation inherits them. The session must open with `0x00`, and that frame must carry its 24-byte body. The unit answers an empty one with `STATUS -5` in 40ms and then ignores it. That reads like success if nobody checks `STATUS`. Every capture shows `0x02` as the opener instead, because every capture started mid-session. The accessory interface has to land at index 2, and the audio function has to be a source rather than a sink.

  `backend/scripts/check_real_deq.py` is the check to run against a unit. It uses `DEQ_TRANSPORT`, same as the app itself:

```bash
cd backend
PYTHONPATH=. uv run python scripts/check_real_deq.py   # the accessory gadget, this script's default

cd backend && uv sync --extra usb
DEQ_TRANSPORT=usb PYTHONPATH=. uv run python scripts/check_real_deq.py
```

  It also reads the speaker and system mute states (`0x14` and `0x1c`). No unit answered those two so far, so the script prints the raw value. It reads only, unless you pass `--write` (which writes the unit's own settings back unchanged). Each check prints `ok`, `DIFFERS` or `FAILED`. A `DIFFERS` line is the valuable one: the unit answered, but not the way the app and the captures predicted. Record those in the private notes. The Pioneer app and the unit are the authority, and this code is the thing under test. The `accessory` transport opens a socket and needs no privileges of its own. The `usb` transport opens a USB device, which on Linux usually needs root or a udev rule. `backend/scripts/99-pioneer-deq.rules` is one, with the install steps in its own comment.

  `backend/scripts/probe_audio_output.py` sends source modes to a real unit and holds each one long enough to hear what comes out. It answered the hardware question that blocked this project, in a car on 2026-10-08. On `SP_OTHER_SOURCE` the unit plays what this device writes over USB. On `THROUGH` it plays the car's own audio. Both hold with the USB audio function attached, so a session and the car radio do not conflict. `THROUGH` is what a connect leaves the unit on. The probe also found one catch. The unit refuses a volume write with `STATUS -6` while it holds `THROUGH`, and accepts one on an OTHER mode. So the mode goes first.

```bash
cd backend
DEQ_TRANSPORT=accessory PYTHONPATH=. uv run python scripts/probe_audio_output.py
```

  It writes to the unit, and it puts the mode and the volume it found back when it finishes. Rehearse it against the fake first, where it costs nothing: `DEQ_TRANSPORT=fake PYTHONPATH=. uv run python scripts/probe_audio_output.py --hold-seconds 0`.
