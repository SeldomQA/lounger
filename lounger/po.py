import pathlib
import sys
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Pattern,
    Union,
)

from playwright._impl._api_structures import (
    FilePayload,
    FloatRect,
    Position,
)
from playwright._impl._element_handle import ElementHandle
from playwright._impl._helper import (
    KeyboardModifier,
    MouseButton,
    locals_to_params,
)
from playwright._impl._js_handle import Serializable

from lounger.config import Lounger
from lounger.log import log

if sys.version_info >= (3, 8):  # pragma: no cover
    from typing import Literal
else:  # pragma: no cover
    from typing_extensions import Literal

if TYPE_CHECKING:  # pragma: no cover
    from playwright.sync_api import FrameLocator, JSHandle, Page


class BasePage(object):
    """
    Page Object pattern.
    """

    def __init__(self, page):
        """
        :param page: `playwright.sync_api.Page`
        Root URI to base any calls to the ``PageObject.get`` method. If not defined
        in the constructor it will try and look it from the webdriver object.
        """
        self.page = page


class Locator:
    """
    Returns an element object
    """

    def __init__(
            self,
            selector: str,
            describe: str = "",
            position: Position = None,
            modifiers: List[KeyboardModifier] = None,
            delay: float = None,
            timeout: float = None,
            force: bool = None,
            no_wait_after: bool = None,
            trial: bool = None):
        self.selector = selector
        self.desc = describe
        self.position = position
        self.modifiers = modifiers
        self.delay = delay
        self.timeout = timeout
        self.force = force
        self.no_wait_after = no_wait_after
        self.trial = trial

    @property
    def find(self):
        """
        playwright locator, find element and return object.
        :return:
        """
        elem = self.driver.locator(self.selector)
        if self.desc == "":
            log.info(f"✨ Find element {self.selector} -> {Lounger.action}. ")
        else:
            log.info(f"✨ Find element [{self.desc}] {self.selector} -> {Lounger.action}.")
        Lounger.action = None
        return elem

    def __getattr__(self, name: str) -> Any:
        """
        Delegate any not-hand-written Playwright Locator member to the real
        locator (3.9: API-drift governance, plan option A).

        Keeps ``Lounger.action`` logging consistent with the hand-written
        methods, and transparently forwards args/kwargs. This eliminates
        "missing method" drift: new/renamed Playwright Locator members are
        available without updating this class.

        :param name: Attribute name not found on this class.
        :return: The attribute from the underlying Playwright locator.
        """
        underlying = object.__getattribute__(self, "find")
        if not hasattr(underlying, name):
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}' "
                f"(and Playwright Locator has no '{name}' either)"
            )

        attr = getattr(underlying, name)
        # record the action for the find() log, mirroring hand-written methods
        Lounger.action = f"{name}()" if callable(attr) else name

        def _delegate(*args, **kwargs):
            result = attr(*args, **kwargs)
            # unwrap raw playwright Locator results back into lounger Locator
            return result

        return _delegate if callable(attr) else attr

    def __get__(self, instance, owner):
        if instance is None:
            return None

        self.driver = instance.page
        return self

    def __set__(self, instance, value):
        elem = self.__get__(instance, instance.__class__)
        elem.fill(value)

    def all_inner_texts(self) -> List[str]:
        """
        Returns an array of node.innerText values for all matching nodes.
        :return:
        """
        Lounger.action = "all_inner_texts()"
        return self.find.all_inner_texts()

    def all_text_contents(self) -> List[str]:
        """
        Returns an array of node.textContent values for all matching nodes.
        :return:
        """
        Lounger.action = "all_text_contents()"
        return self.find.all_text_contents()

    def bounding_box(self) -> Optional[FloatRect]:
        """
        This method returns the bounding box of the element, or null if the element is not visible.
        :param timeout:
        :return:
        """
        Lounger.action = "bounding_box()"
        return self.find.bounding_box(timeout=self.timeout)

    def fill(self, value: str) -> None:
        """
        Text input
        :param value:
        :return:
        """
        Lounger.action = f"fill({value})"
        return self.find.fill(
            value=value,
            timeout=self.timeout,
            no_wait_after=self.no_wait_after,
            force=self.force,
        )

    def clear(self) -> None:
        """
        Clear the input field.
        :return:
        """
        Lounger.action = "clear()"
        return self.find.clear(
            timeout=self.timeout,
            no_wait_after=self.no_wait_after,
            force=self.force,
        )

    def press_sequentially(self, text: str, delay: Optional[float] = None) -> None:
        """
            Focuses the element, and then sends a `keydown`, `keypress`/`input`, and `keyup` event for each character in the
        text.
        :param delay:
        :param text:
        :return:
        """
        Lounger.action = "press_sequentially()"
        return self.find.press_sequentially(
            text=text,
            delay=delay,
            timeout=self.timeout,
            no_wait_after=self.no_wait_after,
        )

    def check(self) -> None:
        """
        Check the checkbox.
        :return:
        """
        Lounger.action = "check()"
        return self.find.check(
            position=self.position,
            timeout=self.timeout,
            force=self.force,
            no_wait_after=self.no_wait_after,
            trial=self.trial,
        )

    def uncheck(self) -> None:
        """
        Uncheck by input <label>
        :return:
        """
        Lounger.action = "uncheck()"
        return self.find.uncheck(
            position=self.position,
            timeout=self.timeout,
            force=self.force,
            no_wait_after=self.no_wait_after,
            trial=self.trial
        )

    def set_checked(self, checked: bool):
        """
        Set the state of a checkbox or a radio element.
        :param checked:
        :return:
        """
        Lounger.action = "set_checked()"
        return self.find.set_checked(
            checked=checked,
            position=self.position,
            timeout=self.timeout,
            force=self.force,
            no_wait_after=self.no_wait_after,
            trial=self.trial
        )

    def select_option(
            self,
            value: Union[str, List[str]] = None,
            index: Union[int, List[int]] = None,
            label: Union[str, List[str]] = None,
            element: Union["ElementHandle", List["ElementHandle"]] = None,
    ) -> List[str]:
        """
        Selects one or multiple options in the <select> element.
        :return:
        """
        Lounger.action = "select_option()"
        return self.find.select_option(
            value=value,
            index=index,
            label=label,
            element=element,
            timeout=self.timeout,
            no_wait_after=self.no_wait_after,
            force=self.force
        )

    def select_text(self) -> None:
        """
        This method waits for actionability checks,
         then focuses the element and selects all its text content.
        :return:
        """
        Lounger.action = "select_text()"
        return self.find.select_text(
            force=self.force,
            timeout=self.timeout
        )



    def click(self, click_count: int = None, button: MouseButton = None) -> None:
        """
        click
        :param click_count:
        :param button:
        :return:
        """
        Lounger.action = "click()"
        return self.find.click(
            modifiers=self.modifiers,
            position=self.position,
            delay=self.delay,
            button=button,
            click_count=click_count,
            timeout=self.timeout,
            force=self.force,
            no_wait_after=self.no_wait_after,
            trial=self.trial,
        )

    def count(self) -> int:
        """
        Returns the number of elements matching given selector.
        :return:
        """
        Lounger.action = "count()"
        return self.find.count()

    def dblclick(self, button: MouseButton = None) -> None:
        """
        double click
        :param button:
        :return:
        """
        Lounger.action = "dblclick()"
        return self.find.dblclick(
            modifiers=self.modifiers,
            position=self.position,
            delay=self.delay,
            button=button,
            timeout=self.timeout,
            force=self.force,
            no_wait_after=self.no_wait_after,
            trial=self.trial,
        )

    def drag_to(
            self,
            target: "Locator",
            source_position: Position = None,
            target_position: Position = None
    ) -> None:
        """
        Locator of the element to drag to.
        :param target:
        :return:
        """
        Lounger.action = "drag_to()"
        return self.find.drag_to(
            target=target,
            force=self.force,
            no_wait_after=self.no_wait_after,
            timeout=self.timeout,
            trial=self.trial,
            source_position=source_position,
            target_position=target_position,
        )

    def element_handle(self) -> ElementHandle:
        """
        Resolves given locator to the first matching DOM element
        :return:
        """
        Lounger.action = "element_handle()"
        return self.find.element_handle(timeout=self.timeout)

    def element_handles(self) -> List[ElementHandle]:
        """
        Resolves given locator to all matching DOM elements.
        :return:
        """
        Lounger.action = "element_handles()"
        return self.find.element_handles()

    @property
    def first(self) -> "Locator":
        """
        Returns locator to the first matching element.
        :return:
        """
        Lounger.action = "first"
        return self.find.first

    @property
    def last(self) -> "Locator":
        """
        Returns locator to the last matching element.
        :return:
        """
        Lounger.action = "last"
        return self.find.last

    def nth(self, index: int) -> "Locator":
        """
        Returns locator to the n-th matching element. It's zero based, nth(0) selects the first element.
        :param index:
        :return:
        """
        Lounger.action = f"nth({index})"
        return self.find.nth(index=index)

    def all(self) -> List["Locator"]:
        """
        When the locator points to a list of elements, this returns an array of locators, pointing to their respective
        elements.
        :return:
        """
        Lounger.action = "all()"
        return self.find.all()

    @property
    def page(self) -> "Page":
        """
        A page this locator belongs to.
        :return:
        """
        Lounger.action = "page"
        return self.find.page()

    @property
    def content_frame(self) -> "FrameLocator":
        """
        Returns a `FrameLocator` object pointing to the same `iframe` as this locator.
        :return:
        """
        Lounger.action = "content_frame"
        return self.find.content_frame

    def frame_locator(self, selector: str) -> "FrameLocator":
        """
        When working with iframes, you can create a frame locator that will enter the iframe and allow locating elements in
        that iframe:
        :param selector:
        :return:
        """
        Lounger.action = "frame_locator()"
        return self.find.frame_locator(selector=selector)

    def filter(
            self,
            has_text: Union[str, Pattern[str]] = None,
            has: "Locator" = None,
    ) -> "Locator":
        """
        This method narrows existing locator according to the options.
        :param has_text:
        :param has:
        :return:
        """
        Lounger.action = "filter()"
        return self.find.filter(has_text=has_text, has=has)

    def input_value(self, timeout: Optional[float] = None) -> str:
        """
        Returns the value for the matching `<input>` or `<textarea>` or `<select>` element.
        :param timeout:
        :return:
        """
        Lounger.action = "input_value()"
        return self.find.input_value(timeout=timeout)

    def get_attribute(self, name: str):
        """
        Returns element attribute value.
        :param name:
        :return:
        """
        Lounger.action = f"get_attribute({name})"
        return self.find.get_attribute(name=name, timeout=self.timeout)

    def highlight(self) -> None:
        Lounger.action = "highlight()"
        return self.find.highlight()

    def hover(self) -> None:
        """
        Hover over element
        :return:
        """
        Lounger.action = "hover()"
        return self.find.hover(
            modifiers=self.modifiers,
            position=self.position,
            timeout=self.timeout,
            force=self.force,
            trial=self.trial,
        )

    def dispatch_event(self, type: str, event_init: Dict = None) -> None:
        """
        Programmatic click
        :param type:
        :param event_init: Optional event data (playwright param is ``event_init``).
        :return:
        """
        Lounger.action = "dispatch_event()"
        return self.find.dispatch_event(
            type=type,
            event_init=event_init,
            timeout=self.timeout,
        )

    def evaluate(self, expression: str, arg: Serializable = None) -> Any:
        """
        This method passes this handle as the first argument to expression.
        :param expression:
        :param arg:
        :param timeout:
        :return:
        """
        Lounger.action = "evaluate()"
        return self.find.evaluate(
            expression=expression,
            arg=arg,
            timeout=self.timeout
        )

    def evaluate_all(self, expression: str, arg: Serializable = None) -> Any:
        """
        The method finds all elements matching the specified locator and
        passes an array of matched elements as a first argument to expression.
        Returns the result of expression invocation.
        :param expression:
        :param arg:
        :return:
        """
        Lounger.action = "evaluate_all()"
        params = locals_to_params(locals())
        return self.find.evaluate_all(
            expression=expression,
            arg=arg
        )

    def evaluate_handle(self, expression: str, arg: Serializable = None) -> "JSHandle":
        """
        This method passes this handle as the first argument to expression.
        :param expression:
        :param arg:
        :param timeout:
        :return:
        """
        Lounger.action = "evaluate_handle()"
        return self.find.evaluate_handle(
            expression=expression,
            arg=arg,
            timeout=self.timeout
        )

    def tap(self) -> None:
        """
        This method taps the element.
        :return:
        """
        Lounger.action = "tap()"
        return self.find.tap(
            modifiers=self.modifiers,
            position=self.position,
            timeout=self.timeout,
            force=self.force,
            no_wait_after=self.no_wait_after,
            trial=self.trial,
        )

    def text_content(self) -> Optional[str]:
        """
        Returns the node.textContent.
        :return:
        """
        Lounger.action = "text_content()"
        return self.find.text_content(timeout=self.timeout)

    def type(self, text: str) -> None:
        """
        Type into the field character by character, as if it was a user with a real keyboard.
        :param text:
        :return:
        """
        Lounger.action = f"type({text})"
        return self.find.type(
            text=text,
            delay=self.delay,
            timeout=self.timeout,
            no_wait_after=self.no_wait_after,
        )

    def press(self, key: str) -> None:
        """
        Keys and shortcuts
        :param key:
        :return:
        """
        Lounger.action = f"press({key})"
        return self.find.press(
            delay=self.delay,
            timeout=self.timeout,
            no_wait_after=self.no_wait_after,
        )

    def set_input_files(
            self,
            files: Union[
                str,
                pathlib.Path,
                FilePayload,
                List[Union[str, pathlib.Path]],
                List[FilePayload],
            ]
    ) -> None:
        """
        Upload files
        :param files:
        :return:
        """
        Lounger.action = "set_input_files()"
        return self.find.set_input_files(
            files=files,
            timeout=self.timeout,
            no_wait_after=self.no_wait_after,
        )

    def focus(self) -> None:
        """
        Focus element
        :return:
        """
        Lounger.action = "focus()"
        return self.find.focus(timeout=self.timeout)

    def blur(self) -> None:
        """
        Calls [blur](https://developer.mozilla.org/en-US/docs/Web/API/HTMLElement/blur) on the element.
        :return:
        """
        Lounger.action = "blur()"
        return self.find.blur(timeout=self.timeout)

    def inner_html(self) -> str:
        """
        Returns the element.innerHTML.
        :return:
        """
        Lounger.action = "inner_html()"
        return self.find.inner_html(timeout=self.timeout)

    def inner_text(self) -> str:
        """
        Returns the element.innerText.
        :return:
        """
        Lounger.action = "inner_text()"
        return self.find.inner_text(timeout=self.timeout)

    def is_checked(self) -> bool:
        """
        Returns whether the element is checked.
        Throws if the element is not a checkbox or radio input.
        :return:
        """
        Lounger.action = "is_checked()"
        return self.find.is_checked(timeout=self.timeout)

    def is_disabled(self) -> bool:
        """
        Returns whether the element is disabled, the opposite of enabled.
        :return:
        """
        Lounger.action = "is_disabled()"
        return self.find.is_disabled(timeout=self.timeout)

    def is_editable(self) -> bool:
        """
        Returns whether the element is editable.
        :return:
        """
        Lounger.action = "is_editable()"
        return self.find.is_editable(timeout=self.timeout)

    def is_enabled(self) -> bool:
        """
        Returns whether the element is enabled.
        :return:
        """
        Lounger.action = "is_enabled()"
        return self.find.is_enabled(timeout=self.timeout)

    def is_hidden(self) -> bool:
        """
        Returns whether the element is hidden, the opposite of visible.
        :return:
        """
        Lounger.action = "is_hidden()"
        return self.find.is_hidden(timeout=self.timeout)

    def is_visible(self) -> bool:
        """
        Returns whether the element is visible.
        :return:
        """
        Lounger.action = "is_visible()"
        return self.find.is_visible(timeout=self.timeout)

    def screenshot(
            self,
            type: Literal["jpeg", "png"] = None,
            path: Union[str, pathlib.Path] = None,
            quality: int = None,
            omit_background: bool = None,
            animations: Literal["allow", "disabled"] = None,
            caret: Literal["hide", "initial"] = None,
            scale: Literal["css", "device"] = None,
            mask: List["Locator"] = None,
    ) -> bytes:
        """
        This method captures a screenshot of the page
        :param type:
        :param path:
        :param quality:
        :param omit_background:
        :param animations:
        :param caret:
        :param scale:
        :param mask:
        :return:
        """
        Lounger.action = "screenshot()"
        return self.find.screenshot(
            timeout=self.timeout,
            type=type,
            path=path,
            quality=quality,
            omit_background=omit_background,
            animations=animations,
            caret=caret,
            scale=scale,
            mask=mask,
        )

    def scroll_into_view_if_needed(self) -> None:
        """
        This method waits for actionability checks, then tries to scroll element into view,
         unless it is completely visible as defined by IntersectionObserver's ratio.
        :return:
        """
        Lounger.action = "scroll_into_view_if_needed()"
        return self.find.scroll_into_view_if_needed(timeout=self.timeout)

    def wait_for(self, state: Literal["attached", "detached", "hidden", "visible"] = None) -> None:
        """
        Returns when element specified by locator satisfies the state option.
        :param state:
        :return:
        """
        Lounger.action = "wait_for()"
        return self.find.wait_for(
            timeout=self.timeout,
            state=state,
        )

    def locator(
            self,
            selector_or_locator: Union["Locator", str],
            has_text: Union[str, Pattern[str]] = None,
            has_not_text: Union[str, Pattern[str]] = None,
            has: "Locator" = None,
            has_not: "Locator" = None,
    ) -> "Locator":
        """
        The method finds an element matching the specified selector in the locator's subtree.
        It also accepts filter options, similar to `locator.filter()` method.
        :param selector_or_locator: A selector or locator to use when resolving DOM element.
        :param has_text: Matches elements containing specified text somewhere inside, possibly in a child or a descendant element.
        :param has_not_text: Matches elements that do not contain specified text somewhere inside, possibly in a child or a descendant element.
        :param has: Narrows down the results of the method to those which contain elements matching this relative locator.
        :param has_not: Matches elements that do not contain an element that matches an inner locator.
        :return:
        """
        Lounger.action = "locator()"
        return self.find.locator(
            selectorOrLocator=selector_or_locator,
            hasText=has_text,
            hasNotText=has_not_text,
            has=has.find if has else None,
            hasNot=has_not.find if has_not else None,
        )

    def get_by_alt_text(
            self,
            text: Union[str, Pattern[str]],
            exact: bool = None,
    ) -> "Locator":
        """
        Allows locating elements by their alt text.
        :param text: Text to locate the element for.
        :param exact: Whether to find an exact match: case-sensitive and whole-string.
        :return:
        """
        Lounger.action = "get_by_alt_text()"
        return self.find.get_by_alt_text(text=text, exact=exact)

    def get_by_label(
            self,
            text: Union[str, Pattern[str]],
            exact: bool = None,
    ) -> "Locator":
        """
        Allows locating input elements by the text of the associated `<label>` or `aria-labelledby` element, or by the
        `aria-label` attribute.
        :param text: Text to locate the element for.
        :param exact: Whether to find an exact match: case-sensitive and whole-string.
        :return:
        """
        Lounger.action = "get_by_label()"
        return self.find.get_by_label(text=text, exact=exact)

    def get_by_placeholder(
            self,
            text: Union[str, Pattern[str]],
            exact: bool = None,
    ) -> "Locator":
        """
        Allows locating input elements by the placeholder text.
        :param text: Text to locate the element for.
        :param exact: Whether to find an exact match: case-sensitive and whole-string.
        :return:
        """
        Lounger.action = "get_by_placeholder()"
        return self.find.get_by_placeholder(text=text, exact=exact)

    def get_by_role(
            self,
            role: Literal[
                "alert",
                "alertdialog",
                "application",
                "article",
                "banner",
                "blockquote",
                "button",
                "caption",
                "cell",
                "checkbox",
                "code",
                "columnheader",
                "combobox",
                "complementary",
                "contentinfo",
                "definition",
                "deletion",
                "dialog",
                "directory",
                "document",
                "emphasis",
                "feed",
                "figure",
                "form",
                "generic",
                "grid",
                "gridcell",
                "group",
                "heading",
                "img",
                "insertion",
                "link",
                "list",
                "listbox",
                "listitem",
                "log",
                "main",
                "marquee",
                "math",
                "menu",
                "menubar",
                "menuitem",
                "menuitemcheckbox",
                "menuitemradio",
                "meter",
                "navigation",
                "none",
                "note",
                "option",
                "paragraph",
                "presentation",
                "progressbar",
                "radio",
                "radiogroup",
                "region",
                "row",
                "rowgroup",
                "rowheader",
                "scrollbar",
                "search",
                "searchbox",
                "separator",
                "slider",
                "spinbutton",
                "status",
                "strong",
                "subscript",
                "superscript",
                "switch",
                "tab",
                "table",
                "tablist",
                "tabpanel",
                "term",
                "textbox",
                "time",
                "timer",
                "toolbar",
                "tooltip",
                "tree",
                "treegrid",
                "treeitem",
            ],
            checked: bool = None,
            disabled: bool = None,
            expanded: bool = None,
            include_hidden: bool = None,
            level: int = None,
            name: Union[str, Pattern[str]] = None,
            pressed: bool = None,
            selected: bool = None,
            exact: bool = None,
    ) -> "Locator":
        """
        Allows locating elements by their ARIA role, ARIA attributes and accessible name.
        :param role: Required aria role.
        :param checked: An attribute that is usually set by `aria-checked` or native `<input type=checkbox>` controls.
        :param disabled: An attribute that is usually set by `aria-disabled` or `disabled`.
        :param expanded: An attribute that is usually set by `aria-expanded`.
        :param include_hidden: Option that controls whether hidden elements are matched.
        :param level: A number attribute that is usually present for roles `heading`, `listitem`, `row`, `treeitem`.
        :param name: Option to match the accessible name.
        :param pressed: An attribute that is usually set by `aria-pressed`.
        :param selected: An attribute that is usually set by `aria-selected`.
        :param exact: Whether `name` is matched exactly: case-sensitive and whole-string.
        :return:
        """
        Lounger.action = "get_by_role()"
        return self.find.get_by_role(
            role=role,
            checked=checked,
            disabled=disabled,
            expanded=expanded,
            includeHidden=include_hidden,
            level=level,
            name=name,
            pressed=pressed,
            selected=selected,
            exact=exact,
        )

    def get_by_test_id(self, test_id: Union[str, Pattern[str]]) -> "Locator":
        """
        Locate element by the test id.
        :param test_id: Id to locate the element by.
        :return:
        """
        Lounger.action = "get_by_test_id()"
        return self.find.get_by_test_id(testId=test_id)

    def get_by_text(
            self,
            text: Union[str, Pattern[str]],
            exact: bool = None,
    ) -> "Locator":
        """
        Allows locating elements that contain given text.
        :param text: Text to locate the element for.
        :param exact: Whether to find an exact match: case-sensitive and whole-string.
        :return:
        """
        Lounger.action = "get_by_text()"
        return self.find.get_by_text(text=text, exact=exact)

    def get_by_title(
            self,
            text: Union[str, Pattern[str]],
            exact: bool = None,
    ) -> "Locator":
        """
        Allows locating elements by their title attribute.
        :param text: Text to locate the element for.
        :param exact: Whether to find an exact match: case-sensitive and whole-string.
        :return:
        """
        Lounger.action = "get_by_title()"
        return self.find.get_by_title(text=text, exact=exact)

    def describe(self, description: str) -> "Locator":
        """
        Describes the locator, description is used in the trace viewer and reports. Returns the locator pointing to the
        same element.
        :param description: Locator description.
        :return:
        """
        Lounger.action = "describe()"
        return self.find.describe(description=description)

    def or_(self, locator: "Locator") -> "Locator":
        """
        Creates a locator matching all elements that match one or both of the two locators.
        :param locator: Alternative locator to match.
        :return:
        """
        Lounger.action = "or_()"
        return self.find.or_(locator=locator.find)

    def and_(self, locator: "Locator") -> "Locator":
        """
        Creates a locator that matches both this locator and the argument locator.
        :param locator: Additional locator to match.
        :return:
        """
        Lounger.action = "and_()"
        return self.find.and_(locator=locator.find)

    def aria_snapshot(self, timeout: float = None) -> str:
        """
        Captures the aria snapshot of the given element.
        :param timeout: Maximum time in milliseconds.
        :return:
        """
        Lounger.action = "aria_snapshot()"
        return self.find.aria_snapshot(timeout=timeout if timeout is not None else self.timeout)
