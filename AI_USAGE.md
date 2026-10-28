# AI Usage

[BeatSmith](README.md) · [App guide](docs/APP_GUIDE.md) · [Command line](docs/COMMAND_LINE.md)

This page describes the released app's AI features and the use of AI during
development. AI features are optional. Normal chart generation does not
require a cloud AI account or API key.

## AI in the app

| Feature | What it does | Where it runs | What you need |
|---|---|---|---|
| AI assist | A bundled step-placement model contributes scores for where steps could go; charting rules still arrange and constrain the result | On your computer, using ONNX Runtime | The bundled model and runtime; no separate cloud account |
| Melody analysis / vocal separation | Demucs separates vocals, drums, bass and other audio so the experimental follow control can use the separated signals | On your computer | The optional vocal-separation download |
| AI verse detection | Whisper, through faster-whisper, reads words from separated vocals; repeated lyrics help identify verses and choruses | On your computer | Vocal separation plus the optional verse-detection download |

The regular beat analysis, chart arrangement, difficulty targeting, Groove
score and editor are not a chat model writing a chart from a prompt.
Artwork cropping and layout are not a text-to-image generator.

**AI assist** and **Arrows follow** are different controls. The former changes
step-placement scores; the latter changes which musical onset signals are
favored. Vocal separation itself uses AI, but the follow control does not
transcribe exact musical pitches. The released app has no dedicated
lead-instrument mode.

## What stays local

In the normal desktop generation and editing workflow, song audio, separated
stems, transcribed words, generated charts and chart statistics are processed
and stored on your computer. These features do not upload your song audio to
a cloud AI service.

After the required packages/models are available, these AI operations run
locally. A first download, a missing model or an optional package update can
still require the internet. Network services receive normal request metadata,
such as your IP address, when contacted; local inference does not make a
download anonymous.

## Downloads and other online requests

| Action | What is requested or sent | Destination |
|---|---|---|
| Download a packaged vocal/verse add-on | A request for your app version's add-on archive | This project's GitHub Releases |
| Install add-ons when running from source | Python/packages/model downloads, rather than the packaged app's ready-made archive | python.org, bootstrap.pypa.io, PyPI/package hosts, Meta's model host and Hugging Face, depending on the add-on |
| Download NVIDIA GPU support | Optional PyTorch/CUDA packages | PyTorch's package servers and package dependencies |
| Enable online artwork lookup | Song title and artist search terms; requests for returned artwork | MusicBrainz, Cover Art Archive/Internet Archive, iTunes/Apple and Deezer, including their image hosts |

The app shows add-on sources before starting a download and logs download
addresses. Online artwork lookup is a separate opt-in option; using nearby
or embedded artwork does not require a web search. Artwork lookup sends
metadata, not song audio.

## Separate cloud-review tool: unfinished

`llm_review.py` is an optional command-line experiment, not an automatic
step in the desktop app. It predates newer app options and its suggested
reruns may omit those options. Treat it as unfinished.

If you explicitly run it with a cloud provider, it sends a **text prompt**
containing derived song-section summaries, chart steps, statistics and
settings. It does not attach the audio file. Supported cloud paths are
Google Gemini and Anthropic Claude, using your API key. Their own terms,
privacy practices and any charges apply.

The tool also supports an OpenAI-compatible local server such as LM Studio.
Its local-server URL is configurable: data stays on your machine only when
you actually use a server on that machine. `--prompt-only` writes a prompt
to disk without calling an AI API; if you paste it into a website yourself,
you are sharing it with that website. Inspect the prompt before sharing it.

See the [command-line reference](docs/COMMAND_LINE.md#unfinished-llm-review-tool)
for the safer prompt-only starting point.

## AI-assisted development

AI tools, including **Claude** and **OpenAI Codex**, have assisted with code,
debugging, tests and documentation. The project maintainer makes product
decisions and reviews changes through pull requests. AI assistance is not a
guarantee that code or documentation is correct; build checks and play
testing remain necessary.

The app screenshots in the documentation are renders of the real interface,
using temporary synthetic demo audio and charts. They are not AI-generated
interface mockups. Optional-download availability is illustrated with a clean
installation state, and file paths use a generic example.

## Limits and your controls

AI can miss or invent perceived musical events. Separation can leave bleed,
speech recognition can mishear lyrics, and model placement can feel wrong
even when an automated score improves. Difficulty and Groove scores are
estimates, not proof of musical quality.

You can leave AI assist at zero, keep melody analysis and AI verse detection
off, and keep online artwork lookup off. Listen, edit and play-test the
result before relying on it. Generated charts do not grant rights to the
underlying song.

This is a description of the app's current behavior, not a promise about an
external provider's retention policy. For technical verification, the main
entry points are [AI assist](src/beatsmith/ai_assist.py), [add-on downloads](src/beatsmith/addons.py),
[separation](workers/stems.py), [verse detection](workers/lyrics.py), [artwork](src/beatsmith/artwork.py)
and the [separate review tool](tools/llm_review.py).
