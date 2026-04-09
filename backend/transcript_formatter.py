"""Format Soniox transcript tokens into .txt and .srt formats."""


def format_timestamp_srt(ms: int) -> str:
    """Convert milliseconds to SRT timestamp format: HH:MM:SS,mmm"""
    hours = ms // 3_600_000
    minutes = (ms % 3_600_000) // 60_000
    seconds = (ms % 60_000) // 1_000
    millis = ms % 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def tokens_to_text(tokens: list[dict], include_speakers: bool = False) -> str:
    """Convert tokens to plain text."""
    if not tokens:
        return ""

    lines = []
    current_speaker = None
    current_line = []

    for token in tokens:
        text = token.get("text", "")
        if not text or text == "<end>":
            continue

        speaker = token.get("speaker")

        if include_speakers and speaker and speaker != current_speaker:
            if current_line:
                lines.append("".join(current_line).strip())
            current_speaker = speaker
            lines.append(f"\n[Speaker {speaker}]")
            current_line = [text]
        else:
            current_line.append(text)

    if current_line:
        lines.append("".join(current_line).strip())

    return "\n".join(lines).strip()


def tokens_to_srt(tokens: list[dict], segment_duration_ms: int = 5000) -> str:
    """Convert tokens to SRT subtitle format, grouped into segments."""
    if not tokens:
        return ""

    # Filter out empty tokens and <end> markers
    valid_tokens = [t for t in tokens if t.get("text") and t["text"] != "<end>"]
    if not valid_tokens:
        return ""

    segments = []
    current_segment_tokens = []
    segment_start_ms = valid_tokens[0].get("start_ms", 0)

    for token in valid_tokens:
        token_start = token.get("start_ms", 0)

        # Start new segment if duration exceeded
        if current_segment_tokens and (token_start - segment_start_ms) >= segment_duration_ms:
            segment_end_ms = current_segment_tokens[-1].get("end_ms", token_start)
            text = "".join(t.get("text", "") for t in current_segment_tokens).strip()
            if text:
                segments.append((segment_start_ms, segment_end_ms, text))
            current_segment_tokens = []
            segment_start_ms = token_start

        current_segment_tokens.append(token)

    # Last segment
    if current_segment_tokens:
        segment_end_ms = current_segment_tokens[-1].get("end_ms", segment_start_ms)
        text = "".join(t.get("text", "") for t in current_segment_tokens).strip()
        if text:
            segments.append((segment_start_ms, segment_end_ms, text))

    # Build SRT
    srt_lines = []
    for i, (start, end, text) in enumerate(segments, 1):
        srt_lines.append(str(i))
        srt_lines.append(f"{format_timestamp_srt(start)} --> {format_timestamp_srt(end)}")
        srt_lines.append(text)
        srt_lines.append("")

    return "\n".join(srt_lines)
