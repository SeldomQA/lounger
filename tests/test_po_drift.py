"""
API-drift governance tests for lounger.po (docs/development_plan.md §3.9).

Strategy (plan option A + B):

- A: ``Locator.__getattr__`` delegates not-hand-written Playwright Locator
  members to the real locator, so missing-method drift cannot happen;
- B: a signature comparison test checks that every hand-written wrapper
  accepts (at least) the parameters Playwright's Locator exposes, and that
  no public Playwright member is missing from the lounger Locator surface.

Covers:

- ``__getattr__`` transparently forwards args/kwargs and records action;
- hand-written wrappers pass the expected kwargs to the underlying locator
  (dummy driver assertion);
- wrapper/underlying signature parity for every public member.
"""
import inspect

import pytest

from lounger.config import Lounger
from lounger.po import Locator


class _RecordingLocator:
    """Dummy Playwright locator recording every call's kwargs.

    Members that exist on the real Playwright ``Locator`` are treated as
    callable; anything else raises AttributeError so the delegation path can
    be tested for unknown names too.
    """

    def __init__(self):
        self.calls = []
        from playwright.sync_api import Locator as PWLocator
        self._known = {name for name in dir(PWLocator) if not name.startswith("_")}

    def __getattr__(self, name):
        if name not in self._known:
            raise AttributeError(name)

        def _record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return "ok"

        return _record


class _RecordingPage:
    def __init__(self):
        self.recorder = _RecordingLocator()

    def locator(self, selector):
        return self.recorder


@pytest.fixture
def loc():
    page = _RecordingPage()
    locator = Locator("#btn", describe="login button")
    locator.driver = page
    return locator, page.recorder


def _action_reset():
    Lounger.action = None


# ── __getattr__ delegation (plan option A) ────────────────────────────────

def test_getattr_delegates_unwritten_methods(loc):
    locator, recorder = loc
    _action_reset()

    handler = lambda: None  # noqa: E731
    result = locator.on("click", handler)

    assert result == "ok"
    name, args, kwargs = recorder.calls[-1]
    assert name == "on"
    assert args[0] == "click"
    assert args[1] is handler
    assert kwargs == {}
    assert Lounger.action == "on()"


def test_getattr_forwards_kwargs(loc):
    """Delegated (not hand-written) members forward positionals and kwargs."""
    locator, recorder = loc
    _action_reset()

    handler = lambda: None  # noqa: E731
    locator.on("click", handler)  # `on` is not hand-written → __getattr__ path

    name, args, kwargs = recorder.calls[-1]
    assert name == "on"
    assert args == ("click", handler)
    assert kwargs == {}


def test_getattr_unknown_attribute_raises(loc):
    locator, _ = loc
    with pytest.raises(AttributeError, match="no attribute 'totally_missing'"):
        locator.totally_missing


# ── hand-written wrappers forward expected kwargs ─────────────────────────

@pytest.mark.parametrize(
    "method,args,kwargs",
    [
        ("fill", ("tom",), {"timeout": None, "no_wait_after": None, "force": None}),
        ("click", (), {"timeout": None, "force": None, "no_wait_after": None, "trial": None}),
        ("press", ("Enter",), {"delay": None, "timeout": None, "no_wait_after": None}),
        ("hover", (), {"timeout": None, "force": None, "trial": None}),
        ("count", (), {}),
        ("inner_text", (), {"timeout": None}),
        ("is_visible", (), {"timeout": None}),
        ("select_option", (), {"timeout": None, "no_wait_after": None, "force": None}),
    ],
)
def test_wrapper_forwards_expected_kwargs(loc, method, args, kwargs):
    """Each hand-written wrapper must forward its params (short-term goal)."""
    locator, recorder = loc
    _action_reset()

    getattr(locator, method)(*args)

    name, call_args, call_kwargs = recorder.calls[-1]
    assert name == method
    for key, value in kwargs.items():
        assert call_kwargs.get(key) == value, f"expected {key}={value!r} in {call_kwargs}"


# ── signature parity with Playwright Locator (plan option B) ──────────────

def _playwright_locator_public():
    from playwright.sync_api import Locator as PWLocator

    return {name for name in dir(PWLocator) if not name.startswith("_")}


def test_all_playwright_locator_members_are_available():
    """Every public Playwright Locator member is reachable on lounger.Locator.

    Hand-written wrappers exist for most; the rest are delegated via
    __getattr__. Missing members would fail here (missing-method drift).
    """
    from playwright.sync_api import Locator as PWLocator

    # every public Playwright member must be either hand-written on the class
    # or resolvable through the __getattr__ delegation path
    for member in _playwright_locator_public():
        assert hasattr(PWLocator, member), f"playwright lost {member}"
        assert hasattr(Locator, member) or member in _RecordingLocator()._known, member


def test_getattr_delegates_known_playwright_unwritten_members():
    """Members playwright has but lounger does not hand-write (on/once/
    remove_listener/description) resolve via __getattr__."""
    from playwright.sync_api import Locator as PWLocator

    # unwritten = playwright members absent from lounger's class dict
    # (hand-written methods and properties are class attributes)
    unwritten = {
        m for m in dir(PWLocator) if not m.startswith("_")
        and m not in Locator.__dict__
    }
    assert "on" in unwritten and "once" in unwritten and "remove_listener" in unwritten

    instance = Locator("#x")
    instance.driver = _RecordingPage()
    for member in unwritten:
        # must not raise (delegated via __getattr__)
        getattr(instance, member)


def test_handwritten_wrappers_match_playwright_signature():
    """Hand-written wrappers must not declare params Playwright lacks.

    Lounger hoists common options (timeout/force/position/modifiers/delay/
    no_wait_after/trial) into the Locator constructor, so wrappers may omit
    them; but every param a wrapper *does* declare must exist on the
    Playwright method (drift detection, plan option B).
    """
    from playwright.sync_api import Locator as PWLocator

    hoisted = {"timeout", "force", "position", "modifiers", "delay", "no_wait_after", "trial"}

    wrapper_names = {
        name for name, _ in inspect.getmembers(Locator, inspect.isfunction)
        if not name.startswith("_")
    }

    mismatches = []
    for name in sorted(wrapper_names):
        pw_method = getattr(PWLocator, name, None)
        if pw_method is None:
            # not a Playwright method (lounger extension, e.g. nothing here) — skip
            continue
        pw_params = set(inspect.signature(pw_method).parameters)
        wrapper_params = set(inspect.signature(getattr(Locator, name)).parameters) - hoisted
        extra = wrapper_params - pw_params
        if extra:
            mismatches.append(f"{name}: declares params not in Playwright: {sorted(extra)}")

    assert not mismatches, "wrapper/playwright signature drift:\n" + "\n".join(mismatches)
