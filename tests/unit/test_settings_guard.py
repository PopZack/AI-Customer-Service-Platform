"""配置层单测：生产环境的密钥守卫。

这是一条**安全控制**，必须有测试盯着 —— 否则以后有人"顺手"放开校验、
或者改了默认值字符串，都不会有人发现。

不需要数据库，纯配置层校验，跑得极快。
"""
import pytest
from pydantic import ValidationError

from app.config.settings import Settings

_DEFAULT = "change_me"
_STRONG = "a-sufficiently-long-secret-for-hs256-0123456789"


@pytest.mark.parametrize("env", ["dev", "test", "staging"])
def test_非生产环境允许使用默认密钥(env: str):
    """开发/测试环境不该被密钥校验拦住，否则本地跑不起来。"""
    s = Settings(APP_ENV=env, JWT_SECRET=_DEFAULT)
    assert s.JWT_SECRET == _DEFAULT


def test_生产环境禁止使用默认密钥():
    """默认密钥签发 token = 任何人都能伪造身份，必须在启动时炸掉。"""
    with pytest.raises(ValidationError) as exc:
        Settings(APP_ENV="prod", JWT_SECRET=_DEFAULT)
    assert "JWT_SECRET" in str(exc.value)


def test_生产环境拒绝过短的密钥():
    """HS256 密钥太短抗不住暴力破解（PyJWT 也会对 <32 字节告警）。"""
    with pytest.raises(ValidationError):
        Settings(APP_ENV="prod", JWT_SECRET="short_secret")


def test_生产环境接受足够强的密钥():
    assert Settings(APP_ENV="prod", JWT_SECRET=_STRONG).JWT_SECRET == _STRONG
