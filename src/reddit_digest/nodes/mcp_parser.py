"""Parser for reddit-mcp-server text output."""

from __future__ import annotations

import re

from reddit_digest.models import RedditPost


def _extract_reddit_id(url: str) -> str | None:
    """Extract the Reddit post ID from a short or full link.

    Supports:
    - https://redd.it/{id}
    - https://reddit.com/r/{sub}/comments/{id}/...
    """
    # Short link: https://redd.it/{id}
    m = re.match(r"https?://redd\.it/(\w+)", url)
    if m:
        return m.group(1)
    # Full permalink: https://reddit.com/r/{sub}/comments/{id}/...
    m = re.search(r"/comments/(\w+)", url)
    if m:
        return m.group(1)
    return None


def parse_top_posts(text: str, subreddit: str) -> list[RedditPost]:
    """Parse get_top_posts text output into RedditPost objects.

    Must extract: title, score, num_comments, reddit_id (from link), url (the link).
    Sets subreddit from parameter, created_utc=0.0, top_comments=[].
    """
    if not text.strip():
        return []

    posts: list[RedditPost] = []

    # Split into post blocks using ### N. pattern
    post_blocks = re.split(r"(?=^### \d+\. )", text, flags=re.MULTILINE)

    for block in post_blocks:
        block = block.strip()
        if not block.startswith("### "):
            continue

        # Extract title: ### N. {title}
        title_match = re.match(r"### \d+\.\s+(.+)", block)
        if not title_match:
            continue
        title = title_match.group(1).strip()

        # Extract score
        score_match = re.search(r"^- Score:\s*([\d,]+)", block, re.MULTILINE)
        if not score_match:
            continue
        score = int(score_match.group(1).replace(",", ""))

        # Extract num_comments
        comments_match = re.search(r"^- Comments:\s*([\d,]+)", block, re.MULTILINE)
        if not comments_match:
            continue
        num_comments = int(comments_match.group(1).replace(",", ""))

        # Extract link
        link_match = re.search(r"^- Link:\s*(\S+)", block, re.MULTILINE)
        if not link_match:
            continue
        url = link_match.group(1).strip()

        # Extract reddit_id from link
        reddit_id = _extract_reddit_id(url)
        if not reddit_id:
            continue

        posts.append(
            RedditPost(
                reddit_id=reddit_id,
                subreddit=subreddit,
                title=title,
                url=url,
                score=score,
                num_comments=num_comments,
            )
        )

    return posts


def parse_post_comments(text: str, limit: int | None = None) -> list[str]:
    """Parse get_post_comments text output into comment body strings.

    Extracts all comment bodies (top-level and replies).
    Returns just the body text, not metadata.
    """
    if not text.strip():
        return []

    # Find the comments section
    comments_section_match = re.search(
        r"^## Comments\b.*?\n(.*)", text, re.MULTILINE | re.DOTALL
    )
    if not comments_section_match:
        return []

    comments_text = comments_section_match.group(1)

    # Split by --- separator
    blocks = re.split(r"^---\s*$", comments_text, flags=re.MULTILINE)

    comments: list[str] = []
    # Pattern for comment header: optional indent + optional └─ + **u/{author}** • ...
    header_pattern = re.compile(
        r"^\s*(?:└─\s*)?[*]{2}u/\w+[*]{2}\s*•\s*\d+\s+points?\s*•\s*.+$",
        re.MULTILINE,
    )

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        m = header_pattern.search(block)
        if not m:
            continue

        # The body is everything after the header line
        body = block[m.end() :].strip()
        if body:
            comments.append(body)

        if limit is not None and len(comments) >= limit:
            break

    return comments
