"""Regression tests for GitHub issue #12 — fresh-install bootstrap.

Covers the four reported problems:
  1. no default account/password
  2. `alembic upgrade head` errors on a fresh DB
  3. frontend 500 after DB init (menu tree missing -> no dynamic routes)
  4. install.sh missing compose file path (static check)

These tests deliberately avoid external services (no OpenSearch/Wazuh/LLM),
so they run offline against a freshly migrated scratch database.

Run with:
    DB_NAME=<scratch-db> pytest tests/test_fresh_install_bootstrap.py
"""
import os
import re
import subprocess
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(BACKEND))
VERSIONS = os.path.join(BACKEND, "alembic", "versions")

sqlalchemy = pytest.importorskip("sqlalchemy")


# --------------------------------------------------------------------------
# Static checks: no migration may pin a menu/role row to a literal id.
# CLAUDE.md §4.3 red line #2. These run without a DB.
# --------------------------------------------------------------------------

# Literal ids that exist only because production was hand-seeded. If a
# migration seeds them, a fresh DB assigns different ids and the migration
# silently no-ops (or corrupts an unrelated row).
FORBIDDEN_LITERAL_PATTERNS = [
    r"parent_id\s*=\s*(?:2|5|22)\b(?!\s*=\s*None)",
    r"SELECT\s+(?:2|5|22)\s*,\s*'",
    r"WHERE\s+id\s*=\s*(?:2|5|22)\b",
    # `... ON p.id = 22` / `ON m.parent_id = 22` style joins to a literal id
    r"\b(?:m|p)\.(?:parent_)?id\s*=\s*(?:2|5|22)\b",
]


