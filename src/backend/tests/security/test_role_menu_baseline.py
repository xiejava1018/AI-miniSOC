"""
角色菜单基线测试（PRD §10.4 P0-T15）

覆盖：
- 导出脚本能跑通、JSON 结构正确
- 应用脚本 ``--check`` 与 ``--apply`` 互相幂等
- drift 报告在 baseline 与 DB 不一致时非空
- 不修改 ``soc_users.role_id``（脚本不得触碰用户角色）
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

from sqlalchemy.orm import Session

from app.models import RoleMenu

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
SCRIPTS_DIR = os.path.join(BACKEND_DIR, "scripts", "security")
EXPORT_SCRIPT = os.path.join(SCRIPTS_DIR, "export_role_menu_baseline.py")
SEED_SCRIPT = os.path.join(SCRIPTS_DIR, "seed_role_menu_baseline.py")
DEFAULT_BASELINE = os.path.join(BACKEND_DIR, "scripts", "data", "role_menu_baseline.v1.json")


# ---------------------------------------------------------------------------
# 导出脚本测试
# ---------------------------------------------------------------------------

class TestExportScript:
    def test_managed_roles_printed(self):
        """``--print-managed-roles`` 输出受管角色清单。"""
        result = subprocess.run(
            [sys.executable, EXPORT_SCRIPT, "--print-managed-roles"],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        assert "admin" in payload["managed_roles"]
        assert "operator" in payload["managed_roles"]
        assert "viewer" in payload["managed_roles"]
        assert "auditor" in payload["managed_roles"]
        assert "user" in payload["managed_roles"]
        # disabled
        assert "readonly" in payload["disabled_roles"]
        assert "test_role" in payload["disabled_roles"]

    def test_export_writes_json_file(self, tmp_path):
        """``--export FILE`` 写入目标文件且包含受管角色数据。"""
        out = tmp_path / "baseline.json"
        subprocess.run(
            [sys.executable, EXPORT_SCRIPT, "--export", str(out)],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        assert out.exists()
        with open(out) as f:
            data = json.load(f)
        assert data["version"] == "v1"
        assert "roles" in data
        assert "admin" in data["roles"]
        assert "operator" in data["roles"]


# ---------------------------------------------------------------------------
# Seed 脚本测试
# ---------------------------------------------------------------------------

class TestSeedScript:
    def test_check_clean_returns_zero(self):
        """当前 DB 与基线一致时，``--check`` 返回 0。"""
        result = subprocess.run(
            [sys.executable, SEED_SCRIPT, "--check"],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"--check should exit 0 on clean DB; got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_dry_run_no_side_effects(self):
        """``--dry-run`` 不修改数据库。"""
        # 记录 user 角色的 menu 数
        from app.core.database import SessionLocal
        from app.models import Role as RoleModel

        db = SessionLocal()
        try:
            user_role = db.query(RoleModel).filter(RoleModel.code == "user").first()
            before = db.query(RoleMenu).filter(RoleMenu.role_id == user_role.id).count()
        finally:
            db.close()

        result = subprocess.run(
            [sys.executable, SEED_SCRIPT, "--dry-run"],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        db = SessionLocal()
        try:
            user_role = db.query(RoleModel).filter(RoleModel.code == "user").first()
            after = db.query(RoleMenu).filter(RoleMenu.role_id == user_role.id).count()
        finally:
            db.close()
        assert before == after, f"dry-run changed DB: {before} -> {after}"

    def test_apply_is_idempotent(self):
        """连续两次 ``--apply`` 行为一致。"""
        # 第一次 apply
        r1 = subprocess.run(
            [sys.executable, SEED_SCRIPT, "--apply"],
            cwd=BACKEND_DIR, capture_output=True, text=True,
        )
        assert r1.returncode == 0, f"first apply failed: {r1.stderr}"

        # 第二次 apply 应无新动作
        r2 = subprocess.run(
            [sys.executable, SEED_SCRIPT, "--apply"],
            cwd=BACKEND_DIR, capture_output=True, text=True,
        )
        assert r2.returncode == 0
        # 第二次 apply 的 drift 报告应为空
        assert "add: 0" in r2.stdout
        assert "remove: 0" in r2.stdout

    def test_check_after_apply_returns_zero(self):
        """``--apply`` 后 ``--check`` 返回 0。"""
        subprocess.run(
            [sys.executable, SEED_SCRIPT, "--apply"],
            cwd=BACKEND_DIR, capture_output=True, text=True, check=True,
        )
        r = subprocess.run(
            [sys.executable, SEED_SCRIPT, "--check"],
            cwd=BACKEND_DIR, capture_output=True, text=True,
        )
        assert r.returncode == 0

    def test_drift_detected_on_modified_baseline(self, tmp_path):
        """修改基线后 ``--check`` 应报 drift（exit 2）。"""
        # 复制基线到 tmp
        modified = tmp_path / "drift.json"
        shutil.copy(DEFAULT_BASELINE, modified)

        # 修改基线：移除 viewer 的某条菜单
        with open(modified) as f:
            data = json.load(f)
        # 删除 viewer 的 dashboard 菜单（保证 locator 唯一）
        data["roles"]["viewer"]["menus"] = [
            m for m in data["roles"]["viewer"]["menus"]
            if m["locator"] != "/dashboard"
        ]
        with open(modified, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        r = subprocess.run(
            [sys.executable, SEED_SCRIPT, "--check", "--baseline", str(modified)],
            cwd=BACKEND_DIR, capture_output=True, text=True,
        )
        assert r.returncode == 2, (
            f"--check should exit 2 on drift, got {r.returncode}\n"
            f"stdout: {r.stdout}"
        )
        # drift 报告里应该提到 dashboard
        assert "/dashboard" in r.stdout


# ---------------------------------------------------------------------------
# 不修改用户角色
# ---------------------------------------------------------------------------

class TestUserRolesUntouched:
    def test_apply_does_not_modify_user_role_id(self, db_session: Session):
        """seed 脚本运行后任何 ``soc_users.role_id`` 不应改变。

        由于 ``apply_baseline`` 是单独进程运行，这里验证：脚本逻辑本身不引用
        ``soc_users`` 表的写操作。通过静态扫描源文件确认（跳过注释/文档字符串）。
        """
        import re
        with open(SEED_SCRIPT) as f:
            source = f.read()

        # 移除所有 docstring 与注释后再扫描
        no_docstring = re.sub(r'""".*?"""', '', source, flags=re.DOTALL)
        no_comments = re.sub(r'#[^\n]*', '', no_docstring)

        # 不应有 User 模型的 import
        assert not re.search(r"from\s+app\.models\s+import\s+.*User", no_comments), (
            "seed script must NOT import User model"
        )
        # 不应有 soc_users 表的直接引用（排除注释）
        assert "soc_users" not in no_comments, (
            "seed script must NOT reference soc_users table"
        )