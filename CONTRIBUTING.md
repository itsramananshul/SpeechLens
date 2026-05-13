# Contributing to SpeechLens

Thanks for being here. SpeechLens is a small tool built to solve a real problem. Contributions that make it better are always welcome.

---

## Before you start

SpeechLens should stay simple. One Python file. One HTML file. No build step. If a change makes it meaningfully harder to set up, understand, or maintain — it's going to need a strong case.

Good contributions:
- Bug fixes
- New export formats
- Better error handling
- Documentation improvements
- Performance improvements

Things we'll be careful about:
- Heavy new dependencies
- Abstracting working code into frameworks
- Anything that breaks the zero-build-step frontend

---

## Running locally

```bash
git clone https://github.com/yourusername/speechlens
cd speechlens
pip install openai-whisper flask
python app.py
```

No build step. Open `localhost:7331` in your browser.

---

## Submitting a PR

1. Fork the repo
2. Create a branch: `git checkout -b fix/what-you-fixed`
3. Make your change
4. Test it — actually upload a file, run a transcription, make sure nothing broke
5. Commit clearly: `git commit -m "fix: describe the fix"`
6. Push and open a PR

Keep PRs focused. One fix or feature per PR. If your PR fixes a bug and also refactors unrelated code, split it.

---

## Reporting bugs

Open an issue and include:

- Your OS
- Your Python version
- The model you used
- What you did
- What happened vs what you expected
- Any terminal output

The more specific, the faster it gets fixed.

---

## Good first issues

Not sure where to start? These are approachable:

- **Audio playback panel** — play the audio inside the UI while reading the transcript
- **Batch export** — download all completed transcripts as a zip
- **Progress estimation** — calculate approximate remaining time from file size and model speed
- **Speaker diarization** — integrate pyannote.audio to label speakers
- **Configurable output directory** — let users choose where files are saved
- **Docker image** — Dockerfile that works on CPU and GPU

---

## Code style

- Readable over clever
- Comments where the logic isn't obvious
- No unused imports or dead code
- Backend: PEP 8 loosely
- Frontend: vanilla JS, no frameworks, stays in one file

---

## Questions?

Open an issue and tag it `question`.