def _module_assignments(path: str) -> dict:
    """Return {name: value} for top-level assignments, via AST.

    Structural parsing beats regex here: docstrings and comments can never
    masquerade as `revision = ...`, and tuple-valued `down_revision` is
    handled natively.
    """
    import ast

    tree = ast.parse(open(path, encoding="utf-8").read())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    try:
                        out[target.id] = ast.literal_eval(node.value)
                    except (ValueError, SyntaxError):
                        out[target.id] = None
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                try:
                    out[node.target.id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    out[node.target.id] = None
    return out


def _as_revs(down_revision):
    """Normalize a down_revision value (str | tuple | None) to a list of str."""
    if down_revision is None:
        return []
    if isinstance(down_revision, str):
        return [down_revision]
    return [x for x in down_revision if isinstance(x, str)]


def _strip_comments_and_docstrings(src: str) -> str:
    """Blank out module/function docstrings so prose can't trip the scans.

    Uses AST to locate docstring nodes precisely, then replaces just those
    character ranges with spaces. Comments are blanked from `#` up to the
    end of the line, which is safe here because none of the SQL we scan for
    contains a `#`.
    """
    import ast

    spans = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            spans.append(
                (first.value.lineno, first.value.col_offset,
                 first.value.end_lineno, first.value.end_col_offset)
            )

    lines = src.splitlines(keepends=True)
    offsets, running = [], 0
    for ln in lines:
        offsets.append(running)
        running += len(ln)

    chars = list(src)
    for (r1, c1, r2, c2) in spans:
        start = offsets[r1 - 1] + c1
        end = offsets[r2 - 1] + c2
        for i in range(start, min(end, len(chars))):
            if chars[i] != "\n":
                chars[i] = " "
    text = "".join(chars)

    # blank `#` comments
    out = []
    for raw in text.splitlines(keepends=True):
        idx = raw.find("#")
        out.append(raw if idx == -1 else raw[:idx])
    return "".join(out)


def _migration_files():
    return [
        os.path.join(VERSIONS, f)
        for f in sorted(os.listdir(VERSIONS))
        if f.endswith(".py")
    ]


def test_no_migration_hardcodes_menu_parent_id():
    """Menus must be located by path, never by numeric id (issue #12 root cause)."""
    offenders = []
    for path in _migration_files():
        src = open(path, encoding="utf-8").read()
        upgrade = src.split("def downgrade")[0]
        code = _strip_comments_and_docstrings(upgrade)
        for pat in FORBIDDEN_LITERAL_PATTERNS:
            for m in re.finditer(pat, code):
                offenders.append(
                    "%s: %s" % (os.path.basename(path), m.group(0).strip())
                )
    assert not offenders, (
        "hardcoded menu ids found (fresh DB assigns different ids):\n  "
        + "\n  ".join(offenders)
    )


def test_alembic_has_single_head():
    """`upgrade head` only works with exactly one head (issue #12 '2').

    Mirrors alembic's own resolution: heads with no child, minus merge points.
    """
    revs, downs = {}, {}
    for path in _migration_files():
        assigns = _module_assignments(path)
        rev = assigns.get("revision")
        if not rev:
            continue
        revs[rev] = path
        downs[rev] = assigns.get("down_revision")

    children = {}
    for rev, dv in downs.items():
        for parent in _as_revs(dv):
            if parent in revs:
                children.setdefault(parent, []).append(rev)

    # Walk BACKWARDS from each head via down_revision links: every revision must
    # be an ancestor of some head, otherwise `upgrade head` never applies it.
    heads = [r for r in revs if r not in children]
    reachable, stack = set(), list(heads)
    while stack:
        rev = stack.pop()
        if rev in reachable:
            continue
        reachable.add(rev)
        for parent in _as_revs(downs.get(rev)):
            if parent in revs:
                stack.append(parent)

    orphans = sorted(set(revs) - reachable)
    assert not orphans, (
        "revisions unreachable from any head (never applied by `upgrade head`): %s"
        % [os.path.basename(revs[o]) for o in orphans]
    )

    assert len(heads) == 1, "expected exactly 1 alembic head, got %d: %s" % (
        len(heads),
        [os.path.basename(revs[h]) for h in heads],
    )


def test_every_orm_table_is_created_by_some_migration():
    """Tables living only in the ORM break `upgrade head` on a fresh DB."""
    import glob

    created = set()
    for path in _migration_files():
        src = open(path, encoding="utf-8").read()
        up = src.split("def downgrade")[0]
        created |= set(re.findall(r'create_table\(\s*["\']([a-z_0-9]+)["\']', up))
        created |= set(
            re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?([a-z_0-9]+)", up, re.I)
        )
        # metadata-driven create_all migrations declare their tables in a
        # `_TABLES`-style literal right above the loop.
        for block in re.findall(r"_TABLES\w*\s*=\s*[\(\[](.*?)[\)\]]", up, re.S):
            created |= set(re.findall(r'["\'](soc_[a-z_0-9]+)["\']', block))

    orm = set()
    for path in glob.glob(os.path.join(BACKEND, "app", "models", "*.py")):
        src = open(path, encoding="utf-8").read()
        orm |= set(
            re.findall(r'__tablename__\s*=\s*["\']([a-z_0-9]+)["\']', src)
        )

    missing = sorted(t for t in orm if t not in created)
    assert not missing, (
        "ORM tables no migration creates (fresh DB will fail): %s" % missing
    )


def test_admin_password_resolves_from_root_env_file():
    """DEFAULT_ADMIN_PASSWORD must be read from the REPO ROOT .env.

    Regression: alembic/env.py does a bare load_dotenv(), whose find_dotenv()
    walks up from the cwd and stops at src/backend/.env. A deployment that
    follows the README and puts DEFAULT_ADMIN_PASSWORD in the root .env
    therefore silently got the factory password instead.

    We assert the migration's resolver picks up a value that exists ONLY in a
    root .env, with src/backend/.env shadowing it.
    """
    import ast
    import textwrap

    mig = os.path.join(
        VERSIONS, "u0a1b2c3d4e5_bootstrap_roles_and_admin.py"
    )
    assert os.path.exists(mig), "admin bootstrap migration missing"
    src = open(mig, encoding="utf-8").read()

    tree = ast.parse(src)
    fn = next(
        (n for n in tree.body
         if isinstance(n, ast.FunctionDef) and n.name == "_admin_password"),
        None,
    )
    assert fn is not None, "_admin_password() resolver not found"

    # Exercise the resolver in isolation against a synthetic repo layout.
    import subprocess
    import tempfile

    snippet = textwrap.dedent(
        """
        import os, sys
        from pathlib import Path

        def _admin_password():
            for candidate in (
                Path(sys.argv[1]).resolve() / ".env",
                Path(sys.argv[2]).resolve() / ".env",
            ):
                if candidate.is_file():
                    try:
                        from dotenv import load_dotenv
                        load_dotenv(candidate, override=False)
                    except Exception:
                        pass
            return os.getenv("DEFAULT_ADMIN_PASSWORD") or "Admin@123456"
        print(_admin_password())
        """
    )
    with tempfile.TemporaryDirectory() as td:
        root = os.path.join(td, "repo")
        backend = os.path.join(root, "src", "backend")
        os.makedirs(backend)
        # Root .env carries the password; src/backend/.env shadows it and does not.
        with open(os.path.join(root, ".env"), "w") as fh:
            fh.write("DEFAULT_ADMIN_PASSWORD=FromRootEnv@777\n")
        with open(os.path.join(backend, ".env"), "w") as fh:
            fh.write("DB_NAME=whatever\n")

        out = subprocess.run(
            [sys.executable, "-c", snippet, root, backend],
            capture_output=True, text=True,
            # ensure a stray ambient value cannot mask a failure
            env={"PATH": os.environ.get("PATH", ""),
                 "PYTHONPATH": os.path.dirname(os.path.dirname(mig))},
        )
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == "FromRootEnv@777", (
            "root .env DEFAULT_ADMIN_PASSWORD was ignored; got %r"
            % out.stdout.strip()
        )


def test_bootstrap_migrations_are_present():
    """The three baselines issue #12 added must not be deleted.

    Their absence is what made a fresh install produce an unusable database:
    no scanner tables (migration crash), no menu tree (frontend 500), no
    login (no account). Static analysis can't infer that, so assert presence.
    """
    required = {
        "k0m1n2o3p4q5": "menu baseline (frontend 500 fix)",
        "s1a2b3c4d5e6": "scanner tables baseline (upgrade head fix)",
        "u0a1b2c3d4e5": "roles + default admin bootstrap (login fix)",
        "n0b1c2d3e4f5": "menu dedupe (duplicate routes fix)",
    }
    present = set()
    for path in _migration_files():
        present.add(_module_assignments(path).get("revision"))
    missing = {r: why for r, why in required.items() if r not in present}
    assert not missing, "bootstrap migrations missing: %s" % missing


def test_install_script_points_at_existing_compose_file():
    """issue #12 '3': install.sh ran docker-compose from the repo root."""
    script = os.path.join(REPO, "scripts", "install", "install.sh")
    assert os.path.exists(script), "install.sh missing"

    src = open(script, encoding="utf-8").read()

    # Must derive the compose path rather than assuming the cwd.
    assert "docker-compose.yaml" in src
    # Every compose invocation goes through the -f flag.
    bare = re.findall(r'"\$\{COMPOSE_CMD\[\@\]\}"\s+(?!-f)', src)
    assert not bare, "docker compose invoked without -f <compose file>"
    assert "COMPOSE_FILE=" in src

    # The referenced file must actually exist in the repo.
    m = re.search(r'COMPOSE_FILE="\$\{COLLECTORS_DIR\}/([^"]+)"', src)
    assert m, "COMPOSE_FILE not derived from COLLECTORS_DIR"
    assert os.path.exists(os.path.join(REPO, "src", "collectors", m.group(1))), (
        "install.sh points at a non-existent compose file: %s" % m.group(1)
    )


def test_install_script_documents_default_login():
    """issue #12 '1': the installer must print AI-miniSOC's own credentials."""
    src = open(
        os.path.join(REPO, "scripts", "install", "install.sh"), encoding="utf-8"
    ).read()
    assert "admin" in src
    assert re.search(r"Admin@123456|DEFAULT_ADMIN_PASSWORD", src), (
        "install.sh must state the default admin password"
    )


# --------------------------------------------------------------------------
# DB-backed checks. Skipped unless pointed at a migrated scratch database.
# --------------------------------------------------------------------------

def _db_available():
    if not os.getenv("DB_NAME"):
        return False
    try:
        import psycopg2

        from app.core.config import settings  # noqa: F401

        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT", "5432"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            dbname=os.getenv("DB_NAME"),
            connect_timeout=5,
        )
        conn.close()
        return True
    except Exception:
        return False


