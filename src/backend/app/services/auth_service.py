"""
认证服务
提供用户认证、会话管理、密码修改和菜单权限功能
"""
import hashlib
from datetime import datetime, timedelta
from typing import Tuple, Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.user import User, UserStatus
from app.models.user_session import UserSession
from app.models.password_history import PasswordHistory
from app.models.menu import Menu
from app.models.system_config import SystemConfig
from app.core.security import verify_password, get_password_hash, validate_password_strength
from app.core.auth import create_access_token, create_refresh_token
from app.core.audit import AuditService


class AuthService:
    """认证服务类，提供用户认证相关功能"""

    @staticmethod
    def authenticate_user(
        db: Session,
        username: str,
        password: str,
        ip_address: str = None,
        user_agent: str = None
    ) -> Tuple[Optional[User], Optional[str], Optional[Dict[str, Any]]]:
        """
        验证用户凭据并返回token数据

        Args:
            db: 数据库会话
            username: 用户名
            password: 密码
            ip_address: 登录IP地址
            user_agent: 用户代理

        Returns:
            Tuple[Optional[User], Optional[str], Optional[Dict]]:
            (用户对象, 错误消息, 令牌数据)
        """
        # 查询用户
        user = db.query(User).filter(User.username == username).first()

        # 用户名不存在
        if not user:
            AuditService.log(
                db=db,
                username=username,
                action="LOGIN_FAILED",
                resource_type="user",
                ip_address=ip_address,
                user_agent=user_agent,
                status="failure",
                error_message="用户不存在"
            )
            return None, "用户名或密码错误", None

        # 检查账户状态
        if user.status == UserStatus.DISABLED:
            AuditService.log(
                db=db,
                user_id=user.id,
                username=user.username,
                action="LOGIN_FAILED",
                resource_type="user",
                resource_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                status="failure",
                error_message="账户已被禁用"
            )
            return None, "账户已被禁用", None

        # 检查账户锁定
        if user.is_locked:
            # 获取配置检查是否已过锁定时间
            if user.locked_until and user.locked_until > datetime.now(user.locked_until.tzinfo):
                AuditService.log(
                    db=db,
                    user_id=user.id,
                    username=user.username,
                    action="LOGIN_FAILED",
                    resource_type="user",
                    resource_id=user.id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    status="failure",
                    error_message="账户已被锁定"
                )
                return None, f"账户已被锁定，请在 {user.locked_until} 后重试", None
            else:
                # 锁定时间已过，自动解锁
                user.status = UserStatus.ACTIVE
                user.locked_until = None
                user.failed_login_attempts = 0
                db.commit()

        # 获取登录配置
        max_attempts, lockout_minutes = AuthService._get_login_config(db)

        # 验证密码
        if not verify_password(password, user.password_hash):
            # 增加失败计数
            user.failed_login_attempts += 1

            # 检查是否超过最大尝试次数
            if user.failed_login_attempts >= max_attempts:
                user.status = UserStatus.LOCKED
                lockout_until = datetime.utcnow() + timedelta(minutes=lockout_minutes)
                user.locked_until = lockout_until
                db.commit()

                AuditService.log(
                    db=db,
                    user_id=user.id,
                    username=user.username,
                    action="LOGIN_LOCKOUT",
                    resource_type="user",
                    resource_id=user.id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    status="success",
                    details={"failed_attempts": user.failed_login_attempts, "lockout_minutes": lockout_minutes}
                )

                return None, f"连续{max_attempts}次密码错误，账户已锁定{lockout_minutes}分钟", None
            else:
                db.commit()

                AuditService.log(
                    db=db,
                    user_id=user.id,
                    username=user.username,
                    action="LOGIN_FAILED",
                    resource_type="user",
                    resource_id=user.id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    status="failure",
                    error_message="密码错误",
                    details={"failed_attempts": user.failed_login_attempts}
                )

                remaining = max_attempts - user.failed_login_attempts
                return None, f"密码错误，还有 {remaining} 次尝试机会", None

        # 密码验证成功，重置失败计数
        user.failed_login_attempts = 0
        user.last_login_at = datetime.utcnow()
        db.commit()

        # 生成JWT令牌
        token_data = {
            "access_token": create_access_token(
                data={
                    "sub": str(user.id),
                    "username": user.username,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role_id": user.role_id,
                    "role_name": user.role.code if user.role else None,
                    "is_admin": user.is_admin
                }
            ),
            "refresh_token": create_refresh_token(
                data={"sub": str(user.id)}
            ),
            "token_type": "bearer"
        }

        # 创建会话记录
        session = AuthService._create_session(
            db=db,
            user=user,
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            ip_address=ip_address,
            user_agent=user_agent
        )

        # 记录审计日志
        AuditService.log(
            db=db,
            user_id=user.id,
            username=user.username,
            action="LOGIN_SUCCESS",
            resource_type="user",
            resource_id=user.id,
            session_id=session.id,
            ip_address=ip_address,
            user_agent=user_agent,
            status="success"
        )

        return user, None, token_data

    @staticmethod
    def logout_user(
        db: Session,
        user: User,
        session_id: int,
        ip_address: str = None,
        user_agent: str = None
    ) -> None:
        """
        用户登出，标记会话为无效

        Args:
            db: 数据库会话
            user: 用户对象
            session_id: 会话ID
            ip_address: IP地址
            user_agent: 用户代理
        """
        session = db.query(UserSession).filter(
            and_(
                UserSession.id == session_id,
                UserSession.user_id == user.id
            )
        ).first()

        if session:
            session.is_active = False
            session.logout_at = datetime.utcnow()
            db.commit()

            AuditService.log(
                db=db,
                user_id=user.id,
                username=user.username,
                action="LOGOUT",
                resource_type="user_session",
                resource_id=session_id,
                ip_address=ip_address,
                user_agent=user_agent,
                session_id=session_id,
                status="success"
            )

    @staticmethod
    def change_password(
        db: Session,
        user: User,
        old_password: str,
        new_password: str,
        ip_address: str = None,
        user_agent: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        修改用户密码

        Args:
            db: 数据库会话
            user: 用户对象
            old_password: 旧密码
            new_password: 新密码
            ip_address: IP地址
            user_agent: 用户代理

        Returns:
            Tuple[bool, Optional[str]]: (是否成功, 错误消息)
        """
        # 验证旧密码
        if not verify_password(old_password, user.password_hash):
            AuditService.log(
                db=db,
                user_id=user.id,
                username=user.username,
                action="CHANGE_PASSWORD_FAILED",
                resource_type="user",
                resource_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                status="failure",
                error_message="旧密码验证失败"
            )
            return False, "旧密码错误"

        # 验证新密码强度
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            AuditService.log(
                db=db,
                user_id=user.id,
                username=user.username,
                action="CHANGE_PASSWORD_FAILED",
                resource_type="user",
                resource_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                status="failure",
                error_message=f"密码强度验证失败: {error_msg}"
            )
            return False, error_msg

        # 检查密码历史，防止重复使用最近5次密码
        password_history = db.query(PasswordHistory)\
            .filter(PasswordHistory.user_id == user.id)\
            .order_by(PasswordHistory.created_at.desc())\
            .limit(5)\
            .all()

        for history in password_history:
            if verify_password(new_password, history.password_hash):
                AuditService.log(
                    db=db,
                    user_id=user.id,
                    username=user.username,
                    action="CHANGE_PASSWORD_FAILED",
                    resource_type="user",
                    resource_id=user.id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    status="failure",
                    error_message="新密码不能与最近5次使用的密码重复"
                )
                return False, "新密码不能与最近5次使用的密码重复，请选择其他密码"

        # 保存旧密码到历史记录
        history_entry = PasswordHistory(
            user_id=user.id,
            password_hash=user.password_hash
        )
        db.add(history_entry)

        # 更新密码
        user.password_hash = get_password_hash(new_password)
        user.password_changed_at = datetime.utcnow()
        db.commit()

        # 记录审计日志
        AuditService.log(
            db=db,
            user_id=user.id,
            username=user.username,
            action="CHANGE_PASSWORD_SUCCESS",
            resource_type="user",
            resource_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            status="success"
        )

        return True, None

    @staticmethod
    def get_user_menus(db: Session, user: User) -> List[Dict[str, Any]]:
        """
        获取用户可访问的菜单树

        Args:
            db: 数据库会话
            user: 用户对象

        Returns:
            List[Dict[str, Any]]: 菜单树列表
        """
        # 查询所有可见菜单
        query = db.query(Menu).filter(Menu.is_visible == True)

        if not user.is_admin:
            # 非管理员，只获取角色授权的菜单
            if user.role and user.role.menus:
                # 获取该角色授权的所有菜单ID
                menu_ids = [menu.id for menu in user.role.menus]
                query = query.filter(Menu.id.in_(menu_ids))
            else:
                # 没有角色，返回空列表
                return []

        # 获取所有符合条件的菜单并按排序字段排序
        menus = query.order_by(Menu.sort_order.asc()).all()

        # 构建菜单树
        return AuthService._build_menu_tree(menus)

    @staticmethod
    def _create_session(
        db: Session,
        user: User,
        access_token: str,
        refresh_token: str,
        ip_address: str = None,
        user_agent: str = None
    ) -> UserSession:
        """
        创建用户会话记录

        Args:
            db: 数据库会话
            user: 用户对象
            access_token: 访问令牌
            refresh_token: 刷新令牌
            ip_address: IP地址
            user_agent: 用户代理

        Returns:
            UserSession: 创建的会话对象
        """
        # 对令牌进行哈希存储，不保存明文
        token_hash = hashlib.sha256(access_token.encode()).hexdigest()
        refresh_token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

        session = UserSession(
            user_id=user.id,
            token_hash=token_hash,
            refresh_token_hash=refresh_token_hash,
            ip_address=ip_address,
            user_agent=user_agent,
            is_active=True
        )

        db.add(session)
        db.commit()
        db.refresh(session)

        return session

    @staticmethod
    def _build_menu_tree(menus: List[Menu]) -> List[Dict[str, Any]]:
        """
        递归构建菜单树

        Args:
            menus: 所有菜单列表

        Returns:
            List[Dict[str, Any]]: 根菜单列表，包含子菜单
        """
        # 转换为字典并按parent_id分组
        menu_map: Dict[Optional[int], List[Menu]] = {}
        menu_dict: Dict[int, Dict[str, Any]] = {}

        for menu in menus:
            menu_dict[menu.id] = menu.to_dict(include_children=False)
            if menu.parent_id not in menu_map:
                menu_map[menu.parent_id] = []
            menu_map[menu.parent_id].append(menu)

        # 为每个菜单设置子菜单
        for menu_id, menu_data in menu_dict.items():
            if menu_id in menu_map:
                children = []
                for child_menu in sorted(menu_map[menu_id], key=lambda x: x.sort_order):
                    children.append(menu_dict[child_menu.id])
                if children:
                    menu_data["children"] = children

        # 返回根菜单（parent_id为None的菜单）
        root_menus = []
        if None in menu_map:
            for root_menu in sorted(menu_map[None], key=lambda x: x.sort_order):
                root_menus.append(menu_dict[root_menu.id])

        return root_menus

    @staticmethod
    def _get_login_config(db: Session) -> Tuple[int, int]:
        """
        获取登录配置，从SystemConfig读取，使用默认值如果配置不存在

        Args:
            db: 数据库会话

        Returns:
            Tuple[int, int]: (最大登录尝试次数, 锁定分钟数)
        """
        # 默认值
        max_attempts = 5
        lockout_minutes = 30

        # 读取最大尝试次数配置
        max_attempts_config = db.query(SystemConfig).filter(
            and_(
                SystemConfig.category == "auth",
                SystemConfig.key == "login_max_attempts"
            )
        ).first()

        if max_attempts_config and max_attempts_config.value:
            try:
                max_attempts = int(max_attempts_config.value)
            except ValueError:
                pass

        # 读取锁定时间配置
        lockout_config = db.query(SystemConfig).filter(
            and_(
                SystemConfig.category == "auth",
                SystemConfig.key == "login_lockout_minutes"
            )
        ).first()

        if lockout_config and lockout_config.value:
            try:
                lockout_minutes = int(lockout_config.value)
            except ValueError:
                pass

        return max_attempts, lockout_minutes
