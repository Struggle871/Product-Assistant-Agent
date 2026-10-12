from app.rag.parsers import parse_document, parse_html, parse_markdown


def test_markdown_preserves_heading_structure() -> None:
    parsed = parse_markdown(b"# Setup\nConnect the power.\n## Reset\nHold reset.")

    assert parsed.page_count == 1
    assert [(section.heading, section.text) for section in parsed.sections] == [
        ("Setup", "Connect the power."),
        ("Reset", "Hold reset."),
    ]


def test_html_removes_scripts_and_keeps_sections() -> None:
    parsed = parse_html(
        b"<h1>Setup</h1><p>Connect Wi-Fi.</p><script>ignore me</script>"
    )

    assert parsed.sections[0].heading == "Setup"
    assert parsed.sections[0].text == "Connect Wi-Fi."


def test_unsupported_document_type_is_rejected() -> None:
    try:
        parse_document(b"binary", "manual.docx", "application/msword")
    except ValueError as exc:
        assert "Unsupported document format" in str(exc)
    else:
        raise AssertionError("Unsupported input must fail")
