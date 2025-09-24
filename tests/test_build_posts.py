import json
import pathlib

from autopost import build_posts


def _write_hot_index(base: pathlib.Path, relative: str, items: list[dict]) -> None:
    path = base.joinpath(*[part for part in relative.split("/") if part], "index.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"items": items, "count": len(items)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_json(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_build_posts_deduplicates_and_sorts(tmp_path):
    data_dir = tmp_path / "data"
    hot_dir = data_dir / "hot"
    taxonomy_path = data_dir / "taxonomy.json"
    alias_path = hot_dir / "category_aliases.json"

    _write_json(
        taxonomy_path,
        {
            "categories": [
                {"slug": "news", "title": "News"},
                {"slug": "politics", "title": "Politics"},
                {"slug": "general", "title": "General"},
            ]
        },
    )

    _write_json(
        alias_path,
        {
            "standard_child": "general",
            "aliases": {
                "news/index": "news/general",
                "index/index": "index/general",
            },
        },
    )

    _write_hot_index(
        hot_dir,
        "news/politics",
        [
            {
                "slug": "story-a",
                "title": "Story A",
                "canonical": "https://aventuroo.local/story-a",
                "source": "https://publisher.example/a",
                "date": "2024-05-10T08:00:00Z",
                "excerpt": "Summary A",
                "cover": "https://images.example/a.jpg",
            },
            {
                "slug": "story-b",
                "title": "Story B",
                "canonical": "https://aventuroo.local/story-b",
                "source": "https://publisher.example/b",
                "date": "2024-05-09",
                "excerpt": "Summary B",
                "cover": "https://images.example/b.jpg",
            },
        ],
    )

    # Duplicate of story-a with a weaker scope to ensure weight comparison works
    _write_hot_index(
        hot_dir,
        "news/index",
        [
            {
                "slug": "story-a",
                "title": "Story A (duplicate)",
                "canonical": "https://aventuroo.local/story-a",
                "source": "https://publisher.example/a",
                "date": "2024-05-01",
                "excerpt": "Alt summary",
                "cover": "https://images.example/a-alt.jpg",
            }
        ],
    )

    _write_hot_index(
        hot_dir,
        "index",
        [
            {
                "slug": "story-c",
                "title": "Story C",
                "canonical": "https://aventuroo.local/story-c",
                "source": "https://publisher.example/c",
                "date": "2024-05-08T12:30:00Z",
                "excerpt": "Summary C",
                "cover": "https://images.example/c.jpg",
            }
        ],
    )

    posts = build_posts.build_posts(
        hot_dir=hot_dir,
        taxonomy_path=taxonomy_path,
        alias_path=alias_path,
        limit=500,
    )

    assert [post["id"] for post in posts] == ["story-a", "story-b", "story-c"]

    story_a = posts[0]
    assert story_a["category"] == "News"
    assert story_a["subcategory"] == "Politics"
    assert story_a["thumbnail"] == "https://images.example/a.jpg"
    assert story_a["published_at"].startswith("2024-05-10")

    story_c = posts[2]
    assert story_c["category"] == "General"
    assert story_c["subcategory"] == ""

    limited = build_posts.build_posts(
        hot_dir=hot_dir,
        taxonomy_path=taxonomy_path,
        alias_path=alias_path,
        limit=2,
    )
    assert [post["id"] for post in limited] == ["story-a", "story-b"]


def test_build_posts_main(tmp_path, capsys):
    data_dir = tmp_path / "data"
    hot_dir = data_dir / "hot"
    taxonomy_path = data_dir / "taxonomy.json"
    alias_path = hot_dir / "category_aliases.json"
    output_path = data_dir / "posts.json"

    _write_json(
        taxonomy_path,
        {"categories": [{"slug": "news", "title": "News"}, {"slug": "general", "title": "General"}]},
    )
    _write_json(alias_path, {"standard_child": "general", "aliases": {}})

    _write_hot_index(
        hot_dir,
        "news",
        [
            {
                "slug": "story-d",
                "title": "Story D",
                "canonical": "https://aventuroo.local/story-d",
                "source": "https://publisher.example/d",
                "date": "2024-05-07",
                "excerpt": "Summary D",
                "cover": "https://images.example/d.jpg",
            }
        ],
    )

    exit_code = build_posts.main(
        [
            "--hot-dir",
            str(hot_dir),
            "--taxonomy",
            str(taxonomy_path),
            "--aliases",
            str(alias_path),
            "--output",
            str(output_path),
            "--limit",
            "10",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Wrote 1 posts" in captured.out

    stored = json.loads(output_path.read_text(encoding="utf-8"))
    assert stored == build_posts.build_posts(
        hot_dir=hot_dir,
        taxonomy_path=taxonomy_path,
        alias_path=alias_path,
        limit=10,
    )
