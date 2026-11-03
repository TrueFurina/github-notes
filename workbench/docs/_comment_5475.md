Confirming this, with one extra trap for whoever fixes it.

Root cause is as described: `get_sentence_based_splitter` splits on `(?<=[.!?])\s+`, and CJK terminators (。！？) are not followed by whitespace, so nothing is ever flushed.

The subtlety: the splitter rejoins the completed sentences with `" ".join(sentences[:-1])`. If you only add 。！？ to the split pattern, Chinese/Japanese chunks get a space inserted between sentences (e.g. `今天很好。 明天会下雨。`), which TTS reads as an extra pause. So the fix has to preserve the original spacing instead of rejoining with a space — splitting on boundary *positions* and slicing the original buffer does that.

Verified locally on main (e355d69): a position-based boundary regex `[.!?](?=\s)|[。！？]` keeps the existing English tests passing unchanged, splits zh/ja at 1/2/3/5/7-char deltas with no lost characters and no inserted spaces, and `tests/voice` stays green (286 passed) plus new zh/ja cases; `ruff check`/`format` clean.

Happy to share the patch if it helps — but per the contribution policy I'm not opening a PR.
