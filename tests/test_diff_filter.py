from pr_description import diff_filter


def test_parse_patterns_splits_and_strips():
    assert diff_filter.parse_patterns(" *.lock, dist/* ,") == ["*.lock", "dist/*"]


def test_parse_patterns_empty():
    assert diff_filter.parse_patterns("") == []


def test_is_excluded_matches_glob():
    patterns = ["*.lock", "dist/*"]
    assert diff_filter.is_excluded("yarn.lock", patterns)
    assert diff_filter.is_excluded("dist/bundle.js", patterns)
    assert not diff_filter.is_excluded("src/main.py", patterns)


def test_build_diff_prompt_skips_files_without_patch():
    files = [{"filename": "image.png"}]  # no "patch" key, e.g. binary file
    prompt = diff_filter.build_diff_prompt(files, [], 1000, "gpt-4o-mini")
    assert prompt == ""


def test_build_diff_prompt_excludes_matching_files():
    files = [
        {"filename": "package-lock.json", "patch": "+++ huge generated diff"},
        {"filename": "src/app.py", "patch": "@@ -1,1 +1,2 @@\n+print('hi')"},
    ]
    prompt = diff_filter.build_diff_prompt(
        files, ["package-lock.json"], 1000, "gpt-4o-mini"
    )
    assert "package-lock.json" not in prompt
    assert "src/app.py" in prompt


def test_build_diff_prompt_respects_token_budget():
    files = [{"filename": f"file{i}.py", "patch": "x" * 200} for i in range(20)]
    prompt = diff_filter.build_diff_prompt(files, [], 50, "gpt-4o-mini")
    encoding = diff_filter.get_encoding("gpt-4o-mini")
    assert diff_filter.count_tokens(prompt, encoding) <= 50


def test_get_encoding_falls_back_for_unknown_model():
    encoding = diff_filter.get_encoding("some-future-model-name")
    assert encoding is not None
    assert diff_filter.count_tokens("hello world", encoding) > 0


def test_build_diff_prompt_stops_once_budget_is_exactly_spent():
    encoding = diff_filter.get_encoding("gpt-4o-mini")
    first_chunk = "Changes in file a.py: +first\n"
    files = [
        {"filename": "a.py", "patch": "+first"},
        {"filename": "b.py", "patch": "+second"},
    ]
    budget = diff_filter.count_tokens(first_chunk, encoding)

    prompt = diff_filter.build_diff_prompt(files, [], budget, "gpt-4o-mini")

    assert prompt == first_chunk
