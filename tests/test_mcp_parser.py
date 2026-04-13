from reddit_digest.nodes.mcp_parser import parse_post_comments, parse_top_posts

TOP_POSTS_FIXTURE = """\
# Top Posts from r/python (hot)

### 1. Building a CLI Tool with Click
- Author: u/dev_user
- Score: 1,234 (95.0% upvoted)
- Comments: 45
- Posted: 4/12/2026, 10:00:00 AM
- Link: https://reddit.com/r/python/comments/abc123/building_a_cli_tool/

### 2. Python 3.13 Release Notes
- Author: u/py_news
- Score: 892 (91.2% upvoted)
- Comments: 120
- Posted: 4/11/2026, 8:00:00 AM
- Link: https://redd.it/def456
"""

COMMENTS_FIXTURE = """\
# Comments for: Building a CLI Tool with Click

## Post Details
- Author: u/dev_user
- Subreddit: r/python
- Score: 1234 (95.0% upvoted)
- Posted: 4/12/2026, 10:00:00 AM
- Link: https://reddit.com/r/python/comments/abc123/building_a_cli_tool/

## Post Content
Check out my new CLI tool built with Click...

## Comments (4 loaded, sorted by best)

**u/commenter1** \u2022 89 points \u2022 4/12/2026, 11:00:00 AM
Great tutorial! I've been looking for something like this.

---

  \u2514\u2500 **u/dev_user** \u2022 45 points \u2022 4/12/2026, 11:30:00 AM
  Thanks! Let me know if you have questions.

---

**u/commenter2** \u2022 67 points \u2022 4/12/2026, 12:00:00 PM
Have you considered using Typer instead? It's built on Click.

---

**u/commenter3** \u2022 23 points \u2022 4/12/2026, 1:00:00 PM
Nice work, bookmarked for later.
"""


class TestParseTopPosts:
    def test_parses_multiple_posts(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        assert len(posts) == 2

    def test_extracts_title(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        assert posts[0].title == "Building a CLI Tool with Click"

    def test_extracts_score_with_commas(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        assert posts[0].score == 1234

    def test_extracts_num_comments(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        assert posts[0].num_comments == 45

    def test_extracts_reddit_id_from_permalink(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        assert posts[0].reddit_id == "abc123"

    def test_extracts_reddit_id_from_short_link(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        assert posts[1].reddit_id == "def456"

    def test_extracts_url(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        assert (
            posts[0].url
            == "https://reddit.com/r/python/comments/abc123/building_a_cli_tool/"
        )

    def test_sets_subreddit(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        assert posts[0].subreddit == "python"
        assert posts[1].subreddit == "python"

    def test_empty_input(self):
        assert parse_top_posts("", "python") == []

    def test_malformed_input(self):
        assert parse_top_posts("No posts found", "python") == []


class TestParsePostComments:
    def test_extracts_comments(self):
        comments = parse_post_comments(COMMENTS_FIXTURE)
        assert len(comments) == 4

    def test_comment_bodies_only(self):
        comments = parse_post_comments(COMMENTS_FIXTURE)
        assert (
            comments[0] == "Great tutorial! I've been looking for something like this."
        )

    def test_nested_reply_body(self):
        comments = parse_post_comments(COMMENTS_FIXTURE)
        assert comments[1] == "Thanks! Let me know if you have questions."

    def test_empty_input(self):
        assert parse_post_comments("") == []

    def test_no_comments_section(self):
        assert parse_post_comments("# Some post\n\nNo comments here") == []

    def test_respects_limit(self):
        comments = parse_post_comments(COMMENTS_FIXTURE, limit=2)
        assert len(comments) == 2