pytestmark_db = pytest.mark.skipif(
    not _db_available(), reason="needs DB_NAME pointing at a migrated database"
)


@pytestmark_db
def test_default_admin_can_authenticate():
    """The account the issue reporter could not find must actually work."""
    sys.path.insert(0, BACKEND)
    from sqlalchemy.orm import Session, joinedload

    from app.core.database import engine
    from app.core.security import verify_password
    from app.models import User

    expected_pw = os.getenv("DEFAULT_ADMIN_PASSWORD") or "Admin@123456"

    db = Session(engine)
    try:
        user = (
            db.query(User)
            .options(joinedload(User.role))
            .filter(User.username == "admin")
            .first()
        )
        assert user is not None, "no admin account was seeded"
        assert user.is_admin, "admin account is not an administrator"
        assert user.status == "active", "admin account is not active"
        assert verify_password(expected_pw, user.password_hash), (
            "default admin password does not verify"
        )
    finally:
        db.close()


@pytestmark_db
def test_x1_roles_are_seeded():
    sys.path.insert(0, BACKEND)
    from sqlalchemy.orm import Session

    from app.core.database import engine
    from app.models import Role

    db = Session(engine)
    try:
        codes = {r.code for r in db.query(Role).all()}
    finally:
        db.close()
    for required in ("admin", "operator", "viewer", "auditor"):
        assert required in codes, "role %r missing (X1 matrix incomplete)" % required


