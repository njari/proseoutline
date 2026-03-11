import re
import subprocess
from datetime import datetime
from pathlib import Path

OUTLINES_DIR = Path(__file__).parent / "outlines"


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def git_run(*args, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def init_article_repo(article_dir: Path):
    """Each article gets its own git repo at outlines/<slug>/."""
    article_dir.mkdir(parents=True, exist_ok=True)
    if not (article_dir / ".git").exists():
        git_run("init", "-b", "main", cwd=article_dir)
        git_run("config", "user.email", "minirag@local", cwd=article_dir)
        git_run("config", "user.name", "minirag", cwd=article_dir)
        (article_dir / "outline.md").touch()
        git_run("add", "outline.md", cwd=article_dir)
        git_run("commit", "-m", "init", cwd=article_dir)


def list_articles(outlines_dir: Path) -> list[dict]:
    """Each subdirectory with a .git is an article."""
    outlines_dir.mkdir(exist_ok=True)
    articles = []
    for article_dir in sorted(d for d in outlines_dir.iterdir() if d.is_dir() and (d / ".git").exists()):
        slug = article_dir.name
        try:
            raw = git_run("branch", "--all", cwd=article_dir)
            branches = [
                b.strip().lstrip("* ").replace("remotes/origin/", "")
                for b in raw.splitlines()
                if b.strip()
            ]
        except RuntimeError:
            branches = ["main"]
        articles.append({"slug": slug, "dir": article_dir, "branches": branches})
    return articles


def save_outline(outlines_dir: Path, slug: str, topic: str, branch: str, content: str) -> str:
    article_dir = outlines_dir / slug
    init_article_repo(article_dir)
    git_run("checkout", "-B", branch, cwd=article_dir)
    frontmatter = (
        f"---\n"
        f"topic: {topic}\n"
        f"generated: {datetime.now().isoformat(timespec='seconds')}\n"
        f"branch: {branch}\n"
        f"---\n\n"
    )
    (article_dir / "outline.md").write_text(frontmatter + content, encoding="utf-8")
    git_run("add", "outline.md", cwd=article_dir)
    git_run("commit", "-m", f"{branch}: {topic}", cwd=article_dir)
    return git_run("rev-parse", "--short", "HEAD", cwd=article_dir)


def read_article(outlines_dir: Path, slug: str, branch: str) -> str:
    """Read content for a branch without modifying the working tree."""
    article_dir = outlines_dir / slug
    return git_run("show", f"{branch}:outline.md", cwd=article_dir)


def commit_edit(outlines_dir: Path, slug: str, branch: str, content: str) -> str:
    """Commit manually edited content, initialising the repo if needed."""
    article_dir = outlines_dir / slug
    init_article_repo(article_dir)
    git_run("checkout", branch, cwd=article_dir)
    (article_dir / "outline.md").write_text(content, encoding="utf-8")
    git_run("add", "outline.md", cwd=article_dir)
    git_run("commit", "-m", f"{branch}: manual edit", cwd=article_dir)
    return git_run("rev-parse", "--short", "HEAD", cwd=article_dir)


def show_article(outlines_dir: Path, slug: str, branch: str):
    article_dir = outlines_dir / slug
    git_run("checkout", branch, cwd=article_dir)
    print((article_dir / "outline.md").read_text(encoding="utf-8"))
