"""密码哈希工具:基于 bcrypt。

不使用 passlib(passlib 多年未更新,Python 3.13 有兼容问题)。
直接调用 bcrypt 库,API 简单稳定。
"""
import bcrypt

# bcrypt work factor,4-31 之间,12 是业界推荐值
# 数值越大越安全但越慢(每次约 200-300ms)
_ROUNDS = 12


def hash_password(plain: str) -> str:
    """对明文密码做 bcrypt 哈希。

    Args:
        plain: 明文密码

    Returns:
        形如 "$2b$12$..." 的哈希字符串(已含盐,可直接存库)
    """
    salt = bcrypt.gensalt(rounds=_ROUNDS)
    hashed = bcrypt.hashpw(plain.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码与已存的 bcrypt 哈希是否匹配。

    Args:
        plain: 用户输入的明文密码
        hashed: 库中存的哈希字符串

    Returns:
        True 表示匹配,False 表示不匹配或哈希格式错误
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # hashed 格式非法,统一返回 False,不暴露内部错误
        return False