@pytestmark_db
def test_menu_tree_is_complete_and_admin_has_full_access():
    """Frontend registers routes from this tree; empty tree => every page 500."""
    sys.path.insert(0, BACKEND)
    from sqlalchemy.orm import Session

    from app.core.database import engine
    from app.models import Menu, Role, RoleMenu, User

    db = Session(engine)
    try:
        all_menus = db.query(Menu).all()
        roots = [m for m in all_menus if m.parent_id is None]

        assert len(roots) >= 10, (
            "expected the full top-level menu tree, got %d roots" % len(roots)
        )

        by_id = {m.id: m for m in all_menus}
        for m in all_menus:
            if m.parent_id is not None:
                assert m.parent_id in by_id, (
                    "menu %r references a parent outside the tree" % m.path
                )

        # No duplicate (parent, path) pairs -> no duplicate frontend routes.
        seen = set()
        for m in all_menus:
            key = (m.parent_id, m.path)
            assert key not in seen, "duplicate menu path %r under parent %s" % (
                m.path,
                m.parent_id,
            )
            seen.add(key)

        # admin must reach every menu, otherwise pages 500 behind the guard.
        admin = db.query(User).filter(User.username == "admin").first()
        granted = {
            rm.menu_id
            for rm in db.query(RoleMenu)
            .filter(RoleMenu.role_id == admin.role_id)
            .all()
        }
        missing = [m.path for m in all_menus if m.id not in granted]
        assert not missing, "admin cannot reach menus: %s" % missing[:10]
    finally:
        db.close()